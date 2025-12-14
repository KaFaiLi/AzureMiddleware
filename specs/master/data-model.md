# Data Model: Azure OpenAI Local Middleware

**Date**: 2025-12-14  
**Phase**: 1 - Design & Contracts

---

## Core Entities

### 1. Configuration

Central configuration loaded from `config.yaml` at startup.

```python
from pydantic import BaseModel, Field, SecretStr
from typing import Literal
from enum import Enum

class AuthMode(str, Enum):
    AAD = "aad"
    API_KEY = "api_key"

class AzureConfig(BaseModel):
    """Azure OpenAI connection settings."""
    endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    deployment: str = Field(..., description="Default deployment name")
    api_version: str = Field(default="2024-02-01", description="API version")
    auth_mode: AuthMode = Field(default=AuthMode.AAD, description="Authentication mode")
    api_key: SecretStr | None = Field(default=None, description="API key (if auth_mode=api_key)")

class LocalConfig(BaseModel):
    """Local server settings."""
    host: str = Field(default="127.0.0.1", description="Bind address")
    port: int = Field(default=8000, ge=1, le=65535, description="Port number")
    api_key: SecretStr = Field(..., description="Local API key for request validation")

class PricingTier(BaseModel):
    """Per-model pricing in EUR per 1000 tokens."""
    input: float = Field(..., ge=0, description="Input token price")
    output: float = Field(default=0.0, ge=0, description="Output token price")

class LimitsConfig(BaseModel):
    """Cost and rate limits."""
    daily_cost_cap_eur: float = Field(default=5.0, ge=0, description="Daily spending cap in EUR")

class LoggingConfig(BaseModel):
    """Logging and encryption settings."""
    encryption_key: SecretStr = Field(..., description="Base64-encoded AES-256 key")
    compression: Literal["gzip", "none"] = Field(default="gzip", description="Compression algorithm")
    directory: str = Field(default="logs", description="Log directory path")

class AppConfig(BaseModel):
    """Root configuration schema."""
    azure: AzureConfig
    local: LocalConfig
    pricing: dict[str, PricingTier] = Field(default_factory=dict)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    logging: LoggingConfig
```

**Validation Rules**:
- `azure.endpoint` must be a valid URL starting with `https://`
- `azure.api_key` required if `auth_mode` is `api_key`
- `logging.encryption_key` must decode to exactly 32 bytes
- `pricing` keys should match deployment names

---

### 2. LogEntry

Single JSONL record representing one API interaction.

```python
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any

class TokenUsage(BaseModel):
    """Token counts from response."""
    prompt: int = Field(ge=0)
    completion: int = Field(ge=0)
    total: int = Field(ge=0)

class LogEntry(BaseModel):
    """JSONL log entry schema."""
    # Plaintext metadata (always readable)
    timestamp: datetime = Field(..., description="UTC timestamp")
    user: str = Field(..., description="Windows username")
    endpoint: str = Field(..., description="Request path")
    method: str = Field(default="POST", description="HTTP method")
    deployment: str = Field(..., description="Azure deployment name")
    
    # Encrypted fields (prefixed with $enc: when serialized)
    request: str = Field(..., description="Encrypted request JSON")
    response: str | None = Field(default=None, description="Encrypted response JSON (null for embeddings)")
    
    # Cost tracking (plaintext)
    tokens: TokenUsage | None = Field(default=None)
    cost_eur: float = Field(ge=0, description="This request's cost")
    cumulative_cost_eur: float = Field(ge=0, description="Daily cumulative cost")
    
    # Performance & status
    duration_ms: int = Field(ge=0, description="Request duration")
    stream: bool = Field(default=False, description="Was streaming enabled")
    status_code: int = Field(ge=100, le=599, description="HTTP status code")
    error: str | None = Field(default=None, description="Error message if failed")
```

**Storage Format**: `logs/YYYYMMDD/<username>_YYYYMMDD.jsonl`

**Example**:
```json
{
  "timestamp": "2025-12-14T10:30:00.000Z",
  "user": "developer",
  "endpoint": "/openai/deployments/gpt-4/chat/completions",
  "method": "POST",
  "deployment": "gpt-4",
  "request": "$enc:BASE64...",
  "response": "$enc:BASE64...",
  "tokens": {"prompt": 150, "completion": 50, "total": 200},
  "cost_eur": 0.0234,
  "cumulative_cost_eur": 2.5678,
  "duration_ms": 1250,
  "stream": false,
  "status_code": 200,
  "error": null
}
```

---

### 3. CostState

In-memory cost tracking state.

```python
from dataclasses import dataclass
from datetime import date

@dataclass
class CostState:
    """Mutable cost tracking state."""
    cumulative_cost_eur: float = 0.0
    current_date: date = None  # Set on init
    
    def reset(self, new_date: date) -> None:
        """Reset for new day."""
        self.cumulative_cost_eur = 0.0
        self.current_date = new_date
```

**State Transitions**:
1. **Startup**: Load from last log line or initialize to 0
2. **Pre-request**: Check if `cumulative_cost_eur < daily_cap`
3. **Post-request**: Add cost, update `cumulative_cost_eur`
4. **Midnight**: Reset to 0 on next request

---

### 4. ProxyRequest / ProxyResponse

Internal DTOs for request/response handling.

```python
from pydantic import BaseModel
from typing import Any

class ProxyRequest(BaseModel):
    """Captured incoming request."""
    method: str
    path: str
    query_params: dict[str, str]
    headers: dict[str, str]
    body: bytes
    timestamp: datetime
    is_streaming: bool = False

class ProxyResponse(BaseModel):
    """Captured upstream response."""
    status_code: int
    headers: dict[str, str]
    body: bytes | None  # None for streaming (buffered separately)
    duration_ms: int
```

---

### 5. StreamBuffer

Accumulator for streaming responses.

```python
from dataclasses import dataclass, field

@dataclass
class StreamBuffer:
    """Accumulates SSE chunks for logging."""
    chunks: list[bytes] = field(default_factory=list)
    started_at: datetime = None
    
    def append(self, chunk: bytes) -> None:
        self.chunks.append(chunk)
    
    def get_complete_response(self) -> bytes:
        return b''.join(self.chunks)
    
    def parse_sse_events(self) -> list[dict]:
        """Parse SSE format into list of data payloads."""
        raw = self.get_complete_response().decode('utf-8')
        events = []
        for line in raw.split('\n'):
            if line.startswith('data: ') and line[6:] != '[DONE]':
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
        return events
```

---

## Entity Relationships

```
┌─────────────┐
│  AppConfig  │──────────────────────────────────────┐
└─────────────┘                                      │
       │                                             │
       │ loads                                       │
       ▼                                             │
┌─────────────┐     validates     ┌──────────────┐  │
│   Server    │◄─────────────────│ ProxyRequest │  │
│  (FastAPI)  │                   └──────────────┘  │
└─────────────┘                          │          │
       │                                 │ forwards │
       │ uses                            ▼          │
       ▼                         ┌──────────────┐   │
┌─────────────┐                  │    Azure     │   │
│ CostTracker │                  │   OpenAI     │   │
└─────────────┘                  └──────────────┘   │
       │                                 │          │
       │ tracks                          │ returns  │
       ▼                                 ▼          │
┌─────────────┐     logs         ┌──────────────┐   │
│  CostState  │◄────────────────│ProxyResponse │   │
└─────────────┘                  └──────────────┘   │
       │                                 │          │
       │                                 │ or       │
       │                                 ▼          │
       │                         ┌──────────────┐   │
       │                         │ StreamBuffer │   │
       │                         └──────────────┘   │
       │                                 │          │
       │                                 │          │
       ▼                                 ▼          │
┌─────────────────────────────────────────────┐    │
│                  LogEntry                    │◄───┘
│  (encrypted request/response, plaintext meta)│    pricing
└─────────────────────────────────────────────┘
       │
       │ writes
       ▼
┌─────────────────────────────────────────────┐
│            JSONL Log File                    │
│  logs/YYYYMMDD/<user>_YYYYMMDD.jsonl        │
└─────────────────────────────────────────────┘
```

---

## State Diagram: Cost Enforcement

```
                    ┌─────────────────┐
                    │   Server Start  │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Read Last Line  │
                    │   of Today's    │
                    │    Log File     │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌─────────────────┐         ┌─────────────────┐
     │ Log exists for  │         │  No log or      │
     │     today       │         │ different date  │
     └────────┬────────┘         └────────┬────────┘
              │                           │
              ▼                           ▼
     ┌─────────────────┐         ┌─────────────────┐
     │ Set cumulative  │         │ Set cumulative  │
     │ cost from log   │         │   cost = 0      │
     └────────┬────────┘         └────────┬────────┘
              │                           │
              └──────────────┬────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Ready to Serve │◄───────────────┐
                    └────────┬────────┘                │
                             │                         │
                             ▼ request arrives         │
                    ┌─────────────────┐                │
                    │  Check: is it   │                │
                    │   a new day?    │                │
                    └────────┬────────┘                │
                             │                         │
              ┌──────────────┴──────────────┐          │
              │ yes                    no   │          │
              ▼                             ▼          │
     ┌─────────────────┐         ┌─────────────────┐   │
     │  Reset cost     │         │  Check: cost    │   │
     │    to 0         │         │    < cap?       │   │
     └────────┬────────┘         └────────┬────────┘   │
              │                           │            │
              │              ┌────────────┴─────┐      │
              │              │ yes              │ no   │
              │              ▼                  ▼      │
              │     ┌─────────────────┐ ┌───────────┐  │
              │     │ Process Request │ │ HTTP 429  │  │
              │     └────────┬────────┘ └───────────┘  │
              │              │                         │
              │              ▼                         │
              │     ┌─────────────────┐                │
              │     │ Add cost to     │                │
              │     │   cumulative    │                │
              │     └────────┬────────┘                │
              │              │                         │
              └──────────────┴─────────────────────────┘
```
