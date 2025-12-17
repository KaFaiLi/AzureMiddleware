"""Test async batch logging with queue."""

import asyncio
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from azure_middleware.logging.encryption import FieldEncryptor
from azure_middleware.logging.writer import LogWriter, LogEntry, TokenUsage


@pytest.fixture
def encryptor():
    """Create a test encryptor."""
    key = b"12345678901234567890123456789012"  # 32 bytes
    return FieldEncryptor(key)


@pytest.fixture
async def log_writer(encryptor):
    """Create and start a test log writer."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = LogWriter(
            directory=tmpdir,
            encryptor=encryptor,
            compression="none",
            batch_size=5,
            batch_timeout=0.5,
        )
        await writer.start()
        yield writer
        await writer.stop()


@pytest.mark.asyncio
async def test_batch_write_multiple_entries(log_writer):
    """Test that multiple entries are batched together."""
    # Create multiple log entries
    entries = []
    for i in range(10):
        entry = LogEntry(
            timestamp=datetime.now(timezone.utc),
            endpoint="/test",
            deployment="gpt-4",
            method="POST",
            tokens=TokenUsage(prompt=10, completion=20, total=30),
            cost_eur=0.01 * i,
            cumulative_cost_eur=0.01 * (i + 1) * (i + 2) / 2,
        )
        entries.append(entry)
        await log_writer.write(entry)
    
    # Wait for batch writes to complete
    await asyncio.sleep(1.5)
    
    # Verify all entries were written
    log_path = log_writer._get_log_path(entries[0].timestamp)
    assert log_path.exists(), "Log file should exist"
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    assert len(lines) == 10, f"Expected 10 log entries, got {len(lines)}"
    
    # Verify each entry is valid JSON
    for line in lines:
        data = json.loads(line)
        assert "timestamp" in data
        assert "endpoint" in data
        assert data["endpoint"] == "/test"


@pytest.mark.asyncio
async def test_batch_timeout_flush(log_writer):
    """Test that partial batches are flushed after timeout."""
    # Write only 2 entries (less than batch_size of 5)
    entry1 = LogEntry(
        timestamp=datetime.now(timezone.utc),
        endpoint="/test1",
        deployment="gpt-4",
    )
    entry2 = LogEntry(
        timestamp=datetime.now(timezone.utc),
        endpoint="/test2",
        deployment="gpt-4",
    )
    
    await log_writer.write(entry1)
    await log_writer.write(entry2)
    
    # Wait for timeout to trigger flush (batch_timeout = 0.5s + margin)
    await asyncio.sleep(1.0)
    
    # Verify entries were written despite not reaching batch_size
    log_path = log_writer._get_log_path(entry1.timestamp)
    assert log_path.exists(), "Log file should exist after timeout"
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    assert len(lines) == 2, f"Expected 2 log entries, got {len(lines)}"


@pytest.mark.asyncio
async def test_concurrent_writes(log_writer):
    """Test concurrent writes from multiple coroutines."""
    async def write_entries(prefix: str, count: int):
        for i in range(count):
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc),
                endpoint=f"/{prefix}-{i}",
                deployment="gpt-4",
                cost_eur=0.01,
            )
            await log_writer.write(entry)
    
    # Launch multiple concurrent writers
    await asyncio.gather(
        write_entries("task1", 10),
        write_entries("task2", 10),
        write_entries("task3", 10),
    )
    
    # Wait for all batches to complete
    await asyncio.sleep(1.5)
    
    # Verify all entries were written
    log_path = log_writer._get_log_path(datetime.now(timezone.utc))
    assert log_path.exists(), "Log file should exist"
    
    with open(log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    assert len(lines) == 30, f"Expected 30 log entries, got {len(lines)}"
    
    # Verify all entries are unique and valid
    endpoints = set()
    for line in lines:
        data = json.loads(line)
        endpoints.add(data["endpoint"])
    
    assert len(endpoints) == 30, "All entries should be unique"


@pytest.mark.asyncio
async def test_shutdown_flushes_queue(encryptor):
    """Test that shutdown flushes remaining entries in queue."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = LogWriter(
            directory=tmpdir,
            encryptor=encryptor,
            compression="none",
            batch_size=100,  # Large batch size
            batch_timeout=10.0,  # Long timeout
        )
        await writer.start()
        
        # Write some entries
        entries = []
        for i in range(5):
            entry = LogEntry(
                timestamp=datetime.now(timezone.utc),
                endpoint=f"/test-{i}",
                deployment="gpt-4",
            )
            entries.append(entry)
            await writer.write(entry)
        
        # Immediately stop (should flush queue)
        await writer.stop()
        
        # Verify entries were written
        log_path = writer._get_log_path(entries[0].timestamp)
        assert log_path.exists(), "Log file should exist after shutdown"
        
        with open(log_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        
        assert len(lines) == 5, f"Expected 5 log entries, got {len(lines)}"


@pytest.mark.asyncio
async def test_batch_grouping_by_date(encryptor):
    """Test that entries are grouped by date when writing batches."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = LogWriter(
            directory=tmpdir,
            encryptor=encryptor,
            compression="none",
            batch_size=10,
            batch_timeout=0.5,
        )
        await writer.start()
        
        # Create entries with different dates (simulate day rollover)
        from datetime import timedelta
        
        today = datetime.now(timezone.utc)
        yesterday = today - timedelta(days=1)
        
        # Write entries for yesterday
        for i in range(3):
            entry = LogEntry(
                timestamp=yesterday,
                endpoint=f"/yesterday-{i}",
                deployment="gpt-4",
            )
            await writer.write(entry)
        
        # Write entries for today
        for i in range(3):
            entry = LogEntry(
                timestamp=today,
                endpoint=f"/today-{i}",
                deployment="gpt-4",
            )
            await writer.write(entry)
        
        # Wait for batch writes
        await asyncio.sleep(1.5)
        
        # Stop writer
        await writer.stop()
        
        # Verify separate log files exist
        yesterday_path = writer._get_log_path(yesterday)
        today_path = writer._get_log_path(today)
        
        assert yesterday_path.exists(), "Yesterday's log file should exist"
        assert today_path.exists(), "Today's log file should exist"
        
        # Verify entry counts
        with open(yesterday_path, "r", encoding="utf-8") as f:
            yesterday_lines = f.readlines()
        with open(today_path, "r", encoding="utf-8") as f:
            today_lines = f.readlines()
        
        assert len(yesterday_lines) == 3, f"Expected 3 entries for yesterday, got {len(yesterday_lines)}"
        assert len(today_lines) == 3, f"Expected 3 entries for today, got {len(today_lines)}"
