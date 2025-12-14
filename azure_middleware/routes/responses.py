"""Responses API endpoint for Azure OpenAI proxy."""

import json
import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import Response, JSONResponse

from azure_middleware.routes.chat import (
    filter_request_headers,
    build_azure_url,
    get_app_state,
    PRESERVE_RESPONSE_HEADERS,
)
from azure_middleware.cost.tracker import CostCapExceededError
from azure_middleware.cost.calculator import calculate_cost, extract_token_counts
from azure_middleware.logging.writer import LogEntry, TokenUsage
from azure_middleware.routes.models import CostLimitError


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Responses API"])


@router.post(
    "/openai/deployments/{deployment}/responses",
    summary="Responses API",
    description="Create a response using the Responses API. Fully compatible with Azure OpenAI API.",
    responses={
        429: {"model": CostLimitError, "description": "Daily cost limit exceeded"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "required": ["input"],
                        "properties": {
                            "input": {
                                "description": "The input for the response. Can be a string or structured input.",
                                "oneOf": [
                                    {"type": "string"},
                                    {"type": "array"},
                                ],
                            },
                            "max_output_tokens": {"type": "integer", "description": "Maximum number of output tokens."},
                            "temperature": {"type": "number", "description": "Sampling temperature."},
                            "instructions": {"type": "string", "description": "System instructions for the model."},
                        },
                    },
                    "example": {
                        "input": "What is the capital of France?",
                        "max_output_tokens": 100
                    },
                },
            },
        },
    },
)
async def create_response(
    request: Request,
    deployment: str,
):
    """Proxy Responses API request to Azure OpenAI.

    The Responses API is a newer Azure OpenAI feature that provides
    enhanced response handling.
    Note: Request body is passed through directly without Pydantic validation.
    """
    state = await get_app_state(request)
    config = state.config
    cost_tracker = state.cost_tracker
    log_writer = state.log_writer
    auth_provider = state.auth_provider

    start_time = datetime.now(timezone.utc)

    # Check cost cap before processing
    try:
        await cost_tracker.check_cap()
    except CostCapExceededError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "daily_cost_limit_exceeded",
                "message": f"Daily cost limit exceeded. Current: €{e.current_cost:.4f}, Limit: €{e.cap:.2f}. Resets at UTC midnight.",
                "current_cost_eur": e.current_cost,
                "limit_eur": e.cap,
                "retry_after_seconds": e.seconds_until_reset,
            },
            headers={"Retry-After": str(e.seconds_until_reset)},
        )

    # Read raw body and pass through directly - no Pydantic validation
    raw_body = await request.body()
    try:
        request_data = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_json", "message": "Request body must be valid JSON"},
        )

    # Build Azure URL
    query_params = dict(request.query_params)
    azure_url = build_azure_url(config, deployment, "responses", query_params)

    # Prepare headers
    headers = filter_request_headers(dict(request.headers))
    auth_headers = await auth_provider.get_auth_header()
    headers.update(auth_headers)
    headers["Content-Type"] = "application/json"

    # Create HTTP client and forward request
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
        follow_redirects=True,
    ) as client:
        try:
            response = await client.post(azure_url, content=raw_body, headers=headers)
        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "azure_unreachable",
                    "message": f"Cannot connect to Azure OpenAI at {config.azure.endpoint}.",
                },
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"error": "azure_timeout", "message": "Request to Azure OpenAI timed out."},
            )

    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

    # Parse response for cost calculation
    response_data = None
    tokens = None
    cost_result = None

    if response.status_code == 200:
        try:
            response_data = response.json()
            # Responses API may have different usage format, try to extract tokens
            prompt_tokens, completion_tokens = extract_token_counts(response_data)
            cost_result = calculate_cost(config, deployment, prompt_tokens, completion_tokens)
            tokens = TokenUsage(
                prompt=prompt_tokens,
                completion=completion_tokens,
                total=prompt_tokens + completion_tokens,
            )

            # Update cost tracker
            cumulative_cost = await cost_tracker.add_cost(cost_result.total_cost_eur)
        except Exception as e:
            logger.warning(f"Failed to process responses API response for cost tracking: {e}")
            cumulative_cost = await cost_tracker.get_current_cost()
    else:
        cumulative_cost = await cost_tracker.get_current_cost()

    # Log entry
    log_entry = LogEntry(
        timestamp=start_time,
        endpoint=f"/openai/deployments/{deployment}/responses",
        deployment=deployment,
        request=request_data,
        response=response_data,
        tokens=tokens,
        cost_eur=cost_result.total_cost_eur if cost_result else 0.0,
        cumulative_cost_eur=cumulative_cost,
        duration_ms=duration_ms,
        stream=False,
        status_code=response.status_code,
        error=None if response.status_code == 200 else f"HTTP {response.status_code}",
    )

    # Write log asynchronously
    import asyncio
    asyncio.create_task(log_writer.write(log_entry))

    # Build response headers
    response_headers = {}
    for header in PRESERVE_RESPONSE_HEADERS:
        if header in response.headers:
            response_headers[header] = response.headers[header]

    return Response(
        content=response.content,
        status_code=response.status_code,
        headers=response_headers,
        media_type=response.headers.get("content-type", "application/json"),
    )
