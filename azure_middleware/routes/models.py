"""Pydantic models for API documentation (Swagger UI).

These models define the request/response schemas shown in the Swagger UI.
They are used for documentation purposes - the actual proxy passes through
the raw request body to Azure OpenAI.
"""

from typing import Any, Literal
from pydantic import BaseModel, Field


# ============================================================================
# Chat Completions Models
# ============================================================================

class ChatMessage(BaseModel):
    """A chat message."""
    
    role: Literal["system", "user", "assistant", "tool"] = Field(
        ..., 
        description="The role of the message author."
    )
    content: str | None = Field(
        None, 
        description="The content of the message."
    )
    name: str | None = Field(
        None, 
        description="An optional name for the participant."
    )


class ChatCompletionRequest(BaseModel):
    """Request body for chat completions."""
    
    messages: list[ChatMessage] = Field(
        ..., 
        description="A list of messages comprising the conversation so far.",
        min_length=1,
    )
    max_completion_tokens: int | None = Field(
        None, 
        description="Maximum number of tokens to generate. Use this instead of max_tokens for newer models.",
        ge=1,
    )
    max_tokens: int | None = Field(
        None, 
        description="Maximum tokens in response (deprecated, use max_completion_tokens).",
        ge=1,
    )
    temperature: float | None = Field(
        None, 
        description="Sampling temperature (0.0-2.0). Higher = more random.",
        ge=0.0,
        le=2.0,
    )
    top_p: float | None = Field(
        None, 
        description="Nucleus sampling probability.",
        ge=0.0,
        le=1.0,
    )
    stream: bool | None = Field(
        False, 
        description="If true, returns a stream of server-sent events."
    )
    stop: str | list[str] | None = Field(
        None, 
        description="Sequences where the API will stop generating."
    )
    presence_penalty: float | None = Field(
        None, 
        description="Penalty for new tokens based on presence in text so far.",
        ge=-2.0,
        le=2.0,
    )
    frequency_penalty: float | None = Field(
        None, 
        description="Penalty for new tokens based on frequency in text so far.",
        ge=-2.0,
        le=2.0,
    )
    n: int | None = Field(
        None, 
        description="Number of chat completion choices to generate.",
        ge=1,
    )
    seed: int | None = Field(
        None, 
        description="Seed for deterministic sampling."
    )
    user: str | None = Field(
        None, 
        description="Unique identifier for the end-user."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "messages": [
                        {"role": "system", "content": "You are a helpful assistant."},
                        {"role": "user", "content": "Hello!"}
                    ],
                    "max_completion_tokens": 100,
                    "temperature": 0.7
                }
            ]
        }
    }


class ChatCompletionChoice(BaseModel):
    """A chat completion choice."""
    
    index: int
    message: ChatMessage
    finish_reason: str | None = None


class TokenUsageInfo(BaseModel):
    """Token usage information."""
    
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """Response from chat completions."""
    
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: TokenUsageInfo | None = None


# ============================================================================
# Embeddings Models
# ============================================================================

class EmbeddingsRequest(BaseModel):
    """Request body for embeddings."""
    
    input: str | list[str] = Field(
        ..., 
        description="Input text to embed. Can be a string or array of strings."
    )
    encoding_format: Literal["float", "base64"] | None = Field(
        None, 
        description="The format of the embeddings."
    )
    dimensions: int | None = Field(
        None, 
        description="The number of dimensions for the output embeddings.",
        ge=1,
    )
    user: str | None = Field(
        None, 
        description="Unique identifier for the end-user."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input": "Hello, world!"
                },
                {
                    "input": ["Hello", "World"],
                    "dimensions": 256
                }
            ]
        }
    }


class EmbeddingData(BaseModel):
    """A single embedding."""
    
    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingsResponse(BaseModel):
    """Response from embeddings."""
    
    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: TokenUsageInfo


# ============================================================================
# Responses API Models
# ============================================================================

class ResponsesRequest(BaseModel):
    """Request body for the Responses API."""
    
    input: str | list[Any] = Field(
        ..., 
        description="The input for the response. Can be a string or structured input."
    )
    max_output_tokens: int | None = Field(
        None, 
        description="Maximum number of output tokens.",
        ge=1,
    )
    temperature: float | None = Field(
        None, 
        description="Sampling temperature.",
        ge=0.0,
        le=2.0,
    )
    instructions: str | None = Field(
        None, 
        description="System instructions for the model."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "input": "What is the capital of France?",
                    "max_output_tokens": 100
                }
            ]
        }
    }


class ResponsesResponse(BaseModel):
    """Response from the Responses API."""
    
    id: str
    object: str = "response"
    created_at: int
    status: str
    output: list[Any]
    usage: TokenUsageInfo | None = None


# ============================================================================
# Error Models
# ============================================================================

class ErrorDetail(BaseModel):
    """Error detail."""
    
    error: str
    message: str


class CostLimitError(BaseModel):
    """Cost limit exceeded error."""
    
    error: str = "daily_cost_limit_exceeded"
    message: str
    current_cost_eur: float
    limit_eur: float
    retry_after_seconds: int
