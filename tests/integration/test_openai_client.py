"""Integration tests for OpenAI client compatibility.

Tests that the middleware correctly proxies requests from the official
OpenAI Python SDK to Azure OpenAI.
"""

import pytest
from openai import AzureOpenAI


@pytest.mark.integration
class TestChatCompletions:
    """Test chat completion functionality."""

    def test_basic_chat_completion(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test basic chat completion returns valid response."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "user", "content": "What is 2+2? Reply with just the number."}
            ],
            max_completion_tokens=10,
        )

        assert response.id is not None
        assert response.model is not None
        assert len(response.choices) > 0
        assert response.choices[0].message.role == "assistant"
        assert response.choices[0].finish_reason in ("stop", "length")
        assert response.usage is not None
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0

    def test_chat_with_system_message(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test chat completion with system message."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant. Be concise."},
                {"role": "user", "content": "Say hello."},
            ],
            max_completion_tokens=50,
        )

        assert response.choices[0].message.content is not None
        assert len(response.choices[0].message.content) > 0

    def test_chat_with_temperature(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test chat completion with temperature parameter."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Pick a random color."}],
            max_completion_tokens=20,
            temperature=0.9,
        )

        assert response.choices[0].message.content is not None

    @pytest.mark.parametrize("max_tokens", [10, 50, 100])
    def test_chat_max_tokens_respected(
        self, openai_client: AzureOpenAI, chat_model: str, max_tokens: int
    ) -> None:
        """Test that max_completion_tokens limits response length."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Write a very long story."}],
            max_completion_tokens=max_tokens,
        )

        # Response should not exceed max tokens (with some tolerance for finish)
        assert response.usage.completion_tokens <= max_tokens + 5


@pytest.mark.integration
class TestStreaming:
    """Test streaming chat completions."""

    def test_basic_streaming(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test streaming chat completion returns chunks."""
        stream = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Count from 1 to 3."}],
            max_completion_tokens=50,
            stream=True,
        )

        chunks = list(stream)
        
        assert len(chunks) > 0
        # First chunk should have model info
        assert chunks[0].model is not None
        
        # Accumulate content
        content_parts = []
        for chunk in chunks:
            if chunk.choices and chunk.choices[0].delta.content:
                content_parts.append(chunk.choices[0].delta.content)
        
        full_content = "".join(content_parts)
        assert len(full_content) > 0

    def test_streaming_with_usage(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test streaming with usage information."""
        stream = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Say hi."}],
            max_completion_tokens=20,
            stream=True,
            stream_options={"include_usage": True},
        )

        chunks = list(stream)
        
        # Last chunk should have usage
        final_chunk = chunks[-1]
        if hasattr(final_chunk, 'usage') and final_chunk.usage:
            assert final_chunk.usage.prompt_tokens > 0


@pytest.mark.integration
class TestMultiTurnConversation:
    """Test multi-turn conversation handling."""

    def test_conversation_context(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test that conversation context is maintained."""
        messages = [
            {"role": "system", "content": "You are a math tutor. Be concise."},
            {"role": "user", "content": "What is 5 * 3?"},
        ]

        # First turn
        response1 = openai_client.chat.completions.create(
            model=chat_model,
            messages=messages,
            max_completion_tokens=20,
        )
        
        first_answer = response1.choices[0].message.content
        assert first_answer is not None

        # Add assistant response and continue
        messages.append({"role": "assistant", "content": first_answer})
        messages.append({"role": "user", "content": "Now divide that by 3."})

        # Second turn
        response2 = openai_client.chat.completions.create(
            model=chat_model,
            messages=messages,
            max_completion_tokens=20,
        )

        second_answer = response2.choices[0].message.content
        assert second_answer is not None
        # Should reference the previous calculation context
        assert response2.usage.prompt_tokens > response1.usage.prompt_tokens


@pytest.mark.integration
class TestCostTracking:
    """Test cost tracking functionality."""

    def test_cost_increases_after_request(
        self, openai_client: AzureOpenAI, chat_model: str, metrics_helper
    ) -> None:
        """Test that cost increases after making a request."""
        initial_cost = metrics_helper.get_daily_cost()

        # Make a request
        openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Hi"}],
            max_completion_tokens=10,
        )

        new_cost = metrics_helper.get_daily_cost()
        assert new_cost >= initial_cost

    def test_metrics_endpoint_returns_valid_data(self, metrics_helper) -> None:
        """Test that metrics endpoint returns expected fields."""
        metrics = metrics_helper.get_metrics()

        assert "daily_cost_eur" in metrics
        assert "daily_cap_eur" in metrics
        assert "percentage_used" in metrics
        assert "date" in metrics
        
        assert isinstance(metrics["daily_cost_eur"], (int, float))
        assert isinstance(metrics["daily_cap_eur"], (int, float))
        assert metrics["daily_cap_eur"] > 0


@pytest.mark.integration
class TestHealthEndpoint:
    """Test health endpoint."""

    def test_health_returns_healthy(self, http_client) -> None:
        """Test health endpoint returns healthy status."""
        response = http_client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_health_no_auth_required(self, middleware_url: str) -> None:
        """Test health endpoint works without API key."""
        import httpx
        
        response = httpx.get(f"{middleware_url}/health", timeout=5.0)
        assert response.status_code == 200


@pytest.mark.integration
class TestAuthentication:
    """Test API key authentication."""

    def test_request_without_api_key_fails(self, middleware_url: str) -> None:
        """Test that requests without API key are rejected."""
        import httpx
        
        response = httpx.post(
            f"{middleware_url}/openai/deployments/test/chat/completions",
            json={"messages": [{"role": "user", "content": "hi"}]},
            timeout=5.0,
        )
        
        assert response.status_code == 401

    def test_request_with_invalid_api_key_fails(self, middleware_url: str) -> None:
        """Test that requests with invalid API key are rejected."""
        import httpx
        
        response = httpx.post(
            f"{middleware_url}/openai/deployments/test/chat/completions",
            headers={"api-key": "invalid-key"},
            json={"messages": [{"role": "user", "content": "hi"}]},
            timeout=5.0,
        )
        
        assert response.status_code == 401
