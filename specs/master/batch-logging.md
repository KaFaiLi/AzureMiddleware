# High-Performance Batch Logging

## Overview

The AzureMiddleware logging system uses **asynchronous queue-based batch writes** to optimize performance in high-latency environments, such as network drives or cloud storage.

## Architecture

### Components

1. **Async Queue**: In-memory `asyncio.Queue` buffers log entries
2. **Background Task**: Dedicated coroutine consumes queue and writes batches
3. **Batch Grouping**: Entries are grouped by date before writing
4. **Graceful Shutdown**: Remaining entries are flushed on application shutdown

### Flow

```
API Request → LogWriter.write() → Queue.put() → Returns immediately
                                         ↓
                                  Background Task
                                         ↓
                              Collect batch (up to N entries or timeout)
                                         ↓
                              Group by date → Write to disk
```

## Configuration

### config.yaml

```yaml
logging:
  encryption_key: "..."
  compression: "gzip"
  directory: "logs"
  
  # Batch write settings
  batch_size: 10          # Max entries per batch (1-1000)
  batch_timeout: 1.0      # Max seconds before flushing partial batch (0.1-60.0)
```

### Parameters

- **batch_size**: Maximum number of log entries collected before writing
  - Lower values: More frequent writes, lower latency for log visibility
  - Higher values: Better throughput, more efficient for high-latency storage
  - Recommended: 10-50 for network drives, 5-10 for local storage

- **batch_timeout**: Maximum time (seconds) to wait before flushing a partial batch
  - Ensures timely writes even under low request volume
  - Prevents log entries from sitting in memory indefinitely
  - Recommended: 0.5-2.0 seconds

## Performance Benefits

### Before (Synchronous Writes)

- Each API request blocks on disk I/O
- High-latency storage (1-2s) = 1-2s added to each request
- Concurrent requests queue up behind slow writes
- Throughput limited by storage speed

### After (Async Batch Writes)

- API requests return immediately after enqueueing
- Multiple entries written in single I/O operation
- 10 entries × 1.5s latency = 150ms per entry (10× improvement)
- Requests not blocked by slow storage

### Example Scenario

**Network drive with 1.5s write latency:**

| Configuration | Requests/sec | Avg Request Latency |
|--------------|-------------|---------------------|
| Synchronous  | 0.67        | 1500ms + processing |
| Async (batch=10) | 10+     | processing only     |

## Lifecycle

### Startup

```python
# In server.py lifespan
await state.log_writer.start()
```

- Creates background task
- Begins consuming queue

### Runtime

```python
# In route handlers
await state.log_writer.write(entry)
```

- Enqueues entry (non-blocking)
- Returns immediately

### Shutdown

```python
# In server.py lifespan
await state.log_writer.stop()
```

- Signals background task to stop
- Flushes remaining queue entries
- Waits for final writes to complete

## Error Handling

- **Queue Full**: Logs warning, drops entry (best-effort semantics)
- **Write Failure**: Logs error, continues processing queue
- **Background Task Crash**: Logged with stack trace, but doesn't affect API requests

## Testing

Run batch logging tests:

```bash
pytest tests/test_batch_logging.py -v
```

Tests cover:
- Batch size enforcement
- Timeout-based flushing
- Concurrent writes from multiple coroutines
- Graceful shutdown with queue flush
- Date-based file grouping

## Monitoring

Enable debug logging to monitor batch behavior:

```python
import logging
logging.getLogger("azure_middleware.logging.writer").setLevel(logging.DEBUG)
```

Log messages:
- `"Log writer started (batch_size=..., timeout=...s)"`
- `"Wrote N log entries to {path}"`
- `"Flushing N remaining log entries"` (on shutdown)

## Tuning Recommendations

### Local SSD/NVMe
```yaml
batch_size: 5
batch_timeout: 0.5
```
- Low latency, prioritize log freshness

### Network Drive (LAN)
```yaml
batch_size: 20
batch_timeout: 1.0
```
- Moderate latency, balance throughput and freshness

### High-Latency Network Storage
```yaml
batch_size: 50
batch_timeout: 2.0
```
- Maximize throughput, accept slight delay in log visibility

### Very High Request Rate
```yaml
batch_size: 100
batch_timeout: 0.5
```
- Large batches fill quickly, timeout rarely triggered

## Implementation Details

### Thread Safety

- Uses `asyncio.Lock` for file writes (not OS-level locks)
- Single background task ensures sequential writes per file
- Multiple date files can be written in parallel (future enhancement)

### Memory Usage

- Queue grows unbounded if writes can't keep up
- Monitor queue size: `log_writer._queue.qsize()`
- Consider adding max queue size with back-pressure

### Date Rollover

- Entries are grouped by date before writing
- Midnight crossing handled gracefully
- Each date gets separate log file

## Future Enhancements

1. **Max Queue Size**: Implement back-pressure when queue grows too large
2. **Parallel Writes**: Write to multiple date files concurrently
3. **Write Buffering**: Use in-memory buffer before thread pool I/O
4. **Metrics Export**: Expose queue size, batch stats to `/metrics` endpoint
5. **Compression in Background**: Move GZIP compression to background task
