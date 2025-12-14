"""Shared pytest fixtures for Azure OpenAI Middleware tests."""

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from azure_middleware.config import (
    AppConfig,
    AzureConfig,
    LocalConfig,
    LoggingConfig,
    LimitsConfig,
    PricingTier,
    AuthMode,
)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_encryption_key() -> str:
    """Sample base64-encoded 32-byte key for testing."""
    # This is a test key - DO NOT use in production
    return "dGVzdGtleWZvcmFlczI1NmdjbXRlc3RpbmcxMjM0NTY="


@pytest.fixture
def sample_config(sample_encryption_key: str) -> AppConfig:
    """Create a sample configuration for testing."""
    return AppConfig(
        azure=AzureConfig(
            endpoint="https://test-resource.openai.azure.com",
            deployment="gpt-4",
            api_version="2024-02-01",
            auth_mode=AuthMode.API_KEY,
            api_key="test-azure-api-key",
        ),
        local=LocalConfig(
            host="127.0.0.1",
            port=8000,
            api_key="test-local-api-key",
        ),
        pricing={
            "gpt-4": PricingTier(input=0.03, output=0.06),
            "gpt-35-turbo": PricingTier(input=0.0015, output=0.002),
            "text-embedding-ada-002": PricingTier(input=0.0001, output=0.0),
        },
        limits=LimitsConfig(daily_cost_cap_eur=5.0),
        logging=LoggingConfig(
            encryption_key=sample_encryption_key,
            compression="gzip",
            directory="test_logs",
        ),
    )


@pytest.fixture
def mock_azure_response() -> dict:
    """Sample Azure OpenAI chat completion response."""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1702500000,
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 9,
            "total_tokens": 19,
        },
    }


@pytest.fixture
def mock_azure_streaming_chunks() -> list[bytes]:
    """Sample Azure OpenAI streaming response chunks."""
    return [
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702500000,"model":"gpt-4","choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702500000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702500000,"model":"gpt-4","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}\n\n',
        b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1702500000,"model":"gpt-4","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}\n\n',
        b"data: [DONE]\n\n",
    ]


@pytest.fixture
def mock_embedding_response() -> dict:
    """Sample Azure OpenAI embedding response."""
    return {
        "object": "list",
        "data": [
            {
                "object": "embedding",
                "index": 0,
                "embedding": [0.1, 0.2, 0.3, 0.4, 0.5] * 307,  # 1536 dims
            }
        ],
        "model": "text-embedding-ada-002",
        "usage": {
            "prompt_tokens": 5,
            "total_tokens": 5,
        },
    }


@pytest.fixture
def fixed_datetime() -> datetime:
    """Fixed datetime for consistent testing."""
    return datetime(2025, 12, 14, 10, 30, 0, tzinfo=timezone.utc)


@pytest.fixture
def mock_httpx_client(mock_azure_response: dict) -> AsyncMock:
    """Create a mock httpx AsyncClient."""
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.headers = {
        "content-type": "application/json",
        "x-request-id": "test-request-id",
    }
    mock_response.json.return_value = mock_azure_response
    mock_response.content = b'{"test": "response"}'

    mock_client = AsyncMock(spec=AsyncClient)
    mock_client.post.return_value = mock_response
    mock_client.send.return_value = mock_response

    return mock_client


@pytest.fixture
def test_client(sample_config: AppConfig) -> TestClient:
    """Create a FastAPI test client."""
    from azure_middleware.server import create_app

    app = create_app(sample_config)
    return TestClient(app)


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Headers with valid local API key."""
    return {"api-key": "test-local-api-key"}


@pytest.fixture
def chat_request_body() -> dict:
    """Sample chat completion request body."""
    return {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ],
        "max_tokens": 100,
        "temperature": 0.7,
    }


@pytest.fixture
def embedding_request_body() -> dict:
    """Sample embedding request body."""
    return {
        "input": "Hello, world!",
        "model": "text-embedding-ada-002",
    }
