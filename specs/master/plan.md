# Implementation Plan: Azure OpenAI Local Middleware

**Branch**: `master` | **Date**: 2025-12-14 | **Spec**: [spec.md](../../.specify/memory/spec.md)
**Input**: Feature specification from `.specify/memory/spec.md`

## Summary

A Python package providing a local FastAPI server that acts as a transparent routing layer to Azure OpenAI. The middleware centralizes authentication (AAD or API key), enforces daily cost caps in EUR, and logs all requests/responses in encrypted JSONL format—all while maintaining full Azure OpenAI SDK compatibility for chat completions, embeddings, and the Responses API.

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: FastAPI, Uvicorn, httpx (async HTTP), azure-identity, PyYAML, Pydantic, cryptography (AES-256-GCM)  
**Storage**: JSONL files in `logs/YYYYMMDD/` directory (no database)  
**Testing**: pytest, pytest-asyncio, httpx (TestClient)  
**Target Platform**: Windows (single-user local development)  
**Project Type**: Single Python package with CLI entry point  
**Performance Goals**: 10 concurrent requests, <100ms streaming latency overhead, <5s startup with 100MB logs  
**Constraints**: Async-only I/O, best-effort logging (non-blocking), cost cap enforcement pre-request  
**Scale/Scope**: Single user, single machine, ~100 requests/day typical usage

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. API Compatibility First | ✅ PASS | Design preserves Azure OpenAI response formats, headers, status codes exactly |
| II. Fail-Safe Operations | ✅ PASS | Logging is async/best-effort; only auth and cost cap block requests |
| III. Async-First Architecture | ✅ PASS | FastAPI + asyncio mandatory; httpx for async HTTP; async locks for cost |
| IV. Single Source of Truth | ✅ PASS | All config in config.yaml; cost state reconstructed from logs |
| V. Explicit Over Implicit | ✅ PASS | 501 for unknown endpoints; clear error messages with current/limit values |
| VI. Security is Best-Effort | ✅ PASS | Local API key prevents accidents; AES-256-GCM for log encryption |
| VII. Testability | ✅ PASS | DI for Azure client, clock, filesystem; pytest-asyncio for integration tests |

**Gate Result**: ✅ PASS - All constitution principles satisfied. Proceed to Phase 0.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
azure_middleware/
├── __init__.py
├── __main__.py          # CLI entry point (python -m azure_middleware)
├── server.py            # FastAPI app factory
├── config.py            # Configuration loading & Pydantic validation
├── auth/
│   ├── __init__.py
│   ├── aad.py           # AAD token acquisition via azure-identity
│   ├── apikey.py        # API key header injection
│   └── local.py         # Local API key validation middleware
├── routes/
│   ├── __init__.py
│   ├── chat.py          # POST /openai/deployments/{deployment}/chat/completions
│   ├── embeddings.py    # POST /openai/deployments/{deployment}/embeddings
│   ├── responses.py     # POST /openai/deployments/{deployment}/responses
│   └── health.py        # GET /health, GET /metrics
├── logging/
│   ├── __init__.py
│   ├── writer.py        # Async JSONL writer with queue
│   └── encryption.py    # gzip + AES-256-GCM for request/response fields
├── cost/
│   ├── __init__.py
│   ├── calculator.py    # Token-based cost calculation from response
│   └── tracker.py       # Daily cumulative tracking with async lock
└── streaming/
    ├── __init__.py
    └── buffer.py        # SSE chunk accumulation for logging

tests/
├── conftest.py          # Shared fixtures (mock Azure, test config)
├── unit/
│   ├── test_config.py
│   ├── test_cost_calculator.py
│   ├── test_encryption.py
│   └── test_stream_buffer.py
├── integration/
│   ├── test_chat_endpoint.py
│   ├── test_embeddings_endpoint.py
│   ├── test_streaming.py
│   └── test_cost_enforcement.py
└── contract/
    └── test_sdk_compatibility.py  # Azure OpenAI SDK compatibility tests
```

**Structure Decision**: Single Python package following constitution's Code Organization. Tests separated into unit (no I/O), integration (FastAPI TestClient), and contract (SDK compatibility).

## Complexity Tracking

> No constitution violations requiring justification. All principles satisfied.

---

## Phase Outputs

### Phase 0: Research (Complete)

- [research.md](research.md) - FastAPI proxy patterns, AES-256-GCM encryption, async cost tracking

### Phase 1: Design & Contracts (Complete)

- [data-model.md](data-model.md) - Entity definitions, state diagrams
- [contracts/openapi.yaml](contracts/openapi.yaml) - OpenAPI 3.1 specification
- [contracts/config-schema.md](contracts/config-schema.md) - Configuration file schema
- [quickstart.md](quickstart.md) - Installation and usage guide

### Phase 2: Tasks (Pending)

- Run `/speckit.tasks` to generate implementation tasks

---

## Constitution Re-Check (Post-Design)

| Principle | Status | Design Artifact |
|-----------|--------|-----------------|
| I. API Compatibility First | ✅ PASS | OpenAPI spec preserves all Azure endpoints/schemas |
| II. Fail-Safe Operations | ✅ PASS | LogEntry model has optional fields; async writer |
| III. Async-First Architecture | ✅ PASS | All routes async; httpx AsyncClient; asyncio.Lock |
| IV. Single Source of Truth | ✅ PASS | Config schema fully documented; no hidden state |
| V. Explicit Over Implicit | ✅ PASS | CostCapError schema includes all details |
| VI. Security is Best-Effort | ✅ PASS | AES-256-GCM for logs; simple local API key |
| VII. Testability | ✅ PASS | Test structure defined; mocks planned |

**Post-Design Gate**: ✅ PASS - Ready for implementation.
