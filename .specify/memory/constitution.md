# Azure OpenAI Local Middleware Constitution

## Core Principles

### I. API Compatibility First
The middleware MUST be transparent to clients. Any code using the Azure OpenAI SDK should work with zero modifications beyond endpoint URL and API key configuration. Response formats, headers, status codes, and streaming behavior must match Azure OpenAI exactly. When in doubt, preserve Azure's behavior.

### II. Fail-Safe Operations
Request processing MUST NOT fail due to auxiliary features. Logging failures, cost tracking errors, or encryption issues must be handled gracefully—the request proceeds, and errors are recorded separately. Only authentication and rate limiting (cost cap) are blocking concerns.

### III. Async-First Architecture
All I/O operations use async/await patterns. Logging is non-blocking. Cost updates use async locks. The server must handle concurrent requests without blocking. FastAPI + asyncio is the mandatory stack.

### IV. Single Source of Truth
Configuration lives in `config.yaml`. Pricing lives in `config.yaml`. Cost state is reconstructed from log files on startup. No hidden state, no external databases, no environment variable overrides that aren't documented.

### V. Explicit Over Implicit
Unknown endpoints return 501 (not silent failures). Missing configuration causes startup failure with clear messages. Cost cap exceeded returns detailed error with current/limit values. Every error should tell the developer how to fix it.

### VI. Security is Best-Effort
This is an internal single-user tool. Security measures exist to prevent accidents, not attacks. The local API key prevents accidental misuse. Log encryption prevents casual snooping. Do not over-engineer security for this use case.

### VII. Testability
Each component (auth, routing, logging, cost tracking) must be independently testable. Use dependency injection for Azure client, clock, and file system. Mock external services in tests. Integration tests use actual FastAPI test client.

## Technology Stack

- **Language**: Python 3.11+
- **Framework**: FastAPI with Uvicorn
- **Azure SDK**: azure-identity, httpx for async HTTP
- **Configuration**: PyYAML, Pydantic for validation
- **Testing**: pytest, pytest-asyncio, httpx for test client
- **Packaging**: pyproject.toml (PEP 517/518)

## Development Standards

### Code Organization
```
azure_middleware/
├── __init__.py
├── __main__.py          # CLI entry point
├── server.py            # FastAPI app factory
├── config.py            # Configuration loading & validation
├── auth/
│   ├── __init__.py
│   ├── aad.py           # AAD authentication
│   ├── apikey.py        # API key authentication
│   └── local.py         # Local API key validation
├── routes/
│   ├── __init__.py
│   ├── chat.py          # Chat completions
│   ├── embeddings.py    # Embeddings
│   ├── responses.py     # Responses API
│   └── health.py        # GET /health, GET /metrics
├── logging/
│   ├── __init__.py
│   ├── writer.py        # Async JSONL writer
│   └── encryption.py    # Compression & encryption
├── cost/
│   ├── __init__.py
│   ├── calculator.py    # Token-based cost calculation
│   └── tracker.py       # Daily cumulative tracking
└── streaming/
    ├── __init__.py
    └── buffer.py        # Stream accumulation
```

### Error Handling Pattern
```python
# DO: Specific errors with actionable messages
raise HTTPException(
    status_code=429,
    detail={
        "error": "daily_cost_limit_exceeded",
        "current_cost_eur": 5.02,
        "limit_eur": 5.00,
        "message": "Daily cost limit exceeded. Resets at UTC midnight."
    }
)

# DON'T: Generic errors
raise HTTPException(status_code=429, detail="Limit exceeded")
```

### Logging Pattern
```python
# DO: Structured async logging
await log_writer.write(LogEntry(
    timestamp=datetime.utcnow(),
    request=request_data,
    response=response_data,
    cost=calculated_cost,
    cumulative_cost=tracker.daily_total
))

# DON'T: Synchronous logging that blocks requests
```

## Quality Gates

1. **All tests pass** before any merge
2. **Type hints** on all public functions
3. **Docstrings** on all public classes and functions
4. **No hardcoded values**—use config.yaml
5. **Async all the way**—no sync I/O in request handlers

## Governance

This constitution defines the non-negotiable principles for the Azure OpenAI Local Middleware project. Any changes to these principles require explicit documentation of the rationale and impact assessment.

**Version**: 1.0.0 | **Ratified**: 2024-12-14 | **Last Amended**: 2024-12-14
