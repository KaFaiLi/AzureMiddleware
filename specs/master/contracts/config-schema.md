# Configuration Schema: config.yaml

**Version**: 1.0.0

This document defines the configuration file schema for the Azure OpenAI Local Middleware.

---

## Full Example

```yaml
# Azure OpenAI connection settings
azure:
  endpoint: "https://my-resource.openai.azure.com"
  deployment: "gpt-4"
  api_version: "2024-02-01"
  auth_mode: "aad"  # "aad" or "api_key"
  api_key: ""       # Required only if auth_mode is "api_key"

# Local server settings
local:
  host: "127.0.0.1"
  port: 8000
  api_key: "your-local-api-key-here"  # Required

# Pricing per deployment (EUR per 1000 tokens)
pricing:
  gpt-4:
    input: 0.03
    output: 0.06
  gpt-4-turbo:
    input: 0.01
    output: 0.03
  gpt-35-turbo:
    input: 0.0015
    output: 0.002
  text-embedding-ada-002:
    input: 0.0001
    output: 0.0
  text-embedding-3-small:
    input: 0.00002
    output: 0.0

# Cost limits
limits:
  daily_cost_cap_eur: 5.0

# Logging settings
logging:
  encryption_key: "BASE64_ENCODED_32_BYTE_KEY"  # Generate with: python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import base64; print(base64.b64encode(AESGCM.generate_key(256)).decode())"
  compression: "gzip"  # "gzip" or "none"
  directory: "logs"    # Relative or absolute path
```

---

## Section Details

### `azure` (required)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `endpoint` | string | ✅ | - | Azure OpenAI endpoint URL (e.g., `https://myresource.openai.azure.com`) |
| `deployment` | string | ✅ | - | Default deployment name for cost calculation |
| `api_version` | string | ❌ | `2024-02-01` | Azure OpenAI API version |
| `auth_mode` | enum | ❌ | `aad` | Authentication mode: `aad` or `api_key` |
| `api_key` | string | conditional | - | Azure API key (required if `auth_mode: api_key`) |

### `local` (required)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `host` | string | ❌ | `127.0.0.1` | Server bind address |
| `port` | integer | ❌ | `8000` | Server port (1-65535) |
| `api_key` | string | ✅ | - | Local API key for request authentication |

### `pricing` (optional)

Map of deployment names to pricing tiers. Used for cost calculation.

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `<deployment>.input` | float | ✅ | - | EUR per 1000 input tokens |
| `<deployment>.output` | float | ❌ | `0.0` | EUR per 1000 output tokens |

**Note**: If a deployment is not in the pricing map, a warning is logged and the request proceeds with zero cost.

### `limits` (optional)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `daily_cost_cap_eur` | float | ❌ | `5.0` | Daily spending cap in EUR |

### `logging` (required)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `encryption_key` | string | ✅ | - | Base64-encoded 32-byte AES-256 key |
| `compression` | enum | ❌ | `gzip` | Compression: `gzip` or `none` |
| `directory` | string | ❌ | `logs` | Log directory path |

---

## Validation Rules

1. **`azure.endpoint`** must be a valid HTTPS URL
2. **`azure.api_key`** is required when `auth_mode` is `api_key`
3. **`local.port`** must be between 1 and 65535
4. **`logging.encryption_key`** must decode to exactly 32 bytes
5. **`pricing.*.input`** and `pricing.*.output`** must be non-negative

---

## Environment Variable Overrides

The following values can be overridden via environment variables:

| Config Path | Environment Variable | Description |
|-------------|---------------------|-------------|
| `azure.api_key` | `AZURE_OPENAI_API_KEY` | Azure API key |
| `local.api_key` | `LOCAL_API_KEY` | Local API key |
| `logging.encryption_key` | `LOG_ENCRYPTION_KEY` | Encryption key |

Environment variables take precedence over config.yaml values.

---

## Generating an Encryption Key

```bash
# Python one-liner
python -c "from cryptography.hazmat.primitives.ciphers.aead import AESGCM; import base64; print(base64.b64encode(AESGCM.generate_key(256)).decode())"

# Or using openssl
openssl rand -base64 32
```
