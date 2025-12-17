"""Async JSONL log writer with encryption support."""

import asyncio
import getpass
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Any

from azure_middleware.logging.encryption import FieldEncryptor


logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """Token counts from response."""

    prompt: int = 0
    completion: int = 0
    total: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert to dictionary."""
        return {
            "prompt": self.prompt,
            "completion": self.completion,
            "total": self.total,
        }


@dataclass
class LogEntry:
    """JSONL log entry data."""

    # Plaintext metadata
    timestamp: datetime
    endpoint: str
    deployment: str
    method: str = "POST"

    # Data to encrypt
    request: dict | None = None
    response: dict | None = None

    # Cost tracking (plaintext)
    tokens: TokenUsage | None = None
    cost_eur: float = 0.0
    cumulative_cost_eur: float = 0.0

    # Performance & status
    duration_ms: int = 0
    stream: bool = False
    status_code: int = 200
    error: str | None = None

    # Set automatically
    user: str = field(default_factory=lambda: get_windows_username())


def get_windows_username() -> str:
    """Get the current Windows username.

    Returns:
        Windows username or 'unknown' if detection fails
    """
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


class LogWriter:
    """Async JSONL log writer with encryption and best-effort semantics.

    Logs are written to: {directory}/YYYYMMDD/{username}_YYYYMMDD.jsonl
    """

    def __init__(
        self,
        directory: str | Path,
        encryptor: FieldEncryptor,
        compression: str = "gzip",
        batch_size: int = 10,
        batch_timeout: float = 1.0,
    ) -> None:
        """Initialize the log writer.

        Args:
            directory: Base directory for log files
            encryptor: FieldEncryptor instance for request/response encryption
            compression: Compression mode ("gzip" or "none") - applied by encryptor
            batch_size: Maximum number of log entries per batch write
            batch_timeout: Maximum time (seconds) to wait before flushing partial batch
        """
        self._directory = Path(directory)
        self._encryptor = encryptor
        self._compression = compression
        self._write_lock = asyncio.Lock()
        self._username = get_windows_username()
        
        # Async queue and batch configuration
        self._queue: asyncio.Queue[LogEntry | None] = asyncio.Queue()
        self._batch_size = batch_size
        self._batch_timeout = batch_timeout
        self._background_task: asyncio.Task | None = None
        self._shutdown = False

    def _get_log_path(self, dt: datetime) -> Path:
        """Get the log file path for a given datetime.

        Args:
            dt: Datetime to get path for

        Returns:
            Path to the log file
        """
        date_str = dt.strftime("%Y%m%d")
        date_dir = self._directory / date_str
        filename = f"{self._username}_{date_str}.jsonl"
        return date_dir / filename

    def _serialize_entry(self, entry: LogEntry) -> str:
        """Serialize a log entry to JSONL format.

        Args:
            entry: LogEntry to serialize

        Returns:
            JSON string for one JSONL line
        """
        data: dict[str, Any] = {
            "timestamp": entry.timestamp.isoformat(),
            "user": entry.user,
            "endpoint": entry.endpoint,
            "method": entry.method,
            "deployment": entry.deployment,
        }

        # Encrypt request if present
        if entry.request is not None:
            data["request_encrypted"] = self._encryptor.encrypt(entry.request)
        else:
            data["request_encrypted"] = None

        # Encrypt response if present (None for embeddings)
        if entry.response is not None:
            data["response_encrypted"] = self._encryptor.encrypt(entry.response)
        else:
            data["response_encrypted"] = None

        # Add plaintext fields
        if entry.tokens:
            data["tokens"] = entry.tokens.to_dict()
        else:
            data["tokens"] = None

        data["cost_eur"] = entry.cost_eur
        data["cumulative_cost_eur"] = entry.cumulative_cost_eur
        data["duration_ms"] = entry.duration_ms
        data["stream"] = entry.stream
        data["status_code"] = entry.status_code
        data["error"] = entry.error

        return json.dumps(data, separators=(",", ":"))

    async def write(self, entry: LogEntry) -> bool:
        """Write a log entry asynchronously via queue (best-effort).

        This method enqueues the entry and returns immediately,
        decoupling request latency from disk I/O.

        Args:
            entry: LogEntry to write

        Returns:
            True (always succeeds unless queue is full)
        """
        try:
            # Non-blocking enqueue (returns immediately)
            await self._queue.put(entry)
            return True
        except Exception as e:
            logger.warning(f"Failed to enqueue log entry: {e}")
            return False

    def _write_line(self, path: Path, line: str) -> None:
        """Write a line to a file (blocking, run in thread pool).

        Args:
            path: File path to write to
            line: Line to write
        """
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

    async def start(self) -> None:
        """Start the background log writer task.
        
        Should be called during application startup.
        """
        if self._background_task is None:
            self._shutdown = False
            self._background_task = asyncio.create_task(self._background_writer())
            logger.info(f"Log writer started (batch_size={self._batch_size}, timeout={self._batch_timeout}s)")

    async def stop(self) -> None:
        """Stop the background log writer task and flush pending entries.
        
        Should be called during application shutdown.
        """
        if self._background_task:
            self._shutdown = True
            # Send sentinel to wake up the worker
            await self._queue.put(None)
            # Wait for worker to finish
            await self._background_task
            self._background_task = None
            logger.info("Log writer stopped")

    async def _background_writer(self) -> None:
        """Background task that consumes queue and writes in batches."""
        logger.info("Background log writer task started")
        
        while not self._shutdown:
            try:
                batch = await self._collect_batch()
                if batch:
                    await self._write_batch(batch)
            except Exception as e:
                logger.error(f"Error in background writer: {e}", exc_info=True)
        
        # Final flush on shutdown
        await self._flush_remaining()
        logger.info("Background log writer task stopped")

    async def _collect_batch(self) -> list[LogEntry]:
        """Collect a batch of log entries from the queue.
        
        Returns:
            List of log entries (up to batch_size)
        """
        batch: list[LogEntry] = []
        
        try:
            # Wait for first entry (with timeout)
            entry = await asyncio.wait_for(
                self._queue.get(),
                timeout=self._batch_timeout
            )
            
            # Sentinel value for shutdown
            if entry is None:
                return batch
            
            batch.append(entry)
            
            # Collect additional entries up to batch_size (non-blocking)
            while len(batch) < self._batch_size:
                try:
                    entry = self._queue.get_nowait()
                    if entry is None:  # Sentinel
                        return batch
                    batch.append(entry)
                except asyncio.QueueEmpty:
                    break
        
        except asyncio.TimeoutError:
            # Timeout waiting for first entry, return empty batch
            pass
        
        return batch

    async def _write_batch(self, batch: list[LogEntry]) -> None:
        """Write a batch of log entries to disk.
        
        Groups entries by date and writes to appropriate files.
        
        Args:
            batch: List of log entries to write
        """
        if not batch:
            return
        
        # Group entries by date
        entries_by_date: dict[Path, list[str]] = {}
        
        for entry in batch:
            log_path = self._get_log_path(entry.timestamp)
            line = self._serialize_entry(entry) + "\n"
            
            if log_path not in entries_by_date:
                entries_by_date[log_path] = []
            entries_by_date[log_path].append(line)
        
        # Write batches to each file
        for log_path, lines in entries_by_date.items():
            try:
                # Ensure directory exists
                log_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Batch write with lock
                async with self._write_lock:
                    await asyncio.to_thread(self._write_lines, log_path, lines)
                
                logger.debug(f"Wrote {len(lines)} log entries to {log_path}")
            
            except Exception as e:
                logger.warning(f"Failed to write batch to {log_path}: {e}")

    def _write_lines(self, path: Path, lines: list[str]) -> None:
        """Write multiple lines to a file (blocking, run in thread pool).
        
        Args:
            path: File path to write to
            lines: Lines to write
        """
        with open(path, "a", encoding="utf-8") as f:
            f.writelines(lines)

    async def _flush_remaining(self) -> None:
        """Flush any remaining entries in the queue during shutdown."""
        remaining: list[LogEntry] = []
        
        while not self._queue.empty():
            try:
                entry = self._queue.get_nowait()
                if entry is not None:  # Skip sentinels
                    remaining.append(entry)
            except asyncio.QueueEmpty:
                break
        
        if remaining:
            logger.info(f"Flushing {len(remaining)} remaining log entries")
            await self._write_batch(remaining)

    def get_last_entry_for_date(self, target_date: date) -> LogEntry | None:
        """Read the last log entry for a specific date.

        Used for cost recovery on startup.

        Args:
            target_date: Date to read last entry for

        Returns:
            Last LogEntry for the date, or None if no logs exist
        """
        # Construct path for the date
        date_str = target_date.strftime("%Y%m%d")
        date_dir = self._directory / date_str
        log_file = date_dir / f"{self._username}_{date_str}.jsonl"

        if not log_file.exists():
            return None

        try:
            # Read last line efficiently
            last_line = self._read_last_line(log_file)
            if not last_line:
                return None

            # Parse JSON
            data = json.loads(last_line)

            # Convert to LogEntry (without decrypting)
            tokens = None
            if data.get("tokens"):
                tokens = TokenUsage(
                    prompt=data["tokens"].get("prompt", 0),
                    completion=data["tokens"].get("completion", 0),
                    total=data["tokens"].get("total", 0),
                )

            return LogEntry(
                timestamp=datetime.fromisoformat(data["timestamp"]),
                user=data.get("user", self._username),
                endpoint=data.get("endpoint", ""),
                method=data.get("method", "POST"),
                deployment=data.get("deployment", ""),
                tokens=tokens,
                cost_eur=data.get("cost_eur", 0.0),
                cumulative_cost_eur=data.get("cumulative_cost_eur", 0.0),
                duration_ms=data.get("duration_ms", 0),
                stream=data.get("stream", False),
                status_code=data.get("status_code", 200),
                error=data.get("error"),
            )

        except Exception as e:
            logger.warning(f"Failed to read last log entry: {e}")
            return None

    def _read_last_line(self, path: Path) -> str | None:
        """Read the last non-empty line from a file.

        Args:
            path: File to read from

        Returns:
            Last non-empty line, or None if file is empty
        """
        try:
            with open(path, "rb") as f:
                # Seek to end
                f.seek(0, 2)
                file_size = f.tell()

                if file_size == 0:
                    return None

                # Read backwards to find last line
                buffer = b""
                position = file_size

                while position > 0:
                    # Read chunk backwards
                    chunk_size = min(1024, position)
                    position -= chunk_size
                    f.seek(position)
                    chunk = f.read(chunk_size)
                    buffer = chunk + buffer

                    # Check for newline (excluding trailing newline)
                    lines = buffer.rstrip(b"\n\r").split(b"\n")
                    if len(lines) > 1:
                        return lines[-1].decode("utf-8")

                # File has only one line
                return buffer.rstrip(b"\n\r").decode("utf-8") or None

        except Exception:
            return None
