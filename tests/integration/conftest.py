"""Pytest fixtures for integration tests against running middleware.

These fixtures provide a configured OpenAI client and utilities for
testing the middleware with real Azure OpenAI endpoints.

Note: Integration tests require:
1. A running middleware server (python -m azure_middleware)
2. Valid Azure OpenAI credentials in config.yaml
3. Authentication can be API key or AAD (set via MIDDLEWARE_AUTH_MODE)

Environment Variables:
- MIDDLEWARE_URL: Middleware endpoint (default: http://localhost:8000)
- MIDDLEWARE_API_KEY: Local API key for middleware (required for both auth modes)
- MIDDLEWARE_AUTH_MODE: "api_key" or "aad" (default: api_key)
- AZURE_API_VERSION: API version (default: 2024-02-01)
- CHAT_MODEL: Chat model deployment name
- THINKING_MODEL: Thinking model deployment name
- EMBEDDING_MODEL: Embedding model deployment name

For AAD testing, ensure your middleware config.yaml has:
  azure:
    auth_mode: aad
    tenant_id: "..."  # Optional, or use DefaultAzureCredential
    client_id: "..."
    client_secret: "..."
"""

import os
from typing import Generator

import pytest
from openai import AzureOpenAI
import httpx


# Configuration from environment or defaults
MIDDLEWARE_URL = os.getenv("MIDDLEWARE_URL", "http://localhost:8000")
MIDDLEWARE_API_KEY = os.getenv("MIDDLEWARE_API_KEY", "test-local-key-12345")
MIDDLEWARE_AUTH_MODE = os.getenv("MIDDLEWARE_AUTH_MODE", "api_key")  # "api_key" or "aad"
API_VERSION = os.getenv("AZURE_API_VERSION", "2024-02-01")

# Model deployments
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4.1-nano")
THINKING_MODEL = os.getenv("THINKING_MODEL", "gpt-5-nano")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")


@pytest.fixture(scope="session")
def middleware_url() -> str:
    """Get the middleware URL."""
    return MIDDLEWARE_URL


@pytest.fixture(scope="session")
def auth_mode() -> str:
    """Get the middleware authentication mode (api_key or aad)."""
    return MIDDLEWARE_AUTH_MODE


@pytest.fixture(scope="session")
def api_key() -> str:
    """Get the middleware API key (for local middleware authentication)."""
    return MIDDLEWARE_API_KEY


@pytest.fixture(scope="session")
def openai_client() -> Generator[AzureOpenAI, None, None]:
    """Create an OpenAI client configured for the middleware.
    
    This client can be used for all OpenAI SDK-based tests.
    """
    client = AzureOpenAI(
        azure_endpoint=MIDDLEWARE_URL,
        api_key=MIDDLEWARE_API_KEY,
        api_version=API_VERSION,
    )
    yield client
    # Cleanup if needed
    client.close()


@pytest.fixture(scope="session")
def http_client() -> Generator[httpx.Client, None, None]:
    """Create an HTTP client for direct API calls."""
    client = httpx.Client(
        base_url=MIDDLEWARE_URL,
        headers={"api-key": MIDDLEWARE_API_KEY},
        timeout=30.0,
    )
    yield client
    client.close()


@pytest.fixture
def chat_model() -> str:
    """Get the chat model deployment name."""
    return CHAT_MODEL


@pytest.fixture
def thinking_model() -> str:
    """Get the thinking model deployment name."""
    return THINKING_MODEL


@pytest.fixture
def embedding_model() -> str:
    """Get the embedding model deployment name."""
    return EMBEDDING_MODEL


def pytest_configure(config):
    """Configure custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires running server)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "thinking: mark test as requiring thinking model"
    )
    config.addinivalue_line(
        "markers", "embedding: mark test as requiring embedding model"
    )


@pytest.fixture(autouse=True)
def check_server_running(middleware_url: str, auth_mode: str) -> None:
    """Verify the middleware server is running before each test.
    
    Also logs the authentication mode being tested.
    """
    try:
        response = httpx.get(f"{middleware_url}/health", timeout=5.0)
        if response.status_code != 200:
            pytest.skip(f"Middleware server not healthy: {response.status_code}")
        
        # Log auth mode for debugging
        print(f"\nTesting with auth mode: {auth_mode}")
        
    except httpx.ConnectError:
        pytest.skip(f"Middleware server not running at {middleware_url}")
    except Exception as e:
        pytest.skip(f"Cannot connect to middleware: {e}")


class MetricsHelper:
    """Helper class for checking middleware metrics."""
    
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key = api_key
    
    def get_metrics(self) -> dict:
        """Fetch current metrics from middleware."""
        response = httpx.get(f"{self.base_url}/metrics", timeout=5.0)
        response.raise_for_status()
        return response.json()
    
    def get_daily_cost(self) -> float:
        """Get current daily cost in EUR."""
        return self.get_metrics()["daily_cost_eur"]
    
    def get_percentage_used(self) -> float:
        """Get percentage of daily cap used."""
        return self.get_metrics()["percentage_used"]


@pytest.fixture
def metrics_helper(middleware_url: str, api_key: str) -> MetricsHelper:
    """Create a metrics helper instance."""
    return MetricsHelper(middleware_url, api_key)
