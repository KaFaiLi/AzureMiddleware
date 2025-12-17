# Testing Guide: Batch Logging and Graceful Shutdown

## Overview

This guide explains how to test the batch logging and graceful shutdown features to ensure they work correctly.

## Testing Approaches

### 1. Automated Unit Tests ✅

**Location**: `tests/test_batch_logging.py`, `tests/test_logging_concurrency.py`

**What they test**:
- Batch size enforcement
- Timeout-based flushing
- Concurrent writes from multiple coroutines
- Graceful shutdown with queue flush
- Date-based file grouping
- Write lock prevents corruption

**Run**:
```bash
# All batch logging tests
pytest tests/test_batch_logging.py -v

# All concurrency tests (updated for batch logging)
pytest tests/test_logging_concurrency.py -v
```

**Expected results**: All tests pass (15 tests total)

---

### 2. Integration Tests (API Key or AAD) ✅

**Location**: `tests/integration/`

**Updated Features**:
- Support for both `api_key` and `aad` authentication modes
- Configurable via `MIDDLEWARE_AUTH_MODE` environment variable
- Tests work with real Azure OpenAI backend

**Run with API Key**:
```bash
MIDDLEWARE_URL=http://localhost:8000 \
MIDDLEWARE_API_KEY=your-local-key \
MIDDLEWARE_AUTH_MODE=api_key \
pytest tests/integration/ -v -m integration
```

**Run with AAD**:
```bash
# Ensure server is configured with auth_mode: aad
MIDDLEWARE_URL=http://localhost:8000 \
MIDDLEWARE_API_KEY=your-local-key \
MIDDLEWARE_AUTH_MODE=aad \
pytest tests/integration/ -v -m integration
```

**See**: `tests/integration/README.md` for complete setup instructions

---

### 3. Manual Batch Logging Test 🔧

**Location**: `tests/manual_batch_test.py`

**What it tests**:
- Real server with high batch settings
- Logs stay in memory (not immediately written)
- Ctrl+C triggers graceful shutdown
- All pending logs are flushed to disk

**Setup**:
1. Configure `config.yaml` with high batch settings:
   ```yaml
   logging:
     batch_size: 50
     batch_timeout: 10.0
   ```

2. Start server:
   ```bash
   python -m azure_middleware
   ```

3. In another terminal, run test:
   ```bash
   python tests/manual_batch_test.py
   ```

4. Follow prompts:
   - Script sends 5 requests (< batch_size)
   - Logs are queued in memory
   - Press Ctrl+C to test graceful shutdown
   - Script verifies all logs were written

**Expected result**: All 5 requests logged to disk after Ctrl+C

---

### 4. Performance Test (High-Latency Storage) 📊

**Scenario**: Simulate network drive with high latency

**Setup**:
1. Configure aggressive batching:
   ```yaml
   logging:
     batch_size: 50
     batch_timeout: 2.0
   ```

2. Send many concurrent requests
3. Monitor throughput and log write patterns

**Method 1: Using integration tests**:
```bash
# Run integration tests in parallel
pytest tests/integration/ -v -n 4
```

**Method 2: Custom load test**:
```python
import asyncio
import httpx

async def send_request(client, i):
    response = await client.post(
        "/openai/deployments/gpt-4.1-nano/chat/completions",
        json={"messages": [{"role": "user", "content": f"Request {i}"}]}
    )
    return response.status_code

async def load_test():
    async with httpx.AsyncClient(
        base_url="http://localhost:8000",
        headers={"api-key": "your-key"}
    ) as client:
        tasks = [send_request(client, i) for i in range(100)]
        results = await asyncio.gather(*tasks)
        print(f"Completed {len(results)} requests")

asyncio.run(load_test())
```

**Monitor**:
```bash
# Enable debug logging to see batch writes
export AZURE_MIDDLEWARE_LOG_LEVEL=DEBUG
python -m azure_middleware
```

Look for log messages:
- `"Wrote N log entries to {path}"` - Shows batch size
- `"Flushing N remaining log entries"` - On shutdown

---

## Verification Checklist

### ✅ Batch Logging Works
- [ ] Unit tests pass (`test_batch_logging.py`)
- [ ] Multiple requests are written in single I/O operation
- [ ] Timeout triggers flush even for partial batches
- [ ] Entries grouped by date before writing

### ✅ Graceful Shutdown Works
- [ ] Ctrl+C triggers FastAPI shutdown event
- [ ] All queued logs are flushed before exit
- [ ] Server logs show "Flushing N remaining log entries"
- [ ] Log files contain all expected entries

### ✅ Signal Handling Works
- [ ] SIGINT (Ctrl+C) triggers graceful shutdown
- [ ] SIGTERM (kill) triggers graceful shutdown
- [ ] Server prints "Received signal N, initiating graceful shutdown..."
- [ ] Background log writer task completes before exit

### ✅ Integration Tests Work
- [ ] Tests pass with `api_key` auth mode
- [ ] Tests pass with `aad` auth mode
- [ ] Both modes write logs correctly
- [ ] Cost tracking works with both modes

---

## Troubleshooting

### Logs Not Flushed on Shutdown

**Symptom**: Log count doesn't increase after graceful shutdown

**Possible causes**:
1. Server killed with `kill -9` or Task Manager (forced termination)
2. Signal handler not registered (check __main__.py)
3. Background task not started (check lifespan in server.py)

**Solution**: Ensure Ctrl+C is used for graceful shutdown

---

### Tests Fail with "Server not running"

**Symptom**: `pytest.skip: Middleware server not running`

**Solution**:
```bash
# Start server in one terminal
python -m azure_middleware

# Run tests in another terminal
pytest tests/integration/ -v
```

---

### Integration Tests Fail with AAD

**Symptom**: `401 Unauthorized` or `403 Forbidden`

**Solution**:
1. Verify server `config.yaml` has `auth_mode: aad`
2. Check Azure credentials:
   ```bash
   az login
   az account show
   ```
3. Verify service principal has permissions to Azure OpenAI resource

---

### Batch Not Writing

**Symptom**: Logs not appearing in files during test

**Possible causes**:
1. `batch_timeout` is too high
2. Not enough requests to reach `batch_size`
3. Background task not started

**Solution**:
- Lower `batch_timeout` to 0.5-1.0 seconds for testing
- Send more requests or trigger Ctrl+C to flush

---

## Performance Expectations

### Before Batch Logging
| Metric | Value |
|--------|-------|
| Latency per request | Processing + I/O (e.g., 1.5s) |
| Throughput (1.5s I/O) | 0.67 req/s |
| Concurrent impact | Linear degradation |

### After Batch Logging
| Metric | Value |
|--------|-------|
| Latency per request | Processing only (~ms) |
| Throughput (1.5s I/O, batch=10) | 10+ req/s |
| Concurrent impact | Minimal (queue-based) |

---

## CI/CD Integration

For automated testing in GitHub Actions or similar:

```yaml
name: Test Batch Logging

jobs:
  test-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run unit tests
        run: pytest tests/test_batch_logging.py tests/test_logging_concurrency.py -v

  test-integration-api-key:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start middleware
        run: python -m azure_middleware &
        env:
          CONFIG_YAML: ${{ secrets.CONFIG_YAML }}
      - name: Run integration tests (API Key)
        run: |
          pytest tests/integration/ -v -m integration
        env:
          MIDDLEWARE_AUTH_MODE: api_key
          MIDDLEWARE_API_KEY: ${{ secrets.MIDDLEWARE_API_KEY }}

  test-integration-aad:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Start middleware (AAD mode)
        run: python -m azure_middleware &
        env:
          CONFIG_YAML: ${{ secrets.CONFIG_YAML_AAD }}
      - name: Run integration tests (AAD)
        run: |
          pytest tests/integration/ -v -m integration
        env:
          MIDDLEWARE_AUTH_MODE: aad
          MIDDLEWARE_API_KEY: ${{ secrets.MIDDLEWARE_API_KEY }}
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

---

## Summary

The testing strategy ensures:

1. **Batch logging works correctly** (unit tests)
2. **Graceful shutdown flushes logs** (manual test)
3. **Both auth modes are supported** (integration tests)
4. **Performance meets expectations** (load tests)

All components are tested at different levels:
- Unit: Fast, isolated, comprehensive
- Integration: Real server, real Azure backend
- Manual: End-to-end user experience
- Performance: Load and latency verification
