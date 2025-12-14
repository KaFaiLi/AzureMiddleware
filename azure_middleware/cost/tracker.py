"""Daily cost tracker with async lock and persistence."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from azure_middleware.logging.writer import LogWriter


logger = logging.getLogger(__name__)


class CostCapExceededError(Exception):
    """Raised when daily cost cap is exceeded."""

    def __init__(
        self,
        current_cost: float,
        cap: float,
        seconds_until_reset: int,
    ) -> None:
        self.current_cost = current_cost
        self.cap = cap
        self.seconds_until_reset = seconds_until_reset
        super().__init__(
            f"Daily cost cap exceeded: €{current_cost:.4f} >= €{cap:.2f}"
        )


@dataclass
class CostState:
    """Mutable cost tracking state."""

    cumulative_cost_eur: float = 0.0
    current_date: date | None = None

    def reset(self, new_date: date) -> None:
        """Reset for new day.

        Args:
            new_date: The new date to set
        """
        self.cumulative_cost_eur = 0.0
        self.current_date = new_date


class CostTracker:
    """Async-safe daily cost tracker.

    Tracks cumulative daily cost with:
    - Thread-safe updates using asyncio.Lock
    - Lazy midnight reset on first request of new day
    - Persistence via log files (reads last entry on startup)
    - Pre-request cost cap enforcement
    """

    def __init__(self, daily_cap_eur: float, log_writer: "LogWriter | None" = None) -> None:
        """Initialize the cost tracker.

        Args:
            daily_cap_eur: Daily spending cap in EUR
            log_writer: Optional LogWriter for reading persisted state
        """
        self._daily_cap_eur = daily_cap_eur
        self._log_writer = log_writer
        self._state = CostState()
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize cost state from persisted logs.

        Should be called once at startup.
        """
        async with self._lock:
            if self._initialized:
                return

            today = datetime.now(timezone.utc).date()
            self._state.current_date = today

            # Try to recover state from log file
            if self._log_writer:
                last_entry = self._log_writer.get_last_entry_for_date(today)
                if last_entry:
                    self._state.cumulative_cost_eur = last_entry.cumulative_cost_eur
                    logger.info(
                        f"Recovered cost state: €{self._state.cumulative_cost_eur:.4f}"
                    )
                else:
                    logger.info("No existing logs for today, starting at €0.00")
            else:
                logger.info("No log writer configured, starting at €0.00")

            self._initialized = True

    async def check_cap(self) -> None:
        """Check if cost cap is exceeded (pre-request).

        Call this before processing each request.

        Raises:
            CostCapExceededError: If daily cap is exceeded
        """
        async with self._lock:
            # Check for day rollover
            today = datetime.now(timezone.utc).date()
            if self._state.current_date != today:
                logger.info(f"New day detected, resetting cost from €{self._state.cumulative_cost_eur:.4f}")
                self._state.reset(today)

            # Check cap
            if self._state.cumulative_cost_eur >= self._daily_cap_eur:
                raise CostCapExceededError(
                    current_cost=self._state.cumulative_cost_eur,
                    cap=self._daily_cap_eur,
                    seconds_until_reset=self._seconds_until_midnight(),
                )

    async def add_cost(self, cost_eur: float) -> float:
        """Add cost for a completed request.

        Args:
            cost_eur: Cost in EUR to add

        Returns:
            New cumulative cost
        """
        async with self._lock:
            # Check for day rollover (in case request spanned midnight)
            today = datetime.now(timezone.utc).date()
            if self._state.current_date != today:
                self._state.reset(today)

            self._state.cumulative_cost_eur += cost_eur
            return self._state.cumulative_cost_eur

    async def get_current_cost(self) -> float:
        """Get current cumulative cost.

        Returns:
            Current cumulative cost in EUR
        """
        async with self._lock:
            # Check for day rollover
            today = datetime.now(timezone.utc).date()
            if self._state.current_date != today:
                self._state.reset(today)
            return self._state.cumulative_cost_eur

    @property
    def daily_cap(self) -> float:
        """Get the daily cap.

        Returns:
            Daily cap in EUR
        """
        return self._daily_cap_eur

    def _seconds_until_midnight(self) -> int:
        """Calculate seconds until UTC midnight.

        Returns:
            Seconds until next UTC midnight
        """
        now = datetime.now(timezone.utc)
        tomorrow = now.date() + timedelta(days=1)
        midnight = datetime.combine(tomorrow, datetime.min.time(), tzinfo=timezone.utc)
        delta = midnight - now
        return int(delta.total_seconds())

    def get_retry_after(self) -> int:
        """Get Retry-After header value.

        Returns:
            Seconds until cost resets (midnight UTC)
        """
        return self._seconds_until_midnight()
