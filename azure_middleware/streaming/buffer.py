"""SSE stream buffer for accumulating streaming responses."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class StreamBuffer:
    """Accumulates SSE chunks for logging.

    Parses Server-Sent Events format and reconstructs the complete response.
    """

    chunks: list[bytes] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _content_parts: list[str] = field(default_factory=list)
    _usage: dict[str, int] | None = field(default=None)
    _model: str = field(default="")
    _id: str = field(default="")
    _finish_reason: str | None = field(default=None)

    def append(self, chunk: bytes) -> None:
        """Append a chunk to the buffer.

        Args:
            chunk: Raw bytes chunk from SSE stream
        """
        self.chunks.append(chunk)
        self._parse_chunk(chunk)

    def _parse_chunk(self, chunk: bytes) -> None:
        """Parse SSE chunk and extract content.

        Args:
            chunk: Raw SSE chunk bytes
        """
        try:
            text = chunk.decode("utf-8")
            for line in text.split("\n"):
                if line.startswith("data: ") and line[6:] != "[DONE]":
                    try:
                        data = json.loads(line[6:])
                        self._process_event(data)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass

    def _process_event(self, event: dict[str, Any]) -> None:
        """Process a parsed SSE event.

        Args:
            event: Parsed JSON event data
        """
        # Extract metadata from first event
        if not self._id and "id" in event:
            self._id = event["id"]
        if not self._model and "model" in event:
            self._model = event["model"]

        # Extract content deltas
        choices = event.get("choices", [])
        for choice in choices:
            delta = choice.get("delta", {})
            content = delta.get("content", "")
            if content:
                self._content_parts.append(content)

            # Track finish reason
            if choice.get("finish_reason"):
                self._finish_reason = choice["finish_reason"]

        # Extract usage from final event
        if "usage" in event and event["usage"]:
            self._usage = event["usage"]

    def get_complete_response(self) -> bytes:
        """Get all raw bytes combined.

        Returns:
            Complete raw response bytes
        """
        return b"".join(self.chunks)

    def get_reconstructed_content(self) -> str:
        """Get reconstructed content from all chunks.

        Returns:
            Complete assistant message content
        """
        return "".join(self._content_parts)

    def get_usage(self) -> dict[str, int]:
        """Get token usage from stream.

        Returns:
            Usage dict with prompt_tokens, completion_tokens, total_tokens
        """
        if self._usage:
            return self._usage
        # Return zeros if usage not available (some models don't include it)
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def get_reconstructed_response(self) -> dict[str, Any]:
        """Reconstruct a complete response object from streamed chunks.

        Returns:
            Dict matching non-streaming response format
        """
        content = self.get_reconstructed_content()
        usage = self.get_usage()

        return {
            "id": self._id,
            "object": "chat.completion",
            "created": int(self.started_at.timestamp()),
            "model": self._model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": self._finish_reason or "stop",
                }
            ],
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    def parse_sse_events(self) -> list[dict]:
        """Parse SSE format into list of data payloads.

        Returns:
            List of parsed JSON event objects
        """
        raw = self.get_complete_response().decode("utf-8")
        events = []
        for line in raw.split("\n"):
            if line.startswith("data: ") and line[6:] != "[DONE]":
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
        return events

    @property
    def is_complete(self) -> bool:
        """Check if stream is complete.

        Returns:
            True if finish_reason has been received
        """
        return self._finish_reason is not None

    @property
    def duration_ms(self) -> int:
        """Get stream duration in milliseconds.

        Returns:
            Duration since stream started
        """
        delta = datetime.now(timezone.utc) - self.started_at
        return int(delta.total_seconds() * 1000)
