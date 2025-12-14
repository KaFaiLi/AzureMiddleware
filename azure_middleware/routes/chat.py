"""Chat completions endpoint for Azure OpenAI proxy."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Request, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from azure_middleware.config import AppConfig
from azure_middleware.cost.tracker import CostTracker, CostCapExceededError
from azure_middleware.cost.calculator import calculate_cost, extract_token_counts
from azure_middleware.logging.writer import LogWriter, LogEntry, TokenUsage
from azure_middleware.streaming.buffer import StreamBuffer
from azure_middleware.routes.models import CostLimitError


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat Completions"])

# Headers to filter out when forwarding requests
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

# Headers to preserve from Azure response
PRESERVE_RESPONSE_HEADERS = {
    "x-request-id",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "openai-model",
    "openai-processing-ms",
}


def filter_request_headers(headers: dict[str, str]) -> dict[str, str]:
    """Filter hop-by-hop headers from request.

    Args:
        headers: Original request headers

    Returns:
        Filtered headers safe for forwarding
    """
    return {
        k: v for k, v in headers.items()
        if k.lower() not in HOP_BY_HOP_HEADERS
    }


def build_azure_url(config: AppConfig, deployment: str, endpoint_path: str, query_params: dict[str, str]) -> str:
    """Build the Azure OpenAI URL for forwarding.

    Args:
        config: Application configuration
        deployment: Deployment name from path
        endpoint_path: The endpoint path (e.g., "chat/completions")
        query_params: Query parameters from original request

    Returns:
        Complete Azure OpenAI URL
    """
    # Use api-version from query params or config
    api_version = query_params.get("api-version", config.azure.api_version)

    base_url = f"{config.azure.endpoint}/openai/deployments/{deployment}/{endpoint_path}"
    return f"{base_url}?api-version={api_version}"


def is_streaming_request(body: bytes) -> bool:
    """Check if request body indicates streaming.

    Args:
        body: Request body bytes

    Returns:
        True if stream=true in request
    """
    try:
        data = json.loads(body)
        return data.get("stream", False) is True
    except (json.JSONDecodeError, AttributeError):
        return False


async def get_app_state(request: Request):
    """Get application state from request.

    Args:
        request: FastAPI request

    Returns:
        AppState instance
    """
    return request.app.state.app_state


@router.post(
    "/openai/deployments/{deployment}/chat/completions",
    summary="Chat Completions",
    description="Create a chat completion. Supports streaming via stream: true.",
    responses={
        429: {"model": CostLimitError, "description": "Daily cost limit exceeded"},
    },
)
async def chat_completions(
    request: Request,
    deployment: str,
):
    """Proxy chat completion request to Azure OpenAI.

    Handles:
    - Non-streaming and streaming requests
    - Cost tracking and enforcement
    - Request/response logging
    - Error forwarding
    
    Note: Request body is passed through directly to Azure without Pydantic validation
    to ensure all fields (tools, response_format, etc.) are forwarded correctly.
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

    # Check if streaming
    is_streaming = request_data.get("stream", False) is True

    # Build Azure URL
    query_params = dict(request.query_params)
    azure_url = build_azure_url(config, deployment, "chat/completions", query_params)

    # Prepare headers
    headers = filter_request_headers(dict(request.headers))
    auth_headers = await auth_provider.get_auth_header()
    headers.update(auth_headers)
    headers["Content-Type"] = "application/json"

    # Create HTTP client
    # For streaming, we need to create the client inside the generator to keep it alive
    # For non-streaming, we can use the context manager pattern
    if is_streaming:
        try:
            return await handle_streaming_request(
                url=azure_url,
                headers=headers,
                body=raw_body,
                request_data=request_data,
                deployment=deployment,
                config=config,
                cost_tracker=cost_tracker,
                log_writer=log_writer,
                start_time=start_time,
                endpoint=f"/openai/deployments/{deployment}/chat/completions",
            )
        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "azure_unreachable",
                    "message": f"Cannot connect to Azure OpenAI at {config.azure.endpoint}. Check your network and Azure configuration.",
                },
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "error": "azure_timeout",
                    "message": "Request to Azure OpenAI timed out. Try again or reduce request size.",
                },
            )
    
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
        follow_redirects=True,
    ) as client:
        try:
            return await handle_non_streaming_request(
                client=client,
                url=azure_url,
                headers=headers,
                body=raw_body,
                request_data=request_data,
                deployment=deployment,
                config=config,
                cost_tracker=cost_tracker,
                log_writer=log_writer,
                start_time=start_time,
                endpoint=f"/openai/deployments/{deployment}/chat/completions",
            )

        except httpx.ConnectError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "error": "azure_unreachable",
                    "message": f"Cannot connect to Azure OpenAI at {config.azure.endpoint}. Check your network and Azure configuration.",
                },
            )
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={
                    "error": "azure_timeout",
                    "message": "Request to Azure OpenAI timed out. Try again or reduce request size.",
                },
            )


async def handle_non_streaming_request(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    body: bytes,
    request_data: dict,
    deployment: str,
    config: AppConfig,
    cost_tracker: CostTracker,
    log_writer: LogWriter,
    start_time: datetime,
    endpoint: str,
) -> Response:
    """Handle non-streaming chat completion request.

    Args:
        client: HTTP client
        url: Azure URL
        headers: Request headers
        body: Request body
        request_data: Parsed request data
        deployment: Deployment name
        config: App configuration
        cost_tracker: Cost tracker
        log_writer: Log writer
        start_time: Request start time
        endpoint: Endpoint path

    Returns:
        FastAPI Response
    """
    response = await client.post(url, content=body, headers=headers)

    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

    # Parse response for cost calculation
    response_data = None
    tokens = None
    cost_result = None

    if response.status_code == 200:
        try:
            response_data = response.json()
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
            logger.warning(f"Failed to process response for cost tracking: {e}")
            cumulative_cost = await cost_tracker.get_current_cost()
    else:
        cumulative_cost = await cost_tracker.get_current_cost()

    # Log entry (best-effort, non-blocking)
    log_entry = LogEntry(
        timestamp=start_time,
        endpoint=endpoint,
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

    # Write log asynchronously (don't await to avoid blocking response)
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


async def handle_streaming_request(
    url: str,
    headers: dict[str, str],
    body: bytes,
    request_data: dict,
    deployment: str,
    config: AppConfig,
    cost_tracker: CostTracker,
    log_writer: LogWriter,
    start_time: datetime,
    endpoint: str,
) -> StreamingResponse:
    """Handle streaming chat completion request.

    Args:
        url: Azure URL
        headers: Request headers
        body: Request body
        request_data: Parsed request data
        deployment: Deployment name
        config: App configuration
        cost_tracker: Cost tracker
        log_writer: Log writer
        start_time: Request start time
        endpoint: Endpoint path

    Returns:
        StreamingResponse
    """
    buffer = StreamBuffer()

    async def stream_generator():
        """Generate SSE chunks while buffering for logging."""
        nonlocal buffer

        # Create client inside generator to keep connection alive for entire stream
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
            follow_redirects=True,
        ) as client:
            try:
                async with client.stream("POST", url, content=body, headers=headers) as response:
                    if response.status_code != 200:
                        # For errors, read full response and yield
                        error_content = await response.aread()
                        yield error_content
                        return

                    async for chunk in response.aiter_bytes():
                        buffer.append(chunk)
                        yield chunk

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                # Log partial stream with error
                await log_streaming_response(
                    buffer=buffer,
                    request_data=request_data,
                    deployment=deployment,
                    config=config,
                    cost_tracker=cost_tracker,
                    log_writer=log_writer,
                    start_time=start_time,
                    endpoint=endpoint,
                    error=str(e),
                )
                raise

            # Log completed stream
            await log_streaming_response(
                buffer=buffer,
                request_data=request_data,
                deployment=deployment,
                config=config,
                cost_tracker=cost_tracker,
                log_writer=log_writer,
                start_time=start_time,
                endpoint=endpoint,
                error=None,
            )

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


async def log_streaming_response(
    buffer: StreamBuffer,
    request_data: dict,
    deployment: str,
    config: AppConfig,
    cost_tracker: CostTracker,
    log_writer: LogWriter,
    start_time: datetime,
    endpoint: str,
    error: str | None,
) -> None:
    """Log a streaming response after completion.

    Args:
        buffer: Stream buffer with accumulated chunks
        request_data: Original request data
        deployment: Deployment name
        config: App configuration
        cost_tracker: Cost tracker
        log_writer: Log writer
        start_time: Request start time
        endpoint: Endpoint path
        error: Error message if stream failed
    """
    duration_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

    # Reconstruct response from buffer
    response_data = buffer.get_reconstructed_response()
    usage = buffer.get_usage()

    # Calculate cost
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost_result = calculate_cost(config, deployment, prompt_tokens, completion_tokens)

    tokens = TokenUsage(
        prompt=prompt_tokens,
        completion=completion_tokens,
        total=prompt_tokens + completion_tokens,
    )

    # Update cost tracker
    cumulative_cost = await cost_tracker.add_cost(cost_result.total_cost_eur)

    # Create log entry
    log_entry = LogEntry(
        timestamp=start_time,
        endpoint=endpoint,
        deployment=deployment,
        request=request_data,
        response=response_data,
        tokens=tokens,
        cost_eur=cost_result.total_cost_eur,
        cumulative_cost_eur=cumulative_cost,
        duration_ms=duration_ms,
        stream=True,
        status_code=200 if not error else 500,
        error=error,
    )

    # Write log
    await log_writer.write(log_entry)


# Need to import JSONResponse for cost cap error
from fastapi.responses import JSONResponse
