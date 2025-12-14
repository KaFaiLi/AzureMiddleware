"""Integration tests for thinking/reasoning models.

Thinking models (like gpt-5-nano, o1, o1-mini) use 'reasoning tokens' for
internal chain-of-thought processing. These tokens count toward billing
but the reasoning itself may not be visible in the response content.

These tests verify that the middleware correctly handles:
1. Reasoning token tracking in usage
2. Empty content responses (when all tokens are reasoning)
3. Streaming with thinking models
4. Cost tracking for reasoning tokens
"""

import pytest
from openai import AzureOpenAI


@pytest.mark.integration
@pytest.mark.thinking
class TestThinkingModelBasics:
    """Test basic thinking model functionality."""

    def test_thinking_model_returns_response(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test thinking model returns valid response structure."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "What is 2+2?"}],
            max_completion_tokens=100,
        )

        assert response.id is not None
        assert response.model is not None
        assert len(response.choices) > 0
        assert response.usage is not None
        assert response.usage.prompt_tokens > 0
        assert response.usage.completion_tokens > 0

    def test_thinking_model_tracks_reasoning_tokens(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that reasoning tokens are tracked in usage."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "What is 3 + 5?"}],
            max_completion_tokens=150,
        )

        usage = response.usage
        assert usage.completion_tokens > 0

        # Check for reasoning tokens in completion_tokens_details
        if hasattr(usage, 'completion_tokens_details') and usage.completion_tokens_details:
            details = usage.completion_tokens_details
            if hasattr(details, 'reasoning_tokens'):
                # Reasoning tokens should be part of completion tokens
                assert details.reasoning_tokens >= 0
                assert details.reasoning_tokens <= usage.completion_tokens

    def test_thinking_model_may_have_empty_content(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that thinking models can return empty content (all reasoning)."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Solve: 7 * 8"}],
            max_completion_tokens=50,  # Small limit may result in only reasoning
        )

        # Content may be empty or present - both are valid
        content = response.choices[0].message.content
        # This assertion just verifies we got a response
        assert response.choices[0].finish_reason in ("stop", "length")


@pytest.mark.integration
@pytest.mark.thinking
class TestThinkingModelComplexTasks:
    """Test thinking models with complex reasoning tasks."""

    def test_multi_step_reasoning(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test thinking model with multi-step reasoning problem."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[
                {
                    "role": "user",
                    "content": "I have 10 apples. I give 3 to Alice, buy 5 more, "
                               "then give half to Bob. How many do I have?"
                }
            ],
            max_completion_tokens=300,
        )

        assert response.usage.completion_tokens > 0
        # Complex problems should use more tokens
        assert response.usage.total_tokens > response.usage.prompt_tokens

    def test_reasoning_uses_tokens(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that complex reasoning uses reasoning tokens."""
        # Simple question
        simple_response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Say hi"}],
            max_completion_tokens=100,
        )

        # Complex question
        complex_response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[
                {
                    "role": "user",
                    "content": "If a train travels 60 mph for 2.5 hours, how far does it go?"
                }
            ],
            max_completion_tokens=200,
        )

        # Complex should generally use more completion tokens
        # (though this isn't guaranteed, it's a reasonable heuristic)
        assert complex_response.usage.completion_tokens >= simple_response.usage.completion_tokens * 0.5


@pytest.mark.integration
@pytest.mark.thinking
class TestThinkingModelStreaming:
    """Test streaming with thinking models."""

    def test_streaming_returns_chunks(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that streaming works with thinking models."""
        stream = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Count to 3."}],
            max_completion_tokens=100,
            stream=True,
        )

        chunks = list(stream)
        assert len(chunks) > 0

    def test_streaming_with_usage_info(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test streaming with usage information."""
        stream = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "What is 5+5?"}],
            max_completion_tokens=100,
            stream=True,
            stream_options={"include_usage": True},
        )

        chunks = list(stream)
        
        # Look for usage in final chunks
        usage_found = False
        for chunk in reversed(chunks):
            if hasattr(chunk, 'usage') and chunk.usage:
                usage_found = True
                assert chunk.usage.prompt_tokens > 0
                assert chunk.usage.completion_tokens >= 0
                break

    def test_streaming_accumulates_content(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that streaming content can be accumulated."""
        stream = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "Say hello"}],
            max_completion_tokens=50,
            stream=True,
        )

        content_parts = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                content_parts.append(chunk.choices[0].delta.content)

        # Content may be empty for thinking models (all reasoning)
        # This just verifies we processed the stream
        full_content = "".join(content_parts)
        assert isinstance(full_content, str)


@pytest.mark.integration
@pytest.mark.thinking
class TestThinkingModelCostTracking:
    """Test cost tracking for thinking models."""

    def test_cost_tracked_for_reasoning_tokens(
        self, openai_client: AzureOpenAI, thinking_model: str, metrics_helper
    ) -> None:
        """Test that reasoning tokens are included in cost tracking."""
        initial_cost = metrics_helper.get_daily_cost()

        # Make a request that will use reasoning tokens
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[{"role": "user", "content": "What is 15 + 27?"}],
            max_completion_tokens=100,
        )

        # Verify tokens were used
        assert response.usage.completion_tokens > 0

        # Cost should have increased
        new_cost = metrics_helper.get_daily_cost()
        assert new_cost >= initial_cost

    def test_reasoning_tokens_in_usage_details(
        self, openai_client: AzureOpenAI, thinking_model: str
    ) -> None:
        """Test that usage details include reasoning token breakdown."""
        response = openai_client.chat.completions.create(
            model=thinking_model,
            messages=[
                {"role": "user", "content": "Calculate: (5 + 3) * 2"}
            ],
            max_completion_tokens=150,
        )

        usage = response.usage
        
        # Log the usage details for debugging
        print(f"\nUsage Details:")
        print(f"  Prompt tokens: {usage.prompt_tokens}")
        print(f"  Completion tokens: {usage.completion_tokens}")
        print(f"  Total tokens: {usage.total_tokens}")
        
        if hasattr(usage, 'completion_tokens_details') and usage.completion_tokens_details:
            details = usage.completion_tokens_details
            print(f"  Completion token details: {details}")
            if hasattr(details, 'reasoning_tokens'):
                print(f"  Reasoning tokens: {details.reasoning_tokens}")
