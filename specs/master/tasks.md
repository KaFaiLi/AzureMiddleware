# Tasks: Azure OpenAI Local Middleware

**Input**: Design documents from `/specs/master/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Tests**: Not explicitly requested in specification. Test tasks omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Single Python package**: `azure_middleware/` at repository root
- **Tests**: `tests/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependencies, and basic structure

- [X] T001 Create project structure with pyproject.toml, README.md, and config.example.yaml at repository root
- [X] T002 [P] Create azure_middleware/__init__.py with package version
- [X] T003 [P] Create azure_middleware/__main__.py with CLI entry point (python -m azure_middleware)
- [X] T004 [P] Create tests/conftest.py with shared pytest fixtures

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement configuration loading with Pydantic validation in azure_middleware/config.py
- [X] T006 [P] Implement AES-256-GCM encryption/decryption in azure_middleware/logging/encryption.py
- [X] T007 [P] Implement async JSONL log writer in azure_middleware/logging/writer.py
- [X] T008 [P] Implement cost calculator (tokens to EUR) in azure_middleware/cost/calculator.py
- [X] T009 Implement async cost tracker with lock in azure_middleware/cost/tracker.py
- [X] T010 [P] Implement AAD token provider in azure_middleware/auth/aad.py
- [X] T011 [P] Implement API key auth provider in azure_middleware/auth/apikey.py
- [X] T012 Implement local API key validation middleware in azure_middleware/auth/local.py
- [X] T013 Implement FastAPI app factory with lifespan in azure_middleware/server.py
- [X] T014 [P] Implement stream buffer for SSE accumulation in azure_middleware/streaming/buffer.py
- [X] T015 [P] Implement health endpoint (GET /health) in azure_middleware/routes/health.py
- [X] T016 Implement metrics endpoint (GET /metrics) in azure_middleware/routes/health.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Basic Chat Completion (Priority: P1) 🎯 MVP

**Goal**: Developer sends chat completion via SDK → middleware proxies to Azure → returns identical response

**Independent Test**: Send chat completion via Azure OpenAI Python SDK to localhost:8000, verify response format matches direct Azure call

### Implementation for User Story 1

- [X] T017 [US1] Create base proxy utilities (header filtering, URL building) in azure_middleware/routes/__init__.py
- [X] T018 [US1] Implement chat completions endpoint (non-streaming) in azure_middleware/routes/chat.py
- [X] T019 [US1] Add request/response logging to chat completions in azure_middleware/routes/chat.py
- [X] T020 [US1] Add cost calculation and tracking to chat completions in azure_middleware/routes/chat.py
- [X] T021 [US1] Add 401 Unauthorized handling for invalid/missing local API key in azure_middleware/routes/chat.py
- [X] T022 [US1] Add 502 Bad Gateway handling for Azure unreachable in azure_middleware/routes/chat.py
- [X] T023 [US1] Add transparent error forwarding from Azure in azure_middleware/routes/chat.py

**Checkpoint**: User Story 1 complete - non-streaming chat completions work with logging and cost tracking

---

## Phase 4: User Story 2 - Streaming Chat Completion (Priority: P1)

**Goal**: Developer sends streaming chat completion → receives SSE chunks immediately → middleware logs only final response

**Independent Test**: Send streaming request, verify tokens arrive incrementally, verify log has single complete entry

### Implementation for User Story 2

- [X] T024 [US2] Implement streaming detection from request body in azure_middleware/routes/chat.py
- [X] T025 [US2] Implement SSE streaming response with chunk forwarding in azure_middleware/routes/chat.py
- [X] T026 [US2] Implement stream buffering and final response reconstruction in azure_middleware/routes/chat.py
- [X] T027 [US2] Add logging for completed streams (single entry with full response) in azure_middleware/routes/chat.py
- [X] T028 [US2] Handle interrupted streams with partial logging and error indicator in azure_middleware/routes/chat.py

**Checkpoint**: User Story 2 complete - streaming chat completions work with correct logging behavior

---

## Phase 5: User Story 3 - Daily Cost Tracking and Enforcement (Priority: P1)

**Goal**: Middleware enforces daily spending cap, blocks requests when exceeded, survives restarts

**Independent Test**: Set €0.01 cap, make requests until exceeded, verify HTTP 429 with clear message

### Implementation for User Story 3

- [X] T029 [US3] Implement pre-request cost cap check in azure_middleware/cost/tracker.py
- [X] T030 [US3] Implement HTTP 429 response with cost details in azure_middleware/routes/chat.py
- [X] T031 [US3] Implement startup cost reconstruction from last log line in azure_middleware/cost/tracker.py
- [X] T032 [US3] Implement UTC midnight cost reset logic in azure_middleware/cost/tracker.py
- [X] T033 [US3] Add Retry-After header calculation (seconds until midnight) in azure_middleware/cost/tracker.py

**Checkpoint**: User Story 3 complete - cost enforcement works, survives restarts, resets at midnight

---

## Phase 6: User Story 4 - Request/Response Logging (Priority: P1)

**Goal**: All API interactions logged in encrypted JSONL with plaintext metadata

**Independent Test**: Make API calls, verify JSONL entries have correct fields, verify encryption works

### Implementation for User Story 4

- [X] T034 [US4] Implement log entry serialization with encrypted fields in azure_middleware/logging/writer.py
- [X] T035 [US4] Implement log directory structure (logs/YYYYMMDD/) in azure_middleware/logging/writer.py
- [X] T036 [US4] Implement Windows username detection in azure_middleware/logging/writer.py
- [X] T037 [US4] Implement best-effort logging (failures don't block requests) in azure_middleware/logging/writer.py
- [X] T038 [US4] Create decrypt CLI command in azure_middleware/decrypt.py

**Checkpoint**: User Story 4 complete - comprehensive logging with encryption and decryption utility

---

## Phase 7: User Story 5 - Embeddings API Support (Priority: P2)

**Goal**: Developer generates embeddings via SDK with full compatibility

**Independent Test**: Send embeddings request via SDK, verify response format matches Azure

### Implementation for User Story 5

- [X] T039 [US5] Implement embeddings endpoint in azure_middleware/routes/embeddings.py
- [X] T040 [US5] Add cost tracking for embeddings (input tokens only) in azure_middleware/routes/embeddings.py
- [X] T041 [US5] Add logging for embeddings (request only, no response) in azure_middleware/routes/embeddings.py

**Checkpoint**: User Story 5 complete - embeddings work with SDK compatibility

---

## Phase 8: User Story 6 - Responses API Support (Priority: P2)

**Goal**: Developer uses Responses API through middleware

**Independent Test**: Send Responses API request, verify correct proxying

### Implementation for User Story 6

- [X] T042 [US6] Implement responses endpoint in azure_middleware/routes/responses.py
- [X] T043 [US6] Add cost tracking for responses in azure_middleware/routes/responses.py
- [X] T044 [US6] Add logging for responses in azure_middleware/routes/responses.py

**Checkpoint**: User Story 6 complete - Responses API works

---

## Phase 9: User Story 7 - Configuration via YAML (Priority: P2)

**Goal**: All settings configurable via config.yaml without code changes

**Independent Test**: Modify config.yaml, restart server, verify behavior changes

### Implementation for User Story 7

- [X] T045 [US7] Add config file path detection (current dir, then home) in azure_middleware/config.py
- [X] T046 [US7] Add environment variable overrides in azure_middleware/config.py
- [X] T047 [US7] Add clear startup error messages for config problems in azure_middleware/config.py
- [X] T048 [US7] Add config validation for encryption key length in azure_middleware/config.py

**Checkpoint**: User Story 7 complete - flexible configuration with clear error handling

---

## Phase 10: User Story 8 - Unknown Endpoint Rejection (Priority: P3)

**Goal**: Unsupported endpoints return HTTP 501 with helpful message

**Independent Test**: Send request to /v1/images, verify HTTP 501 with supported endpoint list

### Implementation for User Story 8

- [X] T049 [US8] Implement catch-all route returning 501 in azure_middleware/server.py
- [X] T050 [US8] Add supported endpoints list to 501 response body in azure_middleware/server.py

**Checkpoint**: User Story 8 complete - explicit rejection of unknown endpoints

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and refinements

- [X] T051 [P] Update README.md with installation and usage instructions
- [X] T052 [P] Create config.example.yaml with documented settings
- [X] T053 Run quickstart.md validation end-to-end
- [X] T054 Add package __init__.py exports for public API

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 - BLOCKS all user stories
- **User Stories (Phases 3-10)**: All depend on Phase 2 completion
  - US1-US4 (P1 priority) should be completed first
  - US5-US7 (P2 priority) can follow
  - US8 (P3 priority) last
- **Polish (Phase 11)**: After all desired user stories

### User Story Dependencies

- **US1 (Basic Chat)**: Foundation only - MVP starting point
- **US2 (Streaming)**: Extends US1's chat endpoint
- **US3 (Cost Enforcement)**: Uses US1's cost tracking hooks
- **US4 (Logging)**: Enhances US1's logging foundation
- **US5 (Embeddings)**: Foundation only - independent of chat
- **US6 (Responses API)**: Foundation only - independent of chat
- **US7 (Configuration)**: Foundation only - enhances config module
- **US8 (501 Rejection)**: Foundation only - server-level catch-all

### Parallel Opportunities

Setup Phase:
```bash
# Run in parallel (T002, T003, T004):
T002: azure_middleware/__init__.py
T003: azure_middleware/__main__.py
T004: tests/conftest.py
```

Foundational Phase:
```bash
# Run in parallel (T006, T007, T008, T010, T011, T014, T015):
T006: azure_middleware/logging/encryption.py
T007: azure_middleware/logging/writer.py
T008: azure_middleware/cost/calculator.py
T010: azure_middleware/auth/aad.py
T011: azure_middleware/auth/apikey.py
T014: azure_middleware/streaming/buffer.py
T015: azure_middleware/routes/health.py
```

After Phase 2, these user stories can proceed in parallel:
```bash
# Different developers can work on:
US5 (Embeddings) - independent module
US6 (Responses) - independent module
US7 (Config enhancements) - independent module
```

---

## Implementation Strategy

### MVP First (User Stories 1-4)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL)
3. Complete Phase 3: US1 Basic Chat → Test independently
4. Complete Phase 4: US2 Streaming → Test independently
5. Complete Phase 5: US3 Cost Enforcement → Test independently
6. Complete Phase 6: US4 Logging → Test independently
7. **STOP and VALIDATE**: Full MVP with chat, streaming, cost cap, logging

### Incremental Delivery

Each user story adds value without breaking previous stories:
- MVP: Chat + Streaming + Costs + Logging
- Add Embeddings → broader API coverage
- Add Responses API → newer API support
- Add Config enhancements → better UX
- Add 501 rejection → cleaner error handling

---

## Notes

- All tasks follow async-first architecture (Constitution Principle III)
- Logging is best-effort/non-blocking (Constitution Principle II)
- API compatibility is highest priority (Constitution Principle I)
- Each task includes exact file path for implementation
- [P] tasks can run in parallel within their phase
- [US#] labels map tasks to user stories for traceability
