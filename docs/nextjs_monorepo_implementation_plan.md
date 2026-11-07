# Next.js and FastAPI Monorepo Implementation Plan

## 1. Goal

Build a production-quality Next.js frontend with Tailwind CSS while keeping FastAPI as the primary backend and owner of:

- Clinical audit business logic
- Request and response validation
- LLM provider credentials and integrations
- Retry and streaming behavior
- Authentication and authorization enforcement
- API contracts

The repository will use a symmetric monorepo structure with FastAPI under `apps/api`, Next.js under `apps/web`, and pnpm plus Turborepo for JavaScript workspace orchestration.

## 2. Architecture Decisions

1. Move the existing FastAPI application to `apps/api`.
2. Keep `apps/api/app` as the Python import package named `app`.
3. Add a Next.js App Router application under `apps/web`.
4. Use strict TypeScript and locally compiled Tailwind CSS.
5. Use pnpm workspaces and Turborepo.
6. Keep evaluation scripts and datasets at the repository root.
7. Keep Pydantic and FastAPI OpenAPI as the API contract source of truth.
8. Generate frontend TypeScript types and runtime validators from OpenAPI.
9. Consume the POST SSE endpoint with streaming `fetch`, not native `EventSource`.
10. Deploy the API and frontend independently behind a shared ingress.

## 3. Target Repository Structure

```text
MedV_micro_service/
|-- apps/
|   |-- api/
|   |   |-- app/
|   |   |   |-- api/
|   |   |   |-- core/
|   |   |   |-- schemas/
|   |   |   |-- services/
|   |   |   |-- static/
|   |   |   `-- main.py
|   |   |-- tests/
|   |   |-- scripts/
|   |   |   `-- export_openapi.py
|   |   |-- .env.example
|   |   |-- package.json
|   |   |-- pytest.ini
|   |   |-- requirements.txt
|   |   `-- Dockerfile
|   `-- web/
|       |-- src/
|       |   |-- app/
|       |   |   |-- audit/
|       |   |   |   `-- page.tsx
|       |   |   |-- demo/
|       |   |   |   `-- page.tsx
|       |   |   |-- error.tsx
|       |   |   |-- layout.tsx
|       |   |   `-- page.tsx
|       |   |-- features/
|       |   |   `-- audit/
|       |   |       |-- components/
|       |   |       |-- audit-reducer.ts
|       |   |       |-- audit-types.ts
|       |   |       |-- fixtures.ts
|       |   |       `-- use-audit-stream.ts
|       |   `-- lib/
|       |       `-- env.ts
|       |-- e2e/
|       |-- public/
|       |-- next.config.ts
|       |-- package.json
|       |-- playwright.config.ts
|       |-- tsconfig.json
|       |-- vitest.config.ts
|       `-- Dockerfile
|-- packages/
|   |-- api-client/
|   |   |-- openapi/
|   |   |   `-- openapi.json
|   |   |-- src/
|   |   |   |-- generated/
|   |   |   |-- client.ts
|   |   |   `-- sse.ts
|   |   `-- package.json
|   |-- eslint-config/
|   `-- typescript-config/
|-- scripts/
|   |-- benchmark_latency.py
|   |-- run_eval.py
|   `-- test_stream.py
|-- clinical_notes/
|-- policy_rubrics/
|-- eval_cases/
|-- Discharge_notes/
|-- docs/
|-- package.json
|-- pnpm-lock.yaml
|-- pnpm-workspace.yaml
`-- turbo.json
```

## 4. Backend Migration Strategy

### 4.1 Mechanical Move

Move these tracked paths without changing their behavior:

| Current path | Destination |
| --- | --- |
| `app` | `apps/api/app` |
| `tests` | `apps/api/tests` |
| `requirements.txt` | `apps/api/requirements.txt` |
| `pytest.ini` | `apps/api/pytest.ini` |
| `.env.example` | `apps/api/.env.example` |

Keep these paths at the repository root:

- `scripts`
- `clinical_notes`
- `policy_rubrics`
- `eval_cases`
- `Discharge_notes`
- `docs`

Do not rename the Python package from `app`. Existing imports such as `from app.core.config import settings` should remain unchanged.

Do not combine the mechanical move with endpoint, schema, CORS, retry, or provider behavior changes. This keeps migration regressions easy to identify.

### 4.2 Python Commands

Run the API from the repository root:

```powershell
python -m uvicorn app.main:app --app-dir apps/api --reload --host 127.0.0.1 --port 8000
```

Run the API from `apps/api`:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Run tests from the repository root:

```powershell
python -m pytest -c apps/api/pytest.ini -v
```

The API pytest configuration should include:

```ini
[pytest]
testpaths = tests
pythonpath = .
asyncio_default_fixture_loop_scope = function
filterwarnings =
    ignore::DeprecationWarning
```

### 4.3 Stable Environment Loading

The current `env_file=".env"` behavior depends on the process working directory. After relocation, derive the API directory from `__file__` and load `apps/api/.env` explicitly.

Recommended migration precedence:

1. Process environment variables
2. `apps/api/.env`
3. Temporary root `.env` compatibility fallback

Remove the root fallback after developers and deployment environments have migrated. Production should inject secrets through environment variables or a secret manager rather than dotenv files.

### 4.4 Root Evaluation Scripts

Keep root data and output paths unchanged. Update Python import setup in:

- `scripts/benchmark_latency.py`
- `scripts/run_eval.py`
- `scripts/test_stream.py`

Use:

```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent
API_ROOT = PROJECT_ROOT / "apps" / "api"
sys.path.insert(0, str(API_ROOT))
```

Existing `from app...` imports can then remain unchanged.

## 5. Workspace Setup

### 5.1 pnpm Workspace

Add `pnpm-workspace.yaml`:

```yaml
packages:
  - apps/*
  - packages/*
```

The root `package.json` should be private, pin the pnpm version through `packageManager`, and expose these commands:

```text
pnpm dev
pnpm dev:api
pnpm dev:web
pnpm build
pnpm lint
pnpm typecheck
pnpm test
pnpm test:api
pnpm test:web
pnpm test:e2e
pnpm contracts:generate
pnpm contracts:check
```

### 5.2 Turborepo

Configure Turbo tasks for:

- `dev`: persistent and uncached
- `build`: dependent on upstream package builds
- `lint`
- `typecheck`
- `test`
- `contracts:generate`

Provider-backed benchmarks must remain manual or scheduled tasks and must not run in the normal pull-request task graph.

### 5.3 API Workspace Wrapper

Add a private `apps/api/package.json` only to expose Python commands to Turbo:

```json
{
  "name": "@medv/api",
  "private": true,
  "scripts": {
    "dev": "python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000",
    "test": "python -m pytest -v",
    "openapi": "python scripts/export_openapi.py"
  }
}
```

pnpm does not manage Python dependencies. Python continues to use its own virtual environment and dependency files.

## 6. Next.js Application

### 6.1 Technology Choices

- Current stable Next.js with App Router
- React with strict TypeScript
- Tailwind CSS compiled locally
- `next/font` or locally hosted fonts
- React Hook Form for form state
- Zod for browser-side validation
- `eventsource-parser` for SSE parsing
- Vitest and React Testing Library
- Playwright for end-to-end tests
- `jest-axe` for automated accessibility checks

Do not use CDN Tailwind, runtime Google Fonts, or model-controlled HTML.

### 6.2 Main Audit Experience

The `/audit` page should provide:

- Clinical note input
- Policy rubric input
- Optional rubric ID
- Temperature under an advanced section
- Approved synthetic sample presets
- Start and cancel controls
- Streaming status and elapsed time
- Optional collapsed raw stream diagnostics
- Final criterion cards
- Evidence and explanations
- Suggested clarification list
- Synchronous fallback action

The final report must only be rendered from the validated `done.report` event. Partially streamed JSON must not be parsed into criterion cards.

### 6.3 Required UI States

| State | Expected behavior |
| --- | --- |
| Idle | Form is ready and submit is enabled. |
| Invalid | Inline validation errors are shown and focus moves to the first error. |
| Connecting | Request sent; immediate status feedback is displayed. |
| Streaming | Token diagnostics and elapsed metrics update without blocking typing. |
| Retrying | Server retry status is displayed without resubmitting the request. |
| Complete | Validated report is rendered and announced. |
| HTTP error | Status-specific, actionable error is displayed. |
| Stream error | Partial diagnostics remain, but no report is marked complete. |
| Interrupted | EOF without `done` or `error` is treated as failure. |
| Cancelled | User cancellation is distinguished from provider failure. |

## 7. API Contracts

### 7.1 Source of Truth

Pydantic models under `apps/api/app/schemas` remain canonical.

Add `apps/api/scripts/export_openapi.py` to export deterministic OpenAPI JSON without requiring a running server or provider credentials. The generated document should be committed at:

```text
packages/api-client/openapi/openapi.json
```

Generate TypeScript types, fetch helpers, and Zod schemas into `packages/api-client/src/generated`.

CI must regenerate the contract and fail when generated files differ from committed files.

### 7.2 Contract Hardening Before Generation

Complete these backend changes before relying on generated frontend types:

1. Remove the internal provider argument from public FastAPI query parameters.
2. Document 400, 422, 500, 502, and 503 responses.
3. Explicitly document `text/event-stream` for the streaming endpoint.
4. Expose stream event payloads in OpenAPI components.
5. Convert the all-optional `StreamChunk` model into validated event variants.
6. Add maximum lengths for clinical note, rubric, and rubric ID fields.
7. Return safe public errors with a request ID instead of raw provider exceptions.

Recommended frontend event union:

```typescript
type AuditStreamEvent =
  | { event: "status"; message: string; retries: number }
  | { event: "token"; text: string }
  | { event: "done"; report: ClinicalGapReport; retries: number }
  | { event: "error"; error: string; code?: string; requestId?: string };
```

## 8. POST SSE Client

Native `EventSource` cannot be used because the endpoint requires POST, a JSON request body, and potentially authorization headers.

The frontend stream client should:

1. Call the relative path `/api/v1/audit/evaluate/stream` with `fetch`.
2. Send `Content-Type: application/json` and `Accept: text/event-stream`.
3. Set `cache: "no-store"`.
4. Pass an `AbortController` signal.
5. Validate the HTTP status and response content type.
6. Parse response bytes with `TextDecoder` and `eventsource-parser`.
7. Runtime-validate each event.
8. Confirm the SSE event name matches the JSON `event` field.
9. Treat `done.report` as authoritative.
10. Treat EOF without a terminal event as an incomplete stream.
11. Never automatically replay a request after token output begins.

FastAPI should also:

- Detect disconnected clients
- Cancel or close the upstream provider stream
- Emit heartbeat comments during long waits
- Set `Cache-Control: no-cache, no-transform`
- Emit exactly one terminal `done` or `error` event

## 9. Routing and Environment Strategy

### 9.1 Local Development

Use a Next.js rewrite from `/api/:path*` to `http://127.0.0.1:8000/api/:path*`. Verify that the rewrite does not buffer SSE.

If the rewrite buffers streaming in the selected Next.js version, use a configurable browser API origin for development and allow only the explicit local web origin in FastAPI CORS.

### 9.2 Production

Use one public origin with ingress path routing:

```text
/api/*          -> FastAPI
/docs           -> FastAPI, restricted
/redoc          -> FastAPI, restricted
/openapi.json   -> FastAPI, restricted as appropriate
/_next/*        -> Next.js
/*              -> Next.js
```

Route `/api/*` directly to FastAPI instead of relaying SSE through a Next.js route handler. This avoids an additional buffering and timeout boundary.

### 9.3 Secret Ownership

The following variables must remain backend-only:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_API_KEY`
- `GEMINI_API_KEY`
- `OPENAI_API_KEY`
- `LLM_BASE_URL`

Do not create `NEXT_PUBLIC_LLM_*` variables.

## 10. Legacy Demo Migration

The existing FastAPI static demo should remain available during development only until the Next.js UI reaches feature parity.

Migration sequence:

1. Build the Next.js `/audit` experience.
2. Add `/demo` in Next.js as an alias or redirect to `/audit`.
3. Route public `/demo` traffic to Next.js.
4. Remove the superseded FastAPI `/demo` route and static page.
5. Update backend tests for the selected behavior.
6. Remove the legacy static page after a deprecation period.

The legacy page must not remain publicly exposed without fixing its model-output `innerHTML` XSS risk.

## 11. Security and Privacy

- Authenticate real clinical workflows using an approved OIDC/OAuth provider.
- Validate access tokens and scopes in FastAPI, not only in Next.js.
- Rate-limit and concurrency-limit paid audit requests.
- Restrict CORS to explicit origins or disable it for same-origin production routing.
- Enforce request-size limits in FastAPI and at the ingress.
- Treat all LLM output as untrusted text.
- Never use `dangerouslySetInnerHTML` for report content.
- Never place access tokens in `localStorage`.
- Do not persist clinical notes, rubrics, or reports in browser storage by default.
- Do not log clinical content, streamed tokens, authorization headers, or full reports.
- Scrub monitoring and error-reporting payloads.
- Add CSP, HSTS, Referrer-Policy, Permissions-Policy, and frame restrictions.
- Use only synthetic fixtures in tests, screenshots, traces, and demos.

## 12. Accessibility

Target WCAG 2.2 AA.

- Use semantic headings, labels, fieldsets, buttons, and lists.
- Provide complete keyboard navigation and visible focus states.
- Communicate statuses with text and icons, not color alone.
- Use a polite live region for status transitions, not for every token.
- Move focus to validation errors, terminal errors, and completed summaries.
- Make the cancel control keyboard and screen-reader accessible.
- Respect `prefers-reduced-motion`.
- Avoid alert dialogs for routine validation and transport errors.

## 13. Testing Strategy

### 13.1 Backend

Preserve all existing tests and add coverage for:

- Relocated import and environment behavior
- CORS origin allow and deny behavior
- Input limits
- Authentication and authorization
- Safe error redaction
- OpenAPI response documentation
- Every stream event variant
- Exactly one terminal event
- Disconnect cancellation
- Updated `/demo` behavior

### 13.2 Frontend

Add component tests for:

- Form validation and payload construction
- Reducer and stream state transitions
- Report rendering for met, unclear, and missing statuses
- HTTP, stream, interrupted, and cancellation errors
- Focus management and keyboard interaction
- Accessibility checks

Test the SSE parser with:

- Frames split at arbitrary byte boundaries
- UTF-8 characters split across chunks
- LF and CRLF line endings
- Multiple frames in one network chunk
- Multiline `data:` fields
- Malformed JSON
- Event name and payload mismatches
- EOF before a terminal event
- Cancellation before and after the first token

### 13.3 End-to-End

Run FastAPI with `LLM_PROVIDER=mock` and test the real Next.js application with Playwright.

Required scenarios:

- Local API proxying
- Immediate status event
- Token event before final report
- Successful synchronous evaluation
- Successful streaming evaluation
- Request validation failure
- Provider failure
- User cancellation
- Interrupted stream
- Responsive layout
- Keyboard-only operation
- `/demo` compatibility

## 14. CI and Deployment

### 14.1 CI Jobs

1. Backend job: install Python dependencies, run pytest, export OpenAPI.
2. Contract job: regenerate TypeScript and Zod output, fail on drift.
3. Frontend job: install with frozen lockfile, lint, type-check, test, and build.
4. Integration job: start mock FastAPI and Next.js, then run Playwright.
5. Security job: run dependency, secret, and static-analysis scans.

Provider-backed latency and semantic benchmarks should run manually or on a schedule, not on every pull request.

### 14.2 Deployment

Build separate containers for:

- FastAPI ASGI service
- Next.js standalone Node service

Ingress requirements:

- Route `/api/*` directly to FastAPI
- Disable response buffering and compression for SSE
- Use a read timeout longer than the maximum audit duration
- Do not cache API or SSE responses
- Support graceful shutdown of active streams
- Inject LLM credentials only into the API container

## 15. Phased Delivery

### Phase 0: Baseline

- Preserve all current worktree changes.
- Run the existing backend test suite.
- Export baseline OpenAPI.
- Record current routes and stream events.
- Run mock evaluation and streaming smoke tests.

Exit condition: existing behavior is reproducible and documented.

### Phase 1: FastAPI Relocation

- Move backend files to `apps/api`.
- Preserve the Python package name `app`.
- Stabilize dotenv resolution.
- Update pytest and root script import paths.
- Update backend documentation and commands.

Exit condition: tests, scripts, Swagger, the legacy demo, and SSE behave exactly as before.

### Phase 2: Workspace Scaffold

- Add pnpm workspace and lockfile.
- Add Turbo configuration.
- Add API task wrapper.
- Scaffold Next.js, TypeScript, and Tailwind.
- Extend `.gitignore` for frontend artifacts.

Exit condition: `pnpm dev` starts API and web applications together.

### Phase 3: Contract Package

- Add deterministic OpenAPI export.
- Harden API and stream schemas.
- Generate TypeScript and Zod contracts.
- Add contract drift checks.

Exit condition: frontend code imports generated contracts without manually duplicating DTOs.

### Phase 4: Audit Frontend

- Implement form and synthetic presets.
- Implement POST SSE transport and cancellation.
- Implement state reducer and metrics.
- Render validated reports.
- Add synchronous fallback.
- Add responsive and accessible behavior.

Exit condition: Next.js reaches feature parity with the legacy demo against `MockAuditClient`.

### Phase 5: Production Hardening

- Add authentication and authorization.
- Add quotas, rate limiting, input limits, and safe errors.
- Restrict CORS and add security headers.
- Add PHI-safe logs and metrics.
- Complete accessibility testing.

Exit condition: security, privacy, and accessibility requirements pass review.

### Phase 6: CI, Deployment, and Cutover

- Add backend, frontend, contract, integration, and security CI jobs.
- Build separate API and web images.
- Configure streaming-aware ingress.
- Route `/` and `/demo` to Next.js.
- Deprecate and remove the legacy static demo.
- Update all repository documentation.

Exit condition: frontend and backend can be deployed and rolled back independently.

## 16. Acceptance Criteria

- [ ] FastAPI resides under `apps/api/app` and retains `app` as its import package.
- [ ] Existing API paths and response shapes remain compatible.
- [ ] Existing Python tests pass after relocation.
- [ ] Root benchmark and evaluation scripts remain runnable.
- [ ] Environment loading works from the root and `apps/api` working directories.
- [ ] `pnpm dev`, `pnpm build`, and `pnpm test` work from the repository root.
- [ ] Next.js uses strict TypeScript and locally compiled Tailwind CSS.
- [ ] Frontend contracts are generated from FastAPI OpenAPI.
- [ ] No LLM credentials are included in frontend code or bundles.
- [ ] POST SSE supports status, token, done, error, and cancellation behavior.
- [ ] The frontend only reports success after a valid `done` event.
- [ ] No model-controlled content is rendered as HTML.
- [ ] Production `/api/*` routing bypasses Next.js and does not buffer SSE.
- [ ] Client disconnects cancel upstream provider work.
- [ ] Clinical content is absent from logs, analytics, browser persistence, and test artifacts.
- [ ] The Next.js audit workflow passes responsive, accessibility, component, and end-to-end tests.
- [ ] The legacy FastAPI demo is removed or restricted after frontend cutover.
