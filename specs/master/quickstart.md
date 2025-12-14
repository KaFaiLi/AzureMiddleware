# Quickstart: Azure OpenAI Local Middleware

Get the middleware running in under 5 minutes.

---

## Prerequisites

- Python 3.11+
- Azure OpenAI resource with a deployed model
- One of:
  - Azure CLI logged in (`az login`) for AAD authentication
  - Azure OpenAI API key for key-based authentication

---

## Installation

```bash
# Clone the repository
git clone https://github.com/your-org/azure-middleware.git
cd azure-middleware

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# Install the package
pip install -e .
```

---

## Configuration

1. **Copy the example config:**

```bash
copy config.example.yaml config.yaml
```

2. **Edit `config.yaml`:**

```yaml
azure:
  endpoint: "https://YOUR-RESOURCE.openai.azure.com"
  deployment: "gpt-4"
  api_version: "2024-02-01"
  auth_mode: "aad"  # or "api_key"
  api_key: ""       # Set if using api_key mode

local:
  host: "127.0.0.1"
  port: 8000
  api_key: "my-local-key"  # Choose any string

pricing:
  gpt-4:
    input: 0.03
    output: 0.06

limits:
  daily_cost_cap_eur: 5.0

logging:
  encryption_key: "GENERATE_A_KEY"  # See below
  compression: "gzip"
  directory: "logs"
```

3. **Generate encryption key:**

```bash
python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import base64; print(base64.b64encode(AESGCM.generate_key(256)).decode())"
```

Copy the output to `logging.encryption_key`.

---

## Running the Server

```bash
# Start the middleware
python -m azure_middleware

# Or with uvicorn directly
uvicorn azure_middleware.server:create_app --factory --host 127.0.0.1 --port 8000
```

You should see:
```
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

---

## Verify It Works

### Health Check

```bash
curl http://localhost:8000/health
```

Expected: `{"status": "healthy", "timestamp": "..."}`

### Check Metrics

```bash
curl http://localhost:8000/metrics
```

Expected: `{"daily_cost_eur": 0.0, "daily_cap_eur": 5.0, ...}`

---

## Using with Azure OpenAI SDK

```python
from openai import AzureOpenAI

# Point the SDK at your local middleware
client = AzureOpenAI(
    azure_endpoint="http://localhost:8000",
    api_key="my-local-key",  # Your local.api_key from config
    api_version="2024-02-01",
)

# Use exactly like normal Azure OpenAI
response = client.chat.completions.create(
    model="gpt-4",  # Deployment name
    messages=[
        {"role": "user", "content": "Hello!"}
    ]
)

print(response.choices[0].message.content)
```

### Streaming

```python
stream = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

---

## Common Issues

### "401 Unauthorized"

- Check that you're passing the correct `api_key` (the one from `local.api_key` in config.yaml)
- The header name should be `api-key` (with hyphen)

### "429 Daily cost limit exceeded"

- Your daily spending cap has been reached
- Wait until UTC midnight, or increase `limits.daily_cost_cap_eur`

### "502 Bad Gateway"

- Azure OpenAI endpoint is unreachable
- Check your `azure.endpoint` URL
- Verify network connectivity

### AAD Authentication Fails

- Run `az login` to authenticate
- Ensure your Azure account has access to the OpenAI resource

---

## What Gets Logged

Logs are stored in `logs/YYYYMMDD/<username>_YYYYMMDD.jsonl`:

```json
{
  "timestamp": "2025-12-14T10:30:00Z",
  "user": "your_windows_username",
  "endpoint": "/openai/deployments/gpt-4/chat/completions",
  "request": "$enc:BASE64...",    // Encrypted
  "response": "$enc:BASE64...",   // Encrypted
  "cost_eur": 0.0234,
  "cumulative_cost_eur": 1.5678,
  "duration_ms": 1250,
  "stream": false,
  "status_code": 200
}
```

### Decrypting Logs

```bash
python -m azure_middleware.decrypt logs/20251214/user_20251214.jsonl --config config.yaml
```

---

## Next Steps

- Review the full [API documentation](contracts/openapi.yaml)
- Check [configuration options](contracts/config-schema.md)
- Read the [data model](data-model.md) for technical details
