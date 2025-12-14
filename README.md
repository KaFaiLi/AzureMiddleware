# Azure OpenAI Local Middleware

A local FastAPI proxy for Azure OpenAI with authentication, encrypted logging, cost tracking, and full SDK compatibility.

## Features

- **Transparent Proxy**: Full Azure OpenAI SDK compatibility - just change the endpoint URL
- **Multi-Model Support**: Chat models, thinking/reasoning models, and embedding models
- **Authentication**: Supports both Azure AD and API key authentication to Azure OpenAI
- **Local API Key**: Protect your middleware with a local API key
- **Cost Tracking**: Real-time daily cost tracking with configurable EUR cap
- **Encrypted Logging**: All requests/responses logged in JSONL with AES-256-GCM encryption
- **Streaming Support**: Full SSE streaming with proper cost calculation and logging
- **Swagger UI**: Interactive API documentation at `/docs`

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/example/azure-middleware.git
cd azure-middleware

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/Mac

# Install in development mode
pip install -e ".[dev]"
```

### 2. Generate Encryption Key

```bash
# Generate a random 32-byte key (base64 encoded)
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

### 3. Create Configuration

Create a `config.yaml` file:

```yaml
azure:
  endpoint: "https://your-resource.openai.azure.com"
  deployment: "gpt-4"  # Default deployment
  api_version: "2024-02-01"
  auth_mode: "api_key"  # or "aad" for Azure AD
  api_key: "your-azure-api-key"

local:
  host: "127.0.0.1"
  port: 8000
  api_key: "your-local-api-key"  # Used to access the middleware

# Pricing per model (EUR per 1000 tokens)
pricing:
  gpt-4.1-nano:
    input: 0.0001
    output: 0.0004
  gpt-5-nano:
    input: 0.01
    output: 0.03
  text-embedding-3-small:
    input: 0.00002
    output: 0.0

limits:
  daily_cost_cap_eur: 5.0

logging:
  encryption_key: "your-base64-encoded-32-byte-key"
  compression: "gzip"
  directory: "logs"
```

### 4. Start the Server

```bash
# Using the CLI
azure-middleware

# Or using Python module
python -m azure_middleware

# With custom config path
azure-middleware --config /path/to/config.yaml
```

The server starts at `http://127.0.0.1:8000` with:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`
- Metrics: `http://127.0.0.1:8000/metrics`

## Usage

### Using the Azure OpenAI SDK

```python
from openai import AzureOpenAI

# Point to your local middleware instead of Azure directly
client = AzureOpenAI(
    azure_endpoint="http://localhost:8000",
    api_key="your-local-api-key",  # Local API key from config.yaml
    api_version="2024-02-01",
)

# Chat completion
response = client.chat.completions.create(
    model="gpt-4.1-nano",  # Deployment name
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"}
    ],
    max_completion_tokens=100,
)
print(response.choices[0].message.content)

# Streaming
stream = client.chat.completions.create(
    model="gpt-4.1-nano",
    messages=[{"role": "user", "content": "Count to 5"}],
    max_completion_tokens=50,
    stream=True,
)
for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# Embeddings
embeddings = client.embeddings.create(
    model="text-embedding-3-small",
    input="Hello, world!",
)
print(f"Dimensions: {len(embeddings.data[0].embedding)}")
```

### Using Thinking/Reasoning Models

Thinking models (like `gpt-5-nano`, `o1`, `o1-mini`) use reasoning tokens for internal chain-of-thought:

```python
response = client.chat.completions.create(
    model="gpt-5-nano",
    messages=[{"role": "user", "content": "What is 15 + 27?"}],
    max_completion_tokens=200,  # Allow room for reasoning
)

# Content may be empty if all tokens were used for reasoning
content = response.choices[0].message.content
print(f"Answer: {content or '(reasoning only)'}")

# Check reasoning token usage
if response.usage.completion_tokens_details:
    reasoning = response.usage.completion_tokens_details.reasoning_tokens
    print(f"Reasoning tokens: {reasoning}")
```

### Using the Swagger UI

1. Open `http://localhost:8000/docs`
2. Click **Authorize** and enter your local API key
3. Use **Try it out** on any endpoint

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | No | Health check |
| `/metrics` | GET | No | Daily cost and usage metrics |
| `/docs` | GET | No | Swagger UI documentation |
| `/openai/deployments/{deployment}/chat/completions` | POST | Yes | Chat completions |
| `/openai/deployments/{deployment}/embeddings` | POST | Yes | Create embeddings |
| `/openai/deployments/{deployment}/responses` | POST | Yes | Responses API |

### Authentication

Include the `api-key` header with your local API key:

```bash
curl -X POST http://localhost:8000/openai/deployments/gpt-4.1-nano/chat/completions \
  -H "api-key: your-local-api-key" \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}], "max_completion_tokens": 50}'
```

### Cost Metrics

```bash
curl http://localhost:8000/metrics
```

Response:
```json
{
  "daily_cost_eur": 0.0242,
  "daily_cap_eur": 5.0,
  "date": "2025-12-14",
  "percentage_used": 0.48
}
```

## Logging & Decryption

### Log Structure

Logs are stored in `logs/YYYYMMDD/` with encrypted request/response content:

```
logs/
└── 20251214/
    ├── requests.jsonl.gz
    └── ...
```

Each log entry contains:
- `timestamp`: ISO format timestamp
- `endpoint`: API endpoint called
- `deployment`: Model deployment name
- `request_encrypted`: AES-256-GCM encrypted request body
- `response_encrypted`: AES-256-GCM encrypted response body
- `tokens`: Token usage (prompt, completion, total)
- `cost_eur`: Cost for this request
- `cumulative_cost_eur`: Running daily total
- `duration_ms`: Request duration
- `stream`: Whether streaming was used
- `status_code`: HTTP status code

### Decrypting Logs

Use the built-in decrypt CLI:

```bash
# Decrypt to stdout
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-base64-encryption-key"

# Decrypt to file
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-base64-encryption-key" \
  -o decrypted.jsonl

# Decrypt specific fields only
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-base64-encryption-key" \
  -f request_encrypted
```

### Decrypt Options

| Option | Description |
|--------|-------------|
| `input` | Path to encrypted JSONL log file |
| `-o, --output` | Output file path (default: stdout) |
| `-k, --key` | Base64-encoded AES-256 encryption key (required) |
| `-f, --fields` | Fields to decrypt (default: `request_encrypted response_encrypted`) |

### Example: Viewing Decrypted Logs

```bash
# Decrypt and pretty-print with jq
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-key" | jq '.'

# Filter for specific deployment
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-key" | jq 'select(.deployment == "gpt-4.1-nano")'

# Get total cost for the day
python -m azure_middleware.decrypt logs/20251214/requests.jsonl \
  -k "your-key" | jq -s 'last | .cumulative_cost_eur'
```

### Programmatic Decryption

```python
import base64
import json
from azure_middleware.logging.encryption import FieldEncryptor

# Load your key
key = base64.b64decode("your-base64-encryption-key")
encryptor = FieldEncryptor(key)

# Decrypt a single field
with open("logs/20251214/requests.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        if "request_encrypted" in entry:
            request = encryptor.decrypt(entry["request_encrypted"])
            print(json.dumps(request, indent=2))
```

## Configuration Reference

### Azure Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `endpoint` | string | Yes | Azure OpenAI endpoint URL |
| `deployment` | string | Yes | Default deployment name |
| `api_version` | string | No | API version (default: `2024-02-01`) |
| `auth_mode` | string | No | `aad` or `api_key` (default: `aad`) |
| `api_key` | string | Conditional | Required if `auth_mode` is `api_key` |

### Local Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `host` | string | No | Bind address (default: `127.0.0.1`) |
| `port` | integer | No | Port number (default: `8000`) |
| `api_key` | string | Yes | Local API key for middleware access |

### Pricing Settings

Add entries for each deployment with pricing per 1000 tokens:

```yaml
pricing:
  deployment-name:
    input: 0.001   # EUR per 1000 input tokens
    output: 0.002  # EUR per 1000 output tokens
```

### Limits Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `daily_cost_cap_eur` | float | No | Daily cost cap in EUR (default: `5.0`) |

### Logging Settings

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `encryption_key` | string | Yes | Base64-encoded 32-byte AES key |
| `compression` | string | No | `gzip` or `none` (default: `gzip`) |
| `directory` | string | No | Log directory path (default: `logs`) |

## Development

### Running Tests

```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests (requires running server)
python -m pytest tests/integration/ -v

# Skip specific test types
python -m pytest tests/integration/ -v -m "not thinking"
python -m pytest tests/integration/ -v -m "not embedding"

# With coverage
python -m pytest --cov=azure_middleware --cov-report=html
```

### Code Quality

```bash
# Type checking
mypy azure_middleware

# Linting
ruff check azure_middleware

# Format check
ruff format --check azure_middleware
```

### Environment Variables

For integration tests, you can override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MIDDLEWARE_URL` | `http://localhost:8000` | Middleware URL |
| `MIDDLEWARE_API_KEY` | `test-local-key-12345` | Local API key |
| `CHAT_MODEL` | `gpt-4.1-nano` | Chat model deployment |
| `THINKING_MODEL` | `gpt-5-nano` | Thinking model deployment |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model deployment |

## Troubleshooting

### Common Issues

**401 Unauthorized**
- Check that your `api-key` header matches `local.api_key` in config.yaml

**429 Too Many Requests**
- Daily cost cap exceeded
- Check `/metrics` for current usage
- Increase `limits.daily_cost_cap_eur` or wait for UTC midnight reset

**502 Bad Gateway**
- Cannot connect to Azure OpenAI
- Verify `azure.endpoint` in config.yaml
- Check network connectivity

**500 Internal Server Error on /docs**
- Restart the server after config changes

### Checking Server Health

```bash
# Health check
curl http://localhost:8000/health

# View metrics
curl http://localhost:8000/metrics
```

## License

MIT License - see [LICENSE](LICENSE) for details.
