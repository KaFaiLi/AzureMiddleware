# Feature Specification: Azure OpenAI Local Middleware

**Feature Branch**: `main`  
**Created**: 2024-12-14  
**Status**: Draft  
**Input**: User description: "Python package providing a local FastAPI server acting as a transparent routing layer to Azure OpenAI with authentication, logging, and cost tracking."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Basic Chat Completion Request (Priority: P1)

A developer wants to use the Azure OpenAI SDK to send a chat completion request through the local middleware, receiving responses exactly as if they were communicating directly with Azure OpenAI.

**Why this priority**: This is the core value proposition—transparent proxying with full SDK compatibility. Without this, the middleware has no purpose.

**Independent Test**: Can be fully tested by sending a chat completion request via the Azure OpenAI Python SDK configured to use `http://localhost:8000` as the endpoint, and verifying the response matches expected Azure OpenAI response format.

**Acceptance Scenarios**:

1. **Given** the middleware server is running with valid Azure credentials configured, **When** a developer sends a chat completion request using the Azure OpenAI SDK with the local API key, **Then** the request is forwarded to Azure OpenAI and the response is returned in the exact same format as a direct Azure OpenAI call.

2. **Given** the middleware server is running, **When** a developer sends a request without the local API key header, **Then** the server returns HTTP 401 Unauthorized.

3. **Given** the middleware server is running, **When** a developer sends a request with an invalid local API key, **Then** the server returns HTTP 401 Unauthorized.

---

### User Story 2 - Streaming Chat Completion (Priority: P1)

A developer wants to use streaming chat completions, receiving tokens as they are generated while the middleware logs only the final complete response.

**Why this priority**: Streaming is essential for real-time applications and is a commonly used feature. The requirement to buffer and log only final responses makes this technically distinct from non-streaming.

**Independent Test**: Can be tested by sending a streaming chat completion request and verifying: (1) tokens arrive incrementally, (2) the log file contains only one entry with the complete reconstructed response.

**Acceptance Scenarios**:

1. **Given** the middleware server is running, **When** a developer sends a chat completion request with `stream=true`, **Then** the server streams response chunks to the client in real-time using Server-Sent Events (SSE).

2. **Given** a streaming request is in progress, **When** all chunks have been received from Azure OpenAI, **Then** the middleware logs a single entry containing the full reconstructed response (not individual chunks).

3. **Given** a streaming request is in progress, **When** the connection is interrupted mid-stream, **Then** the partial response is logged with an error indicator.

---

### User Story 3 - Daily Cost Tracking and Enforcement (Priority: P1)

A developer wants to prevent unexpected Azure costs by having the middleware enforce a configurable daily spending cap.

**Why this priority**: Cost control is a primary motivation for this tool. Developers need protection against runaway costs, especially during development/experimentation.

**Independent Test**: Can be tested by configuring a very low daily cap (e.g., €0.01), making requests until the cap is exceeded, and verifying subsequent requests are blocked with an appropriate error.

**Acceptance Scenarios**:

1. **Given** the middleware has processed requests totaling €4.50 today with a €5.00 daily cap, **When** a new request would cost €0.60, **Then** the request will still proceesed. **Only when** the cost is already higher or equal to €5.00 daily cap, an HTTP 429 error with a clear message about daily limit exceeded is returned.

2. **Given** the middleware was restarted mid-day, **When** it starts up, **Then** it reads the last line of the existing daily log file to check the cumulative cost before accepting new requests.

3. **Given** a new day has started (UTC midnight), **When** the first request of the day arrives, **Then** the daily cost counter resets to zero.

4. **Given** the daily cap is reached, **When** the user checks the response, **Then** the error message includes the current cumulative cost and the configured cap.

---

### User Story 4 - Request/Response Logging (Priority: P1)

A developer wants all API interactions logged for debugging, auditing, and cost analysis purposes.

**Why this priority**: Logging is essential for debugging, cost tracking, and understanding API usage patterns. It's a core feature that enables cost tracking.

**Independent Test**: Can be tested by making several API calls and verifying the JSONL log file contains properly formatted entries with all required fields.

**Acceptance Scenarios**:

1. **Given** the middleware is running, **When** a chat completion request is processed, **Then** a JSONL entry is written containing:

   * timestamp (plaintext)
   * **compressed and encrypted request JSON**
   * **compressed and encrypted response JSON**
   * calculated cost (plaintext)
   * cumulative daily cost (plaintext).

2. **Given** the middleware is running, **When** an embedding request is processed, **Then** a JSONL entry is written containing:

   * timestamp (plaintext)
   * **compressed and encrypted request JSON**
   * calculated cost (plaintext)
   * cumulative daily cost (plaintext),
     and the response JSON is omitted for embeddings.

3. **Given** logging is configured, **When** a log entry is written, **Then** it is stored in the following format:

   ```
   logs/YYYYMMDD/<os_username>_YYYYMMDD.jsonl
   ```

4. **Given** the logging subsystem encounters an error (e.g., disk full), **When** a request is processed, **Then** the request completes successfully and the logging failure does not block or fail the request.

5. **Given** a log entry is written, **When** the JSONL line is persisted to disk, **Then** only the request and response JSON fields are compressed and encrypted prior to writing, while metadata fields remain readable in plaintext.

---

### User Story 5 - Embeddings API Support (Priority: P2)

A developer wants to generate embeddings through the middleware with the same SDK compatibility as chat completions.

**Why this priority**: Embeddings are a common use case but simpler than chat completions. Supporting them broadens the utility of the middleware.

**Independent Test**: Can be tested by sending an embeddings request via the Azure OpenAI SDK and verifying the response format matches direct Azure OpenAI responses.

**Acceptance Scenarios**:

1. **Given** the middleware server is running, **When** a developer sends an embeddings request, **Then** the request is forwarded to Azure OpenAI and the embedding vectors are returned in the standard format.

2. **Given** an embeddings request is processed, **When** logging occurs, **Then** only the request JSON is logged (not the response vectors, to save space).

---

### User Story 6 - Responses API Support (Priority: P2)

A developer wants to use the Azure OpenAI Responses API through the middleware.

**Why this priority**: The Responses API is a newer feature that some developers need. Including it ensures broader API coverage.

**Independent Test**: Can be tested by sending a Responses API request and verifying correct proxying behavior.

**Acceptance Scenarios**:

1. **Given** the middleware server is running, **When** a developer sends a Responses API request, **Then** the request is forwarded to Azure OpenAI and the response is returned correctly.

---

### User Story 7 - Configuration via YAML (Priority: P2)

A developer wants to configure the middleware through a simple YAML file without modifying code.

**Why this priority**: Easy configuration is essential for usability. YAML is human-readable and standard for configuration.

**Independent Test**: Can be tested by modifying config.yaml values and verifying the middleware behavior changes accordingly on restart.

**Acceptance Scenarios**:

1. **Given** a config.yaml file exists, **When** the middleware starts, **Then** it loads Azure endpoint, deployment name, API version, authentication mode, pricing, and daily cap from the file.

2. **Given** config.yaml specifies `auth_mode: aad`, **When** the middleware starts, **Then** it uses Azure Active Directory authentication for Azure OpenAI requests.

3. **Given** config.yaml specifies `auth_mode: api_key`, **When** the middleware starts, **Then** it uses the configured API key for Azure OpenAI requests.

4. **Given** config.yaml is missing or invalid, **When** the middleware starts, **Then** it fails with a clear error message indicating the configuration problem.

---

### User Story 8 - Unknown Endpoint Rejection (Priority: P3)

A developer accidentally sends a request to an unsupported endpoint and receives a clear error rather than undefined behavior.

**Why this priority**: Explicit rejection of unknown endpoints ensures predictable behavior and makes debugging easier.

**Independent Test**: Can be tested by sending a request to a non-existent endpoint and verifying a proper error response.

**Acceptance Scenarios**:

1. **Given** the middleware is running, **When** a request is sent to an endpoint not in the supported list (e.g., `/v1/images/generations`), **Then** the server returns HTTP 501 Not Implemented with a message listing supported endpoints.

---

### Edge Cases

- What happens when Azure OpenAI returns a 429 (rate limit)? → Forward the error to client transparently with all headers.
- What happens when Azure OpenAI is unreachable? → Return HTTP 502 Bad Gateway with a descriptive error message.
- What happens when the log file is locked by another process? → Retry with backoff, then proceed without logging (best-effort).
- What happens when the request body is malformed JSON? → Return HTTP 400 Bad Request before forwarding.
- What happens when the cost calculation fails (unknown model)? → Log a warning, use a default/fallback price, proceed with request.
- What happens during concurrent requests? → Cost tracking must be thread-safe; use async locks.
- What happens when the encryption key is not configured? → Fail startup with a clear error message.

---

## Requirements *(mandatory)*

### Functional Requirements

#### Authentication & Authorization

- **FR-001**: System MUST support Azure Active Directory (AAD) authentication mode for Azure OpenAI.
- **FR-002**: System MUST support Azure OpenAI API Key authentication mode.
- **FR-003**: System MUST select authentication mode based on `config.yaml` setting.
- **FR-004**: System MUST require a local API key for all incoming requests to prevent accidental misuse.
- **FR-005**: System MUST return HTTP 401 for requests without valid local API key.

#### API Compatibility

- **FR-006**: System MUST expose endpoints compatible with Azure OpenAI REST API format.
- **FR-007**: System MUST support Chat Completions endpoint (`/openai/deployments/{deployment}/chat/completions`).
- **FR-008**: System MUST support Embeddings endpoint (`/openai/deployments/{deployment}/embeddings`).
- **FR-009**: System MUST support Responses API endpoint (`/openai/deployments/{deployment}/responses`).
- **FR-010**: System MUST return HTTP 501 Not Implemented for unsupported endpoints.
- **FR-011**: System MUST preserve all request headers, query parameters, and body when forwarding to Azure OpenAI.
- **FR-012**: System MUST preserve all response headers, status codes, and body when returning to client.

#### Streaming

- **FR-013**: System MUST support streaming responses via Server-Sent Events (SSE).
- **FR-014**: System MUST stream response chunks to client immediately upon receipt from Azure.
- **FR-015**: System MUST buffer streaming chunks internally for logging purposes.
- **FR-016**: System MUST log only the final reconstructed response for streaming requests.

#### Logging

- **FR-017**: System MUST log all requests and responses in JSONL format.
- **FR-018**: System MUST organize logs in `logs/YYYYMMDD/<os_username>_YYYYMMDD.jsonl` structure.
- **FR-019**: System MUST include in each log entry: timestamp, request JSON, response JSON (except embeddings), tool/function calls, calculated cost, cumulative daily cost.
- **FR-020**: System MUST perform logging asynchronously (non-blocking).
- **FR-021**: System MUST NOT fail requests due to logging errors (best-effort logging).
- **FR-022**: System MUST compress the request and response JSON fields prior to writing each JSONL entry.
- **FR-023**: System MUST encrypt the compressed request and response JSON fields using AES-256-GCM prior to writing each JSONL entry.
- **FR-024**: System MUST omit response vectors from embedding request logs to conserve space.

#### Cost Tracking

- **FR-025**: System MUST calculate request costs in EUR based on token counts and configured pricing.
- **FR-026**: System MUST track cumulative daily cost across all requests.
- **FR-027**: System MUST persist cost state such that server restarts do not lose daily totals.
- **FR-028**: System MUST enforce a configurable daily cost cap (default: €5.00).
- **FR-029**: System MUST return HTTP 429 with clear message when daily cap is exceeded.
- **FR-030**: System MUST reset daily cost counter at UTC midnight.
- **FR-031**: System MUST include current cost and cap in the HTTP 429 response body.

#### Configuration

- **FR-032**: System MUST read configuration from `config.yaml` file.
- **FR-033**: System MUST support configuration of: Azure endpoint, deployment name, API version, auth mode, Azure credentials, local API key, pricing per model, daily cost cap, log encryption key.
- **FR-034**: System MUST validate configuration on startup and fail with clear errors if invalid.

#### Error Handling

- **FR-035**: System MUST forward Azure OpenAI error responses transparently to clients.
- **FR-036**: System MUST return HTTP 502 Bad Gateway when Azure OpenAI is unreachable.
- **FR-037**: System MUST return HTTP 400 Bad Request for malformed request bodies.

#### Health & Monitoring

- **FR-038**: System MUST expose an unauthenticated `/health` endpoint that returns HTTP 200 OK when the server is running.
- **FR-039**: System MUST expose an unauthenticated `/metrics` endpoint that returns current daily cost and configured cap in JSON format.

### Non-Functional Requirements

- **NFR-001**: System MUST use FastAPI framework with asyncio for concurrency.
- **NFR-002**: System MUST be concurrency-safe and async-safe for concurrent request handling using asyncio primitives (e.g., `asyncio.Lock`).
- **NFR-003**: System MUST use async locks for cost tracking to prevent race conditions.
- **NFR-004**: System MUST run on Windows operating systems.
- **NFR-005**: System MUST be installable as a Python package.
- **NFR-006**: System MUST provide a CLI command to start the server.
- **NFR-007**: System MUST be designed for easy addition of new endpoints (extensible architecture).
- **NFR-008**: System MUST obtain user identity from Windows OS login name.

### Key Entities

- **Request**: Incoming API request with method, path, headers, body, timestamp.
- **Response**: Azure OpenAI response with status, headers, body, token counts.
- **LogEntry**: JSONL record containing request, response, cost, cumulative cost, timestamp, user.
- **Configuration**: YAML-based settings for Azure connection, authentication, pricing, limits.
- **CostTracker**: In-memory state tracking daily cumulative cost with persistence via log files.
- **StreamBuffer**: Temporary storage for accumulating streaming response chunks.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Azure OpenAI Python SDK can connect to the middleware without any SDK code modifications—only endpoint URL and API key configuration changes.
- **SC-002**: Streaming responses begin arriving at the client within 100ms of the first chunk from Azure OpenAI.
- **SC-003**: Server handles at least 10 concurrent requests without errors or significant latency degradation.
- **SC-004**: Daily cost tracking is accurate to within €0.001 of actual Azure costs.
- **SC-005**: Server startup time (including log file parsing for cost reconstruction) is under 5 seconds for log files up to 100MB.
- **SC-006**: Logging adds no more than 50ms latency to request processing (async, non-blocking).
- **SC-007**: All supported endpoints pass compatibility tests with official Azure OpenAI SDK.
- **SC-008**: Server runs continuously for 24+ hours under normal usage without memory leaks or crashes.
- **SC-009**: Configuration changes require only a server restart, no code changes.
- **SC-010**: Clear error messages enable developers to diagnose issues within 2 minutes.

---

## Technical Notes

### Endpoint Mapping

The middleware must translate between local endpoints and Azure OpenAI endpoints:

| Local Endpoint | Azure OpenAI Endpoint |
|----------------|----------------------|
| `POST /openai/deployments/{deployment}/chat/completions` | `POST https://{resource}.openai.azure.com/openai/deployments/{deployment}/chat/completions?api-version={version}` |
| `POST /openai/deployments/{deployment}/embeddings` | `POST https://{resource}.openai.azure.com/openai/deployments/{deployment}/embeddings?api-version={version}` |
| `POST /openai/deployments/{deployment}/responses` | `POST https://{resource}.openai.azure.com/openai/deployments/{deployment}/responses?api-version={version}` |

> **Note**: The Responses API endpoint format may vary by Azure OpenAI API version. The deployment-based path (`/openai/deployments/{deployment}/responses`) is used for consistency with other endpoints. Verify against your Azure API version.

### Cost Calculation Formula

```
cost = (prompt_tokens * input_price_per_1k / 1000) + (completion_tokens * output_price_per_1k / 1000)
```

Pricing must be configurable per model/deployment in `config.yaml`.

### Log Entry Schema (JSONL)

```json
{
  "timestamp": "2024-12-14T10:30:00.000Z",
  "user": "windows_username",
  "endpoint": "/openai/deployments/gpt-4/chat/completions",
  "request_encrypted": "base64-encoded-gzip-aes256gcm-ciphertext...",
  "response_encrypted": "base64-encoded-gzip-aes256gcm-ciphertext...",
  "tokens": {
    "prompt": 150,
    "completion": 50,
    "total": 200
  },
  "cost_eur": 0.0234,
  "cumulative_cost_eur": 2.5678,
  "duration_ms": 1250,
  "stream": false,
  "error": null
}
```

> **Note**: `request_encrypted` and `response_encrypted` contain the original JSON objects compressed with gzip and encrypted with AES-256-GCM, then base64-encoded. Decrypt and decompress to recover original request/response objects. For embeddings, `response_encrypted` is omitted.

### Configuration Schema (config.yaml)

```yaml
azure:
  endpoint: "https://my-resource.openai.azure.com"
  deployment: "gpt-4"
  api_version: "2024-02-01"
  auth_mode: "aad"  # or "api_key"
  api_key: ""  # only used if auth_mode is "api_key"

local:
  host: "127.0.0.1"
  port: 8000
  api_key: "local-dev-key-12345"

pricing:  # EUR per 1000 tokens
  gpt-4:
    input: 0.03
    output: 0.06
  gpt-35-turbo:
    input: 0.0015
    output: 0.002
  text-embedding-ada-002:
    input: 0.0001
    output: 0.0

limits:
  daily_cost_cap_eur: 5.0

logging:
  encryption_key: "base64-encoded-key-here"
  compression: "gzip"
```

---

## Clarifications

### Session 2025-12-14

- Q: Should the encryption key be stored in config.yaml or retrieved from Windows Credential Manager? → A: Store in config.yaml (simple, matches project security posture)
- Q: Should there be automatic log cleanup/rotation after N days? → A: No automatic cleanup (manual deletion by user)
- Q: Should there be a `/health` endpoint for monitoring? → A: Yes, unauthenticated `/health` returning 200 OK
- Q: Should there be a `/metrics` endpoint exposing current daily cost? → A: Yes, unauthenticated `/metrics` with daily cost & cap
- Q: Which encryption algorithm should be used for log encryption? → A: AES-256-GCM (authenticated encryption, industry standard)

---

## Open Questions

1. ~~**Encryption key management**: Should the encryption key be in config.yaml or retrieved from Windows Credential Manager for better security?~~ **Resolved**: Store in config.yaml.
2. ~~**Log retention**: Should there be automatic log cleanup/rotation after N days?~~ **Resolved**: No automatic cleanup; manual deletion by user.
3. ~~**Health endpoint**: Should there be a `/health` endpoint for monitoring that doesn't require authentication?~~ **Resolved**: Yes, unauthenticated `/health` returning 200 OK.
4. ~~**Metrics endpoint**: Should there be a `/metrics` endpoint exposing current daily cost without making an API call?~~ **Resolved**: Yes, unauthenticated `/metrics` with daily cost & cap.
