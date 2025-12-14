"""Routes package for Azure OpenAI Middleware."""

from azure_middleware.routes.health import router as health_router
from azure_middleware.routes.chat import router as chat_router
from azure_middleware.routes.embeddings import router as embeddings_router
from azure_middleware.routes.responses import router as responses_router

__all__ = ["health_router", "chat_router", "embeddings_router", "responses_router"]
