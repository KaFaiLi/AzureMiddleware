"""Pydantic models for API error responses.

These models are used for OpenAPI documentation of error responses.
Request/response bodies are passed through directly without validation.
"""

from pydantic import BaseModel


class CostLimitError(BaseModel):
    """Cost limit exceeded error response (HTTP 429)."""
    
    error: str = "daily_cost_limit_exceeded"
    message: str
    current_cost_eur: float
    limit_eur: float
    retry_after_seconds: int

