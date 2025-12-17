# Integration Tests

Integration tests verify the middleware works correctly with a real Azure OpenAI backend.

## Prerequisites

1. **Running Middleware Server**
   ```bash
   python -m azure_middleware --config config.yaml --local local.yaml
   ```

2. **Valid Azure OpenAI Credentials** in your `config.yaml`

3. **Model Deployments** matching your test configuration

## Running Tests

### With API Key Authentication (Default)

1. Configure your `config.yaml` with API key auth:
   ```yaml
   azure:
     auth_mode: api_key
     api_key: "your-azure-api-key"
   ```

2. Start the middleware server

3. Run tests:
   ```bash
   # Use default settings
   pytest tests/integration/ -v -m integration
   
   # Or explicitly set environment variables
   MIDDLEWARE_URL=http://localhost:8000 \
   MIDDLEWARE_API_KEY=your-local-key \
   MIDDLEWARE_AUTH_MODE=api_key \
   pytest tests/integration/ -v -m integration
   ```

### With Azure AD (AAD) Authentication

1. Configure your `config.yaml` with AAD auth:
   ```yaml
   azure:
     auth_mode: aad
     endpoint: "https://your-resource.openai.azure.com"
     
     # Option 1: Use DefaultAzureCredential (recommended)
     # Leave tenant_id, client_id, client_secret empty
     
     # Option 2: Use Service Principal
     tenant_id: "your-tenant-id"
     client_id: "your-client-id"
     client_secret: "your-client-secret"
   ```

2. Ensure Azure credentials are available:
   ```bash
   # For DefaultAzureCredential, login via Azure CLI:
   az login
   
   # Or set environment variables for Service Principal:
   export AZURE_TENANT_ID="..."
   export AZURE_CLIENT_ID="..."
   export AZURE_CLIENT_SECRET="..."
   ```

3. Start the middleware server

4. Run tests:
   ```bash
   MIDDLEWARE_URL=http://localhost:8000 \
   MIDDLEWARE_API_KEY=your-local-key \
   MIDDLEWARE_AUTH_MODE=aad \
   pytest tests/integration/ -v -m integration
   ```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MIDDLEWARE_URL` | Middleware server endpoint | `http://localhost:8000` |
| `MIDDLEWARE_API_KEY` | Local API key for middleware | `test-local-key-12345` |
| `MIDDLEWARE_AUTH_MODE` | Auth mode: `api_key` or `aad` | `api_key` |
| `AZURE_API_VERSION` | Azure OpenAI API version | `2024-02-01` |
| `CHAT_MODEL` | Chat model deployment name | `gpt-4.1-nano` |
| `THINKING_MODEL` | Thinking model deployment name | `gpt-5-nano` |
| `EMBEDDING_MODEL` | Embedding model deployment name | `text-embedding-3-small` |

## Model-Specific Tests

Run tests for specific model types:

```bash
# Only chat model tests
pytest tests/integration/test_multimodel.py::TestChatModels -v

# Only thinking model tests
pytest tests/integration/test_thinking.py -v -m thinking

# Only embedding tests
pytest tests/integration/test_multimodel.py::TestEmbeddingModels -v
```

## Test Coverage

- **test_multimodel.py**: Chat models, thinking models, embeddings
- **test_openai_client.py**: OpenAI SDK compatibility
- **test_thinking.py**: Thinking/reasoning model specific features

## Troubleshooting

### Server Not Running
```
pytest.skip: Middleware server not running at http://localhost:8000
```
**Solution**: Start the middleware server first

### Authentication Errors
```
401 Unauthorized
```
**Solution**: 
- For API key: Check `MIDDLEWARE_API_KEY` matches `local.api_key` in config
- For AAD: Verify Azure credentials are valid (run `az account show`)

### Model Not Found
```
404 Not Found: deployment 'gpt-4.1-nano' not found
```
**Solution**: Update environment variables to match your actual deployment names

### Cost Cap Exceeded
```
429 Too Many Requests: Daily cost cap exceeded
```
**Solution**: 
- Increase `limits.daily_cost_cap_eur` in config.yaml
- Wait for daily reset (midnight UTC)
- Or restart server (resets cost tracking)

## Testing Both Auth Modes

To thoroughly test your middleware, run integration tests with both auth modes:

```bash
# Test with API key
MIDDLEWARE_AUTH_MODE=api_key pytest tests/integration/ -v

# Reconfigure server for AAD, then test
MIDDLEWARE_AUTH_MODE=aad pytest tests/integration/ -v
```

**Note**: You need to restart the middleware server with the appropriate `auth_mode` in `config.yaml` before running tests with each mode.

## CI/CD Integration

For automated testing in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Run Integration Tests (API Key)
  env:
    MIDDLEWARE_URL: http://localhost:8000
    MIDDLEWARE_API_KEY: ${{ secrets.MIDDLEWARE_API_KEY }}
    MIDDLEWARE_AUTH_MODE: api_key
  run: pytest tests/integration/ -v -m integration

- name: Run Integration Tests (AAD)
  env:
    MIDDLEWARE_URL: http://localhost:8000
    MIDDLEWARE_API_KEY: ${{ secrets.MIDDLEWARE_API_KEY }}
    MIDDLEWARE_AUTH_MODE: aad
    AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
    AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
    AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  run: pytest tests/integration/ -v -m integration
```

## Performance Testing

For performance/load testing with batch logging:

```bash
# Configure high batch settings in config.yaml
logging:
  batch_size: 50
  batch_timeout: 2.0

# Run many concurrent requests
pytest tests/integration/ -v -n 4  # 4 parallel workers
```

Monitor the middleware logs to verify batching behavior:
- Look for "Wrote N log entries to {path}" messages
- Check that batches are sized correctly
