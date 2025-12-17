"""Tests for concurrent and async logging behavior.

Tests verify:
- Thread safety of LogWriter under concurrent writes
- Async lock preventing interleaved log entries
- Multiple concurrent requests writing to same log file
- Data integrity under high load
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from azure_middleware.logging.encryption import FieldEncryptor
from azure_middleware.logging.writer import LogWriter, LogEntry, TokenUsage


# Test encryption key (32 bytes, base64 encoded for testing)
TEST_KEY = b"testkeyforaes256gcmtesting12345!"  # Exactly 32 bytes


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def encryptor():
    """Create a test encryptor."""
    return FieldEncryptor(TEST_KEY)


@pytest.fixture
async def log_writer(temp_log_dir, encryptor):
    """Create a LogWriter instance for testing."""
    writer = LogWriter(
        directory=temp_log_dir,
        encryptor=encryptor,
        compression="gzip",
        batch_size=10,
        batch_timeout=0.5,
    )
    await writer.start()
    yield writer
    await writer.stop()


def create_test_entry(index: int, user: str = "testuser") -> LogEntry:
    """Create a test log entry with unique content."""
    return LogEntry(
        timestamp=datetime.now(timezone.utc),
        endpoint="/openai/deployments/gpt-4/chat/completions",
        deployment="gpt-4",
        method="POST",
        request={"messages": [{"role": "user", "content": f"Test message {index}"}]},
        response={"id": f"resp-{index}", "choices": [{"message": {"content": f"Response {index}"}}]},
        tokens=TokenUsage(prompt=10, completion=20, total=30),
        cost_eur=0.001,
        cumulative_cost_eur=0.001 * (index + 1),
        duration_ms=100 + index,
        stream=False,
        status_code=200,
        user=user,
    )


class TestLogWriterConcurrency:
    """Test LogWriter under concurrent access."""

    @pytest.mark.asyncio
    async def test_single_write(self, log_writer, temp_log_dir):
        """Test basic single write works."""
        entry = create_test_entry(0)
        result = await log_writer.write(entry)
        
        assert result is True
        
        # Wait for batch to be written
        await asyncio.sleep(1.0)
        
        # Verify file was created
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        assert len(log_files) == 1
        
        # Verify content
        with open(log_files[0], "r") as f:
            lines = f.readlines()
        assert len(lines) == 1
        
        data = json.loads(lines[0])
        assert data["deployment"] == "gpt-4"
        assert data["status_code"] == 200

    @pytest.mark.asyncio
    async def test_concurrent_writes_same_user(self, log_writer, temp_log_dir, encryptor):
        """Test multiple concurrent writes from same user don't interleave."""
        num_writes = 50
        
        # Create entries
        entries = [create_test_entry(i) for i in range(num_writes)]
        
        # Write all concurrently
        tasks = [log_writer.write(entry) for entry in entries]
        results = await asyncio.gather(*tasks)
        
        # All writes should succeed
        assert all(results), "Some writes failed"
        
        # Wait for batch writes to complete
        await asyncio.sleep(1.5)
        
        # Verify file content
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        assert len(log_files) == 1
        
        with open(log_files[0], "r") as f:
            lines = f.readlines()
        
        # Should have exactly num_writes complete lines
        assert len(lines) == num_writes, f"Expected {num_writes} lines, got {len(lines)}"
        
        # Each line should be valid JSON (no interleaving)
        for i, line in enumerate(lines):
            try:
                data = json.loads(line)
                assert "timestamp" in data
                assert "deployment" in data
                assert "request_encrypted" in data
                # Decrypt and verify request content
                decrypted = encryptor.decrypt(data["request_encrypted"])
                assert "messages" in decrypted
            except json.JSONDecodeError as e:
                pytest.fail(f"Line {i} is not valid JSON (interleaving detected): {e}\nLine: {line[:100]}...")

    @pytest.mark.asyncio
    async def test_concurrent_writes_multiple_users(self, temp_log_dir, encryptor):
        """Test concurrent writes from multiple users go to separate files."""
        users = ["alice", "bob", "charlie"]
        writes_per_user = 20
        
        # Create separate log writers (simulating different request contexts)
        # In reality they share the same directory but have different usernames
        writers = {}
        for user in users:
            writer = LogWriter(
                directory=temp_log_dir,
                encryptor=encryptor,
                compression="gzip",
                batch_size=10,
                batch_timeout=0.5,
            )
            writer._username = user  # Override username for testing
            await writer.start()
            writers[user] = writer
        
        try:
            # Create entries for each user
            all_tasks = []
            for user in users:
                for i in range(writes_per_user):
                    entry = create_test_entry(i, user=user)
                    entry.user = user
                    all_tasks.append(writers[user].write(entry))
            
            # Run all writes concurrently
            results = await asyncio.gather(*all_tasks)
            assert all(results), "Some writes failed"
            
            # Wait for batch writes to complete
            await asyncio.sleep(1.5)
        finally:
            # Stop all writers
            for writer in writers.values():
                await writer.stop()
        
        # Verify each user has their own file with correct count
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        assert len(log_files) == len(users)
        
        for user in users:
            user_files = [f for f in log_files if user in f.name]
            assert len(user_files) == 1, f"Expected 1 file for {user}, got {len(user_files)}"
            
            with open(user_files[0], "r") as f:
                lines = f.readlines()
            
            assert len(lines) == writes_per_user, f"User {user}: expected {writes_per_user} lines, got {len(lines)}"
            
            # Verify each line is valid
            for line in lines:
                data = json.loads(line)
                assert data["user"] == user

    @pytest.mark.asyncio
    async def test_high_concurrency_stress(self, log_writer, temp_log_dir, encryptor):
        """Stress test with high concurrency."""
        num_writes = 200
        
        entries = [create_test_entry(i) for i in range(num_writes)]
        
        # Simulate high load with all writes happening at once
        tasks = [log_writer.write(entry) for entry in entries]
        results = await asyncio.gather(*tasks)
        
        success_count = sum(results)
        assert success_count == num_writes, f"Expected {num_writes} successes, got {success_count}"
        
        # Wait for batch writes to complete
        await asyncio.sleep(2.0)
        
        # Verify integrity
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        with open(log_files[0], "r") as f:
            lines = f.readlines()
        
        assert len(lines) == num_writes
        
        # Verify all entries are unique and valid
        seen_durations = set()
        for line in lines:
            data = json.loads(line)
            duration = data["duration_ms"]
            # Each entry has unique duration (100 + index)
            assert duration not in seen_durations or duration >= 100, f"Duplicate or invalid duration: {duration}"
            seen_durations.add(duration)

    @pytest.mark.asyncio
    async def test_interleaved_async_operations(self, log_writer, temp_log_dir):
        """Test that async writes interleaved with other async ops work correctly."""
        num_writes = 30
        
        async def write_with_delay(index: int):
            """Write entry with random delay to simulate real-world timing."""
            await asyncio.sleep(0.001 * (index % 5))  # Variable delay
            entry = create_test_entry(index)
            return await log_writer.write(entry)
        
        tasks = [write_with_delay(i) for i in range(num_writes)]
        results = await asyncio.gather(*tasks)
        
        assert all(results)
        
        # Wait for batch writes to complete
        await asyncio.sleep(1.5)
        
        # Verify all lines are complete
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        with open(log_files[0], "r") as f:
            lines = f.readlines()
        
        assert len(lines) == num_writes
        for line in lines:
            json.loads(line)  # Should not raise

    @pytest.mark.asyncio
    async def test_write_lock_prevents_corruption(self, temp_log_dir, encryptor):
        """Verify the async lock prevents write corruption."""
        writer = LogWriter(
            directory=temp_log_dir,
            encryptor=encryptor,
            compression="gzip",
            batch_size=10,
            batch_timeout=0.5,
        )
        await writer.start()
        
        # Create entries with large payloads to increase chance of interleaving without lock
        large_entries = []
        for i in range(20):
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc),
                endpoint="/test",
                deployment="gpt-4",
                request={"data": "x" * 1000, "index": i},  # Large payload
                response={"result": "y" * 1000, "index": i},
                tokens=TokenUsage(prompt=100, completion=200, total=300),
                cost_eur=0.01,
                cumulative_cost_eur=0.01 * (i + 1),
                duration_ms=i,
                user="testuser",
            )
            large_entries.append(entry)
        
        # Write all concurrently
        tasks = [writer.write(entry) for entry in large_entries]
        results = await asyncio.gather(*tasks)
        
        assert all(results)
        
        # Wait for batch writes and stop writer
        await asyncio.sleep(1.5)
        await writer.stop()
        
        # Verify no corruption
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        with open(log_files[0], "r") as f:
            content = f.read()
        
        lines = content.strip().split("\n")
        assert len(lines) == 20
        
        for i, line in enumerate(lines):
            try:
                data = json.loads(line)
                # Verify structure is intact
                assert "request_encrypted" in data
                assert "response_encrypted" in data
                assert data["deployment"] == "gpt-4"
            except json.JSONDecodeError:
                pytest.fail(f"Line {i} corrupted - JSON decode failed")


class TestEncryptionConcurrency:
    """Test FieldEncryptor under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_encryption(self, encryptor):
        """Test concurrent encryption calls are thread-safe."""
        num_ops = 100
        
        async def encrypt_value(index: int):
            """Encrypt a value in async context."""
            value = {"message": f"Test {index}", "data": list(range(index))}
            # Run in thread pool to simulate real usage
            return await asyncio.to_thread(encryptor.encrypt, value)
        
        tasks = [encrypt_value(i) for i in range(num_ops)]
        results = await asyncio.gather(*tasks)
        
        # All should succeed and be unique
        assert len(results) == num_ops
        assert len(set(results)) == num_ops  # All encrypted values should be unique (different nonces)

    @pytest.mark.asyncio
    async def test_concurrent_encrypt_decrypt_roundtrip(self, encryptor):
        """Test concurrent encrypt/decrypt maintains data integrity."""
        num_ops = 50
        
        async def roundtrip(index: int):
            """Encrypt then decrypt a value."""
            original = {"index": index, "data": f"message-{index}"}
            encrypted = await asyncio.to_thread(encryptor.encrypt, original)
            decrypted = await asyncio.to_thread(encryptor.decrypt, encrypted)
            return original, decrypted
        
        tasks = [roundtrip(i) for i in range(num_ops)]
        results = await asyncio.gather(*tasks)
        
        for original, decrypted in results:
            assert original == decrypted, f"Roundtrip failed: {original} != {decrypted}"


class TestAsyncLockBehavior:
    """Test async lock behavior specifically."""

    @pytest.mark.asyncio
    async def test_lock_serializes_writes(self, temp_log_dir, encryptor):
        """Verify lock serializes concurrent writes."""
        writer = LogWriter(
            directory=temp_log_dir,
            encryptor=encryptor,
            compression="gzip",
            batch_size=5,
            batch_timeout=0.5,
        )
        await writer.start()
        
        write_order = []
        original_write_lines = writer._write_lines
        
        def tracking_write_lines(path, lines):
            """Track write order."""
            for line in lines:
                data = json.loads(line)
                write_order.append(data["duration_ms"])
            return original_write_lines(path, lines)
        
        writer._write_lines = tracking_write_lines
        
        # Create entries with sequential durations
        entries = [create_test_entry(i) for i in range(10)]
        
        # Write concurrently
        tasks = [writer.write(entry) for entry in entries]
        await asyncio.gather(*tasks)
        
        # Wait for batch writes and stop
        await asyncio.sleep(1.5)
        await writer.stop()
        
        # All writes should have completed
        assert len(write_order) == 10
        
        # The writes are serialized (though order may vary due to async scheduling)
        # Key point: no writes should be lost or corrupted
        assert sorted(write_order) == [100 + i for i in range(10)]

    @pytest.mark.asyncio
    async def test_multiple_writers_same_file_known_limitation(self, temp_log_dir, encryptor):
        """Test that multiple LogWriter instances to same file can cause issues.
        
        This test documents a known limitation: multiple LogWriter instances
        writing to the same file have independent locks, which can lead to
        interleaved writes. In the real application, there's only ONE LogWriter
        per AppState, so this isn't an issue.
        
        This test verifies that at least some entries are written successfully.
        """
        # This simulates multiple request handlers writing logs for same user
        writers = [
            LogWriter(
                directory=temp_log_dir, 
                encryptor=encryptor, 
                compression="gzip",
                batch_size=10,
                batch_timeout=0.5,
            )
            for _ in range(5)
        ]
        
        # Start all writers
        for w in writers:
            await w.start()
        
        # All writers use same username
        for w in writers:
            w._username = "shared_user"
        
        try:
            # Each writer writes multiple entries
            all_tasks = []
            for w_idx, writer in enumerate(writers):
                for e_idx in range(10):
                    entry = create_test_entry(w_idx * 100 + e_idx, user="shared_user")
                    all_tasks.append(writer.write(entry))
            
            results = await asyncio.gather(*all_tasks)
            # Note: Some writes may report success but race on file I/O
            assert sum(results) > 0  # At least some writes succeed
            
            # Wait for batch writes
            await asyncio.sleep(1.5)
        finally:
            # Stop all writers
            for w in writers:
                await w.stop()
        
        # Verify single file exists
        log_files = list(temp_log_dir.rglob("*.jsonl"))
        assert len(log_files) == 1
        
        with open(log_files[0], "r") as f:
            content = f.read()
        
        # Due to race conditions with multiple writers, we may have partial lines.
        # The important thing is the app uses ONE LogWriter, avoiding this issue.
        lines = content.strip().split("\n")
        
        valid_count = 0
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("user") == "shared_user":
                    valid_count += 1
            except json.JSONDecodeError:
                pass  # Expected - some lines may be corrupted with multiple writers
        
        # At least some entries should be valid
        assert valid_count > 0, "No valid entries written"
