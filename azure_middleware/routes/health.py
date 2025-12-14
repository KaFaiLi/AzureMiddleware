"""Health and metrics endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from azure_middleware.cost.tracker import CostTracker
from azure_middleware.dependencies import get_cost_tracker


router = APIRouter(tags=["Health & Metrics"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    timestamp: str


class MetricsResponse(BaseModel):
    """Cost metrics response."""

    daily_cost_eur: float
    daily_cap_eur: float
    date: str
    percentage_used: float


def get_health_response() -> HealthResponse:
    """Create health response.

    Returns:
        HealthResponse with current timestamp
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns 200 OK if server is running. No authentication required.",
)
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns server health status. No authentication required.
    """
    return get_health_response()


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Cost metrics",
    description="Returns current daily cost and cap. No authentication required.",
)
async def get_metrics(cost_tracker: CostTracker = Depends(get_cost_tracker)) -> MetricsResponse:
    """Get current cost metrics.

    Returns daily cost, cap, and usage percentage.
    No authentication required.
    """
    current_cost = await cost_tracker.get_current_cost()
    cap = cost_tracker.daily_cap
    percentage = (current_cost / cap * 100) if cap > 0 else 0.0

    return MetricsResponse(
        daily_cost_eur=round(current_cost, 4),
        daily_cap_eur=cap,
        date=datetime.now(timezone.utc).date().isoformat(),
        percentage_used=round(percentage, 2),
    )
