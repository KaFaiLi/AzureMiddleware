"""Token-based cost calculation for Azure OpenAI requests."""

from dataclasses import dataclass

from azure_middleware.config import AppConfig, PricingTier, get_pricing


@dataclass
class CostResult:
    """Result of cost calculation."""

    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_cost_eur: float
    output_cost_eur: float
    total_cost_eur: float


def calculate_cost(
    config: AppConfig,
    deployment: str,
    prompt_tokens: int,
    completion_tokens: int = 0,
) -> CostResult:
    """Calculate cost in EUR for a request.

    Formula:
        cost = (prompt_tokens * input_price / 1000) + (completion_tokens * output_price / 1000)

    Args:
        config: Application configuration with pricing
        deployment: Deployment name to look up pricing
        prompt_tokens: Number of input/prompt tokens
        completion_tokens: Number of output/completion tokens (0 for embeddings)

    Returns:
        CostResult with token counts and costs
    """
    pricing = get_pricing(config, deployment)

    input_cost = prompt_tokens * pricing.input / 1000
    output_cost = completion_tokens * pricing.output / 1000
    total_cost = input_cost + output_cost

    return CostResult(
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        input_cost_eur=round(input_cost, 6),
        output_cost_eur=round(output_cost, 6),
        total_cost_eur=round(total_cost, 6),
    )


def extract_token_counts(response_data: dict) -> tuple[int, int]:
    """Extract token counts from Azure OpenAI response.

    Args:
        response_data: Parsed JSON response from Azure OpenAI

    Returns:
        Tuple of (prompt_tokens, completion_tokens)
    """
    usage = response_data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    return prompt_tokens, completion_tokens


def extract_embedding_tokens(response_data: dict) -> int:
    """Extract token count from embedding response.

    Args:
        response_data: Parsed JSON response from Azure OpenAI embeddings

    Returns:
        Number of prompt tokens (embeddings have no output tokens)
    """
    usage = response_data.get("usage", {})
    # Embeddings use prompt_tokens or total_tokens
    return usage.get("prompt_tokens", usage.get("total_tokens", 0))
