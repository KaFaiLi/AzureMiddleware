# AzureMiddleware Development Guidelines

Local FastAPI proxy for Azure OpenAI with authentication, encrypted logging, and cost tracking.

## Architecture Overview

```
azure_middleware/
├── server.py          # FastAPI app factory, AppState container
├── config.py          # Pydantic config models, validation
├── dependencies.py    # FastAPI dependency injection
├── auth/              # AAD (azure-identity) or API key auth providers
├── cost/              # CostTracker (async-safe), calculator (EUR/1000 tokens)
├── logging/           # AES-256-GCM encryption, JSONL writer
├── routes/            # chat.py, embeddings.py, responses.py, health.py
└── streaming/         # SSE StreamBuffer for chunked responses
```

**Data Flow**: Client → LocalAPIKeyMiddleware → Route → Azure proxy → CostTracker → LogWriter → JSONL

## Key Patterns

### AppState Pattern
All shared state lives in `AppState` ([server.py](azure_middleware/server.py#L27)):
```python
state = request.app.state.app_state  # Access via get_app_state()
state.config, state.cost_tracker, state.log_writer, state.auth_provider
```

### Config Validation
Pydantic models in [config.py](azure_middleware/config.py) with custom validators:
- `AzureConfig.validate_endpoint()` - must be `https://*.openai.azure.com`
- `LoggingConfig.validate_encryption_key()` - must decode to exactly 32 bytes
- Use `SecretStr` for sensitive fields (api keys, encryption key)

### Cost Tracking
- `CostTracker` uses `asyncio.Lock` for thread-safe updates
- Pricing in `config.yaml` as EUR per 1000 tokens
- Pre-request cap check via `await cost_tracker.check_cap()`
- Persisted via JSONL logs, recovered on startup

### Logging
- Path pattern: `logs/YYYYMMDD/{username}_YYYYMMDD.jsonl`
- Request/response encrypted with AES-256-GCM, metadata plaintext
- Embedding vectors NOT logged (space savings per spec)

## Commands

```bash
# Install (dev mode)
pip install -e ".[dev]"

# Run server
python -m azure_middleware              # or: azure-middleware
azure-middleware --config /path/to/config.yaml

# Tests
pytest                                  # Unit tests
pytest -m integration                   # Requires running server
pytest -m thinking                      # Thinking model tests
pytest -m embedding                     # Embedding model tests

# Code quality
ruff check .
mypy azure_middleware
```

## Testing

Integration tests use real Azure endpoints via running middleware:
```bash
# Terminal 1: Start server
python -m azure_middleware

# Terminal 2: Run integration tests
MIDDLEWARE_URL=http://localhost:8000 MIDDLEWARE_API_KEY=your-key pytest -m integration
```

Test fixtures in [tests/conftest.py](tests/conftest.py) provide mocked configs. Integration fixtures in [tests/integration/conftest.py](tests/integration/conftest.py) use env vars.

## Adding New Routes

1. Create router in `azure_middleware/routes/`
2. Use `get_app_state(request)` for state access
3. Check cost cap before Azure call: `await cost_tracker.check_cap()`
4. Use `build_azure_url()` and `filter_request_headers()` from [chat.py](azure_middleware/routes/chat.py)
5. Log via `log_writer.write()` with `LogEntry`
6. Register router in [server.py](azure_middleware/server.py)

## Configuration

See [config.example.yaml](config.example.yaml) for full schema. Key sections:
- `azure`: endpoint, deployment, auth_mode (aad|api_key)
- `local`: host, port, api_key (protects middleware)
- `pricing`: per-model EUR/1000 tokens
- `logging`: encryption_key (base64 32-byte), compression
