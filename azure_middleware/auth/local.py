"""Local API key validation middleware."""

from fastapi import Request, HTTPException, status
from pydantic import SecretStr


def validate_local_api_key(request: Request, expected_key: SecretStr) -> bool:
    """Validate the local API key from request headers.

    Checks the 'api-key' header against the configured local API key.

    Args:
        request: FastAPI request object
        expected_key: Expected API key from configuration

    Returns:
        True if valid

    Raises:
        HTTPException: 401 if key is missing or invalid
    """
    api_key = request.headers.get("api-key")

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "missing_api_key",
                "message": "API key is required. Include 'api-key' header in your request.",
            },
        )

    if api_key != expected_key.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_api_key",
                "message": "Invalid API key. Check your 'api-key' header value.",
            },
        )

    return True


class LocalAPIKeyMiddleware:
    """Middleware for validating local API key on protected routes.

    Usage:
        @app.middleware("http")
        async def api_key_middleware(request: Request, call_next):
            middleware = LocalAPIKeyMiddleware(config.local.api_key)
            return await middleware(request, call_next)
    """

    # Routes that don't require authentication
    PUBLIC_ROUTES = {"/health", "/metrics", "/models", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, api_key: SecretStr) -> None:
        """Initialize with expected API key.

        Args:
            api_key: Expected local API key
        """
        self._api_key = api_key

    def is_public_route(self, path: str) -> bool:
        """Check if route is public (no auth required).

        Args:
            path: Request path

        Returns:
            True if route is public
        """
        return path in self.PUBLIC_ROUTES

    async def __call__(self, request: Request, call_next):
        """Process request, validating API key for protected routes.

        Args:
            request: FastAPI request
            call_next: Next middleware/handler

        Returns:
            Response from next handler

        Raises:
            HTTPException: 401 if key is invalid on protected route
        """
        # Skip auth for public routes
        if self.is_public_route(request.url.path):
            return await call_next(request)

        # Validate API key
        validate_local_api_key(request, self._api_key)

        # Continue to handler
        return await call_next(request)
