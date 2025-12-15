"""FastAPI application factory and server setup."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.openapi.utils import get_openapi

from azure_middleware.config import AppConfig, AuthMode
from azure_middleware.auth.local import LocalAPIKeyMiddleware
from azure_middleware.auth.aad import AADTokenProvider
from azure_middleware.auth.apikey import APIKeyProvider
from azure_middleware.cost.tracker import CostTracker
from azure_middleware.logging.encryption import FieldEncryptor
from azure_middleware.logging.writer import LogWriter
from azure_middleware.routes.health import router as health_router
from azure_middleware.routes.chat import router as chat_router
from azure_middleware.routes.embeddings import router as embeddings_router
from azure_middleware.routes.responses import router as responses_router


logger = logging.getLogger(__name__)


class AppState:
    """Application state container."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

        # Initialize encryptor
        self.encryptor = FieldEncryptor(config.logging.get_key_bytes())

        # Initialize log writer
        self.log_writer = LogWriter(
            directory=config.logging.directory,
            encryptor=self.encryptor,
            compression=config.logging.compression,
        )

        # Initialize cost tracker
        self.cost_tracker = CostTracker(
            daily_cap_eur=config.limits.daily_cost_cap_eur,
            log_writer=self.log_writer,
        )

        # Initialize auth provider based on mode
        if config.azure.auth_mode == AuthMode.AAD:
            # Pass AAD credentials if provided in config
            self.auth_provider = AADTokenProvider(
                tenant_id=config.azure.tenant_id,
                client_id=config.azure.client_id,
                client_secret=config.azure.client_secret.get_secret_value() if config.azure.client_secret else None,
            )
        else:
            self.auth_provider = APIKeyProvider(config.azure.api_key)


def create_app(config: AppConfig) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        config: Application configuration

    Returns:
        Configured FastAPI application
    """
    # Create state container
    state = AppState(config)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        """Application lifespan handler."""
        # Startup
        logger.info("Starting Azure OpenAI Middleware...")
        await state.cost_tracker.initialize()
        logger.info(
            f"Cost tracker initialized: €{await state.cost_tracker.get_current_cost():.4f} / €{state.cost_tracker.daily_cap:.2f}"
        )

        yield

        # Shutdown
        logger.info("Shutting down Azure OpenAI Middleware...")

    # Create FastAPI app
    app = FastAPI(
        title="Azure OpenAI Local Middleware",
        description="Local proxy for Azure OpenAI with authentication, logging, and cost tracking.\n\n"
                    "**Authentication**: Use the `api-key` header with your local API key.\n\n"
                    "Click the **Authorize** button above to set your API key for testing.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Custom OpenAPI schema with security
    def custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        
        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        
        # Add security scheme for API key
        openapi_schema["components"]["securitySchemes"] = {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "api-key",
                "description": "Local API key for authentication (from config.yaml)",
            }
        }
        
        # Apply security to all paths except health, metrics, and models
        for path, methods in openapi_schema.get("paths", {}).items():
            if path not in ["/health", "/metrics", "/models"]:
                for method in methods.values():
                    if isinstance(method, dict):
                        method["security"] = [{"ApiKeyAuth": []}]
        
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi

    # Store state on app for access in routes
    app.state.app_state = state

    # Add API key middleware
    api_key_middleware = LocalAPIKeyMiddleware(config.local.api_key)

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        return await api_key_middleware(request, call_next)

    # Register routes
    app.include_router(health_router)       # Public, no auth
    app.include_router(chat_router)         # Requires auth
    app.include_router(embeddings_router)   # Requires auth
    app.include_router(responses_router)    # Requires auth

    # Add catch-all route for unsupported endpoints (501 Not Implemented)
    @app.api_route(
        "/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        include_in_schema=False,
    )
    async def catch_all(request: Request, path: str):
        """Catch-all handler for unsupported endpoints."""
        supported_endpoints = [
            "GET /health - Health check (no auth)",
            "GET /metrics - Cost metrics (no auth)",
            "GET /models - List available models (no auth)",
            "POST /openai/deployments/{deployment}/chat/completions - Chat completions",
            "POST /openai/deployments/{deployment}/embeddings - Embeddings",
            "POST /openai/deployments/{deployment}/responses - Responses API",
        ]

        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "error": "not_implemented",
                "message": f"Endpoint '/{path}' is not supported by this middleware.",
                "supported_endpoints": supported_endpoints,
            },
        )

    return app
