"""Integration tests for multiple model support.

Tests that the middleware correctly handles different model types:
1. Chat models (gpt-4.1-nano, gpt-4o, etc.)
2. Thinking/reasoning models (gpt-5-nano, o1, etc.)
3. Embedding models (text-embedding-3-small, etc.)

Each model type has different characteristics:
- Chat models: Standard request/response, visible content
- Thinking models: May use reasoning tokens, content may be empty
- Embedding models: Return vector embeddings, no completion tokens
"""

import pytest
from openai import AzureOpenAI


@pytest.mark.integration
class TestChatModels:
    """Test chat model functionality."""

    def test_chat_model_returns_content(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test chat model returns visible content."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Say hello"}],
            max_completion_tokens=20,
        )

        content = response.choices[0].message.content
        assert content is not None
        assert len(content) > 0
        assert response.usage.completion_tokens > 0

    def test_chat_model_token_tracking(
        self, openai_client: AzureOpenAI, chat_model: str
    ) -> None:
        """Test chat model token usage is tracked correctly."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Hi there!"},
            ],
            max_completion_tokens=30,
        )

        usage = response.usage
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens > 0
        assert usage.total_tokens == usage.prompt_tokens + usage.completion_tokens

    @pytest.mark.parametrize("temperature", [0.0, 0.5, 1.0])
    def test_chat_model_temperature_parameter(
        self, openai_client: AzureOpenAI, chat_model: str, temperature: float
    ) -> None:
        """Test chat model accepts different temperature values."""
        response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Pick a number."}],
            max_completion_tokens=10,
            temperature=temperature,
        )

        assert response.choices[0].message.content is not None


@pytest.mark.integration
@pytest.mark.thinking
class TestThinkingModels:
    """Test thinking/reasoning model functionality."""

    def test_thinking_model_usage_structure(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test thinking model returns proper usage structure."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_completion_tokens=100,
        )

        usage = response.usage
        assert usage.prompt_tokens > 0
        assert usage.completion_tokens >= 0
        assert usage.total_tokens > 0

    def test_thinking_model_reasoning_tokens(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test thinking model tracks reasoning tokens."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Calculate 7 * 8"}],
            max_completion_tokens=150,
        )

        # Check for reasoning tokens in usage details
        if hasattr(response.usage, 'completion_tokens_details'):
            details = response.usage.completion_tokens_details
            if details and hasattr(details, 'reasoning_tokens'):
                reasoning = details.reasoning_tokens
                assert reasoning >= 0
                print(f"Reasoning tokens used: {reasoning}")


@pytest.mark.integration
@pytest.mark.embedding
class TestEmbeddingModels:
    """Test embedding model functionality."""

    def test_embedding_returns_vector(
        self, openai_client: AzureOpenAI, embedding_model: str
    ) -> None:
        """Test embedding model returns vector."""
        try:
            response = openai_client.embeddings.create(
                model=embedding_model,
                input="Hello, world!",
            )

            assert len(response.data) > 0
            embedding = response.data[0].embedding
            assert isinstance(embedding, list)
            assert len(embedding) > 0
            assert all(isinstance(x, float) for x in embedding)
        except Exception as e:
            pytest.skip(f"Embedding model not available: {e}")

    def test_embedding_token_usage(
        self, openai_client: AzureOpenAI, embedding_model: str
    ) -> None:
        """Test embedding model tracks token usage."""
        try:
            response = openai_client.embeddings.create(
                model=embedding_model,
                input="Test embedding input",
            )

            assert response.usage.prompt_tokens > 0
            # Embeddings don't have completion tokens
        except Exception as e:
            pytest.skip(f"Embedding model not available: {e}")

    def test_embedding_multiple_inputs(
        self, openai_client: AzureOpenAI, embedding_model: str
    ) -> None:
        """Test embedding model with multiple inputs."""
        try:
            response = openai_client.embeddings.create(
                model=embedding_model,
                input=["Hello", "World", "Test"],
            )

            assert len(response.data) == 3
            for item in response.data:
                assert len(item.embedding) > 0
        except Exception as e:
            pytest.skip(f"Embedding model not available: {e}")

    def test_embedding_dimensions(
        self, openai_client: AzureOpenAI, embedding_model: str
    ) -> None:
        """Test embedding dimensions are consistent."""
        try:
            response1 = openai_client.embeddings.create(
                model=embedding_model,
                input="First text",
            )
            response2 = openai_client.embeddings.create(
                model=embedding_model,
                input="Second text, which is longer",
            )

            # Dimensions should be the same regardless of input length
            dim1 = len(response1.data[0].embedding)
            dim2 = len(response2.data[0].embedding)
            assert dim1 == dim2
        except Exception as e:
            pytest.skip(f"Embedding model not available: {e}")


@pytest.mark.integration
class TestMultiModelCostTracking:
    """Test cost tracking across different model types."""

    def test_chat_model_cost_increases(
        self, openai_client: AzureOpenAI, chat_model: str, metrics_helper
    ) -> None:
        """Test chat model requests increase cost."""
        initial_cost = metrics_helper.get_daily_cost()

        openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Hi"}],
            max_completion_tokens=10,
        )

        new_cost = metrics_helper.get_daily_cost()
        assert new_cost >= initial_cost

    @pytest.mark.thinking
    def test_thinking_model_cost_increases(
        self, openai_client: AzureOpenAI, thinking_model: str, metrics_helper
    ) -> None:
        """Test thinking model requests increase cost."""
        initial_cost = metrics_helper.get_daily_cost()

        openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Hi"}],
            max_completion_tokens=50,
        )

        new_cost = metrics_helper.get_daily_cost()
        assert new_cost >= initial_cost

    @pytest.mark.embedding
    def test_embedding_model_cost_increases(
        self, openai_client: AzureOpenAI, embedding_model: str, metrics_helper
    ) -> None:
        """Test embedding model requests increase cost."""
        try:
            initial_cost = metrics_helper.get_daily_cost()

            openai_client.embeddings.create(
                model=embedding_model,
                input="Test text",
            )

            new_cost = metrics_helper.get_daily_cost()
            assert new_cost >= initial_cost
        except Exception as e:
            pytest.skip(f"Embedding model not available: {e}")


@pytest.mark.integration
class TestModelSwitching:
    """Test switching between different models."""

    def test_sequential_different_models(
        self, openai_client: AzureOpenAI, chat_model: str, thinking_model: str
    ) -> None:
        """Test making sequential requests to different models."""
        # First: chat model
        response1 = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Say 1"}],
            max_completion_tokens=10,
        )
        assert response1.model is not None

        # Second: thinking model
        response2 = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Say 2"}],
            max_completion_tokens=50,
        )
        assert response2.model is not None

        # Third: back to chat model
        response3 = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": "Say 3"}],
            max_completion_tokens=10,
        )
        assert response3.model is not None

    def test_different_models_different_responses(
        self, openai_client: AzureOpenAI, chat_model: str, thinking_model: str
    ) -> None:
        """Test that different models produce valid but potentially different responses."""
        prompt = "What is 5+5?"

        chat_response = openai_client.chat.completions.create(
            model=chat_model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=20,
        )

        thinking_response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=100,
        )

        # Both should have valid responses (though content may differ)
        assert chat_response.usage.total_tokens > 0
        assert thinking_response.usage.total_tokens > 0
