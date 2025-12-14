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
    ) -> None:
        """Initialize the log writer.

        Args:
            directory: Base directory for log files
            encryptor: FieldEncryptor instance for request/response encryption
            compression: Compression mode ("gzip" or "none") - applied by encryptor
        """
        self._directory = Path(directory)
        self._encryptor = encryptor
        self._compression = compression
        self._write_lock = asyncio.Lock()
        self._username = get_windows_username()

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
        """Write a log entry asynchronously (best-effort).

        This method will not raise exceptions - logging failures are
        logged to the standard logger but do not block request processing.

        Args:
            entry: LogEntry to write

        Returns:
            True if write succeeded, False otherwise
        """
        try:
            log_path = self._get_log_path(entry.timestamp)

            # Ensure directory exists
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Serialize entry
            line = self._serialize_entry(entry) + "\n"

            # Write with lock to prevent interleaved writes
            async with self._write_lock:
                # Use asyncio to run blocking I/O in thread pool
                await asyncio.to_thread(self._write_line, log_path, line)

            return True

        except Exception as e:
            # Best-effort: log error but don't raise
            logger.warning(f"Failed to write log entry: {e}")
            return False

    def _write_line(self, path: Path, line: str) -> None:
        """Write a line to a file (blocking, run in thread pool).

        Args:
            path: File path to write to
            line: Line to write
        """
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)

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
