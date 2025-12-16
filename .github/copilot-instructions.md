# AzureMiddleware Development Guidelines

Local FastAPI proxy for Azure OpenAI with authentication, encrypted logging, and cost tracking.

## Architecture & Patterns

### Core Components
- **State Management**: `AppState` in `server.py` holds singletons (`config`, `cost_tracker`, `log_writer`, `auth_provider`). Access via `request.app.state.app_state`.
- **Configuration**: Pydantic models in `config.py`. `SecretStr` for keys. Custom validators for Azure endpoints and key lengths.
- **Authentication**: 
  - **Incoming**: `LocalAPIKeyMiddleware` protects this proxy.
  - **Outgoing**: `AADTokenProvider` (Azure Identity) or `APIKeyProvider` for Azure OpenAI.
- **Cost Tracking**: `CostTracker` (`cost/tracker.py`) uses `asyncio.Lock` for thread-safe updates. Persists state by re-reading logs on startup.

### Logging & Encryption
- **Format**: JSONL files in `logs/YYYYMMDD/{username}_YYYYMMDD.jsonl`.
- **Encryption**: AES-256-GCM (`logging/encryption.py`).
  - Fields `request` and `response` are encrypted individually.
  - **Format**: `$enc:BASE64([flags:1][nonce:12][ciphertext:N][tag:16])`.
  - **Compression**: Data >= 100 bytes is automatically GZIP compressed before encryption (Flag bit 0 set). *Note: The `compression` config setting is currently not enforced; behavior is hardcoded.*
- **Privacy**: Embedding vectors are explicitly excluded from logs.

## Development Workflow

### Setup & Run
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Generate encryption key (32 bytes base64)
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"

# Run server
python -m azure_middleware --config config.yaml
```

### Testing Strategy
- **Unit Tests**: `pytest` (fast, mocks external calls).
- **Integration Tests**: `pytest -m integration`.
  - **Requirement**: Requires a running server instance.
  - **Setup**:
    1. Start server: `python -m azure_middleware`
    2. Run tests: `MIDDLEWARE_URL=http://localhost:8000 MIDDLEWARE_API_KEY=... pytest -m integration`
- **Fixtures**: 
  - `tests/conftest.py`: Mocked configs and unit test fixtures.
  - `tests/integration/conftest.py`: Real HTTP clients for integration.

## Key Files
- `azure_middleware/server.py`: App factory and dependency wiring.
- `azure_middleware/config.py`: Configuration schema and validation logic.
- `azure_middleware/logging/encryption.py`: Custom encryption/compression logic.
- `azure_middleware/routes/chat.py`: Example route implementation (streaming, cost tracking, logging).

## Common Tasks
- **Adding Routes**: 
  1. Create router in `routes/`.
  2. Inject `AppState`.
  3. Check `await state.cost_tracker.check_cap()`.
  4. Log via `state.log_writer.write()`.
  5. Register in `server.py`.
- **Debugging**: Logs are encrypted. Use a decryption script (like `decrypt_logs.py`) to inspect `request_body`/`response_body`.
