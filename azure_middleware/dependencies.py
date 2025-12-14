"""Dependency injection utilities for FastAPI routes."""

from fastapi import Request

from azure_middleware.config import AppConfig
from azure_middleware.cost.tracker import CostTracker


async def get_config(request: Request) -> AppConfig:
    """Get application config from state.

    Args:
        request: FastAPI request object

    Returns:
        AppConfig instance from app state
    """
    return request.app.state.app_state.config


async def get_cost_tracker(request: Request) -> CostTracker:
    """Get cost tracker from application state.

    This is the standard dependency function for routes that need
    access to the cost tracker.

    Args:
        request: FastAPI request object

    Returns:
        CostTracker instance from app state
    """
    return request.app.state.app_state.cost_tracker
