# Research Notes: Azure OpenAI Local Middleware

**Date**: 2025-12-14  
**Phase**: 0 - Outline & Research

---

## 1. FastAPI Transparent Proxy Patterns

### Decision
Use FastAPI's `Request` object to capture raw request data and forward using `httpx.AsyncClient` with minimal transformation.

### Rationale
- `Request.body()` returns raw bytes, preserving exact JSON formatting
- Avoid Pydantic model parsing to prevent data loss or transformation
- httpx AsyncClient provides connection pooling and async support
- Azure OpenAI compatibility requires preserving specific headers

### Key Findings

#### Request Forwarding
- Use `request.body()` for exact byte preservation
- Filter hop-by-hop headers: `connection`, `keep-alive`, `proxy-authenticate`, `transfer-encoding`, `upgrade`, `host`
- Preserve Azure-specific headers: `api-key`, `authorization`, `x-ms-client-request-id`

#### Response Handling
- Preserve Azure response headers: `x-request-id`, `x-ratelimit-*`, `openai-model`, `openai-processing-ms`
- Strip `content-encoding` (httpx auto-decodes) and `transfer-encoding`
- Use `StreamingResponse` for SSE, `Response` for non-streaming

#### Streaming SSE
- Detect streaming via `stream=true` in request body
- Use `client.send(request, stream=True)` with `aiter_bytes()` for chunk iteration
- Buffer chunks in `bytearray` for logging, yield immediately to client
- Parse SSE events after stream completes for final log entry

#### httpx Configuration
```python
httpx.AsyncClient(
    timeout=httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=5.0),
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    http2=False,  # Azure works better with HTTP/1.1
    follow_redirects=True,
)
```

### Alternatives Considered
| Approach | Pros | Cons |
|----------|------|------|
| Pydantic models | Type safety | May transform/lose unknown fields |
| `request.json()` | Parsed dict | Re-serialization may alter formatting |
| **`request.body()`** | **Exact byte preservation** | **Must handle empty body** |
| aiohttp | Mature | Different API, extra dependency |

---

## 2. AES-256-GCM Log Encryption

### Decision
Use `cryptography` library's AESGCM with 12-byte random nonce, gzip compression before encryption, base64 output.

### Rationale
- AES-256-GCM is authenticated encryption (confidentiality + integrity)
- 96-bit nonce is NIST-recommended for GCM
- Compression before encryption (encrypted data is incompressible)
- Base64 output is JSON-safe for JSONL storage

### Key Findings

#### Key Storage
- Store as base64 in `config.yaml` (32 bytes → 44 chars base64)
- Generate: `base64.b64encode(AESGCM.generate_key(bit_length=256))`

#### Encrypted Field Format
```
$enc:BASE64([flags:1][nonce:12][ciphertext:N][tag:16])

flags byte:
  bit 0: compressed (1) or not (0)
```

#### Implementation Pattern
```python
class FieldEncryptor:
    def __init__(self, key: bytes):
        self._aesgcm = AESGCM(key)
    
    def encrypt(self, value: str | dict) -> str:
        data = json.dumps(value).encode() if isinstance(value, dict) else value.encode()
        if len(data) >= 100:
            compressed = gzip.compress(data, compresslevel=6)
            if len(compressed) < len(data):
                data, flags = compressed, 0x01
            else:
                flags = 0x00
        else:
            flags = 0x00
        
        nonce = os.urandom(12)
        ciphertext = self._aesgcm.encrypt(nonce, data, None)
        blob = bytes([flags]) + nonce + ciphertext
        return '$enc:' + base64.b64encode(blob).decode()
```

#### Decryption Utility
- CLI tool for batch decryption: `python -m azure_middleware.decrypt logs.jsonl`
- Stream processing for large files
- Selective field decryption support

### Alternatives Considered
| Approach | Pros | Cons |
|----------|------|------|
| **AES-256-GCM** | **Authenticated, fast (AES-NI)** | **Slightly complex** |
| AES-256-CBC + HMAC | Widely compatible | Two operations, more code |
| Fernet | Simple API | Larger overhead, timestamps |

---

## 3. Async Cost Tracking

### Decision
Singleton `CostTracker` with `asyncio.Lock`, lazy midnight reset, last-line log parsing on startup.

### Rationale
- `asyncio.Lock` is correct for async contexts (not threading.Lock)
- Lazy reset avoids scheduler complexity
- Last-line parsing is O(1) vs O(n) for full file

### Key Findings

#### State Structure
```python
@dataclass
class CostState:
    cumulative_cost_eur: float
    current_date: date

class CostTracker:
    _lock: asyncio.Lock
    _state: CostState
    _daily_cap_eur: float
```

#### Pre-Request Enforcement
- FastAPI dependency injection for clean separation
- Return HTTP 429 with `Retry-After` header (seconds until UTC midnight)
- Block if `current_cost >= cap` (requests in progress may slightly exceed)

#### Post-Request Update
- Calculate cost from response token counts
- Update atomically under lock
- Fire-and-forget async logging

#### Startup Reconstruction
```python
def read_last_line_cost(log_path: Path) -> tuple[float, date | None]:
    # Seek from end to find last newline
    # Parse JSON, extract cumulative_cost_eur
    # Return (0.0, None) if file missing/corrupt
```

#### Midnight Reset (Lazy)
```python
def _maybe_reset_for_new_day(self):
    today = datetime.now(timezone.utc).date()
    if today > self._state.current_date:
        self._state.cumulative_cost_eur = 0.0
        self._state.current_date = today
```

### Edge Cases
| Scenario | Handling |
|----------|----------|
| Request spans midnight | Reset check in `add_cost()` → cost goes to new day |
| Concurrent requests | All may pass check → slight over-cap acceptable |
| Corrupted log last line | Fall back to 0.0 (safe default) |
| Server restart mid-day | Reconstruct from last log line |

### Alternatives Considered
| Approach | Pros | Cons |
|----------|------|------|
| **Lazy reset** | **Simple, no scheduler** | **First request of day slightly slower** |
| Scheduled task | Predictable timing | Complexity, failure modes |
| Database storage | ACID guarantees | Overkill for single-user |

---

## 4. Azure Authentication Patterns

### Decision
Support both AAD (DefaultAzureCredential) and API key modes, selected via config.

### Rationale
- AAD is preferred for security (no static secrets)
- API key is simpler for local development
- `azure-identity` handles token refresh automatically

### Key Findings

#### AAD Mode
```python
from azure.identity.aio import DefaultAzureCredential

class AADAuthProvider:
    def __init__(self):
        self._credential = DefaultAzureCredential()
    
    async def get_headers(self) -> dict:
        token = await self._credential.get_token("https://cognitiveservices.azure.com/.default")
        return {"Authorization": f"Bearer {token.token}"}
```

#### API Key Mode
```python
class APIKeyAuthProvider:
    def __init__(self, api_key: str):
        self._api_key = api_key
    
    async def get_headers(self) -> dict:
        return {"api-key": self._api_key}
```

---

## 5. Dependencies Summary

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | >=0.109.0 | Web framework |
| `uvicorn[standard]` | >=0.27.0 | ASGI server |
| `httpx` | >=0.26.0 | Async HTTP client |
| `azure-identity` | >=1.15.0 | AAD authentication |
| `pyyaml` | >=6.0 | Config loading |
| `pydantic` | >=2.5.0 | Config validation |
| `cryptography` | >=42.0.0 | AES-256-GCM encryption |

### Dev Dependencies
| Package | Purpose |
|---------|---------|
| `pytest` | Testing |
| `pytest-asyncio` | Async test support |
| `pytest-cov` | Coverage |
| `httpx` | TestClient |

---

## Open Items Resolved

All NEEDS CLARIFICATION items from Technical Context have been resolved through this research.
