# Project Structure and Architecture

## Directory Layout

```text
MedV_micro_service/
|-- apps/
|   |-- api/
|   |   |-- app/                 # FastAPI source package
|   |   |-- tests/               # Backend tests
|   |   |-- scripts/             # OpenAPI export
|   |   |-- requirements.txt
|   |   `-- pytest.ini
|   `-- web/
|       |-- src/app/             # Next.js App Router routes
|       |-- src/features/audit/  # Audit UI and streaming state
|       |-- e2e/                 # Playwright scenarios
|       `-- package.json
|-- packages/
|   |-- api-client/              # OpenAPI types and SSE client
|   `-- typescript-config/       # Shared strict TypeScript settings
|-- scripts/                     # Evaluation and latency tools
|-- clinical_notes/              # Synthetic evaluation notes
|-- policy_rubrics/              # Policy fixtures
|-- eval_cases/                  # Expected and measured results
|-- docs/
|-- package.json                 # Root commands
|-- pnpm-workspace.yaml
`-- turbo.json
```

## Responsibilities

| Path | Responsibility |
| --- | --- |
| `apps/api/app/main.py` | FastAPI setup, CORS, and route registration. |
| `apps/api/app/api/v1/audit.py` | Synchronous and POST SSE audit endpoints. |
| `apps/api/app/services/llm_client.py` | Gemini, OpenAI-compatible, and mock providers. |
| `apps/api/app/schemas/audit.py` | Canonical Pydantic API and stream schemas. |
| `apps/web/src/features/audit` | Form, stream lifecycle, metrics, and report UI. |
| `packages/api-client` | Generated OpenAPI types, Zod validation, and SSE parsing. |
| `scripts` | Offline semantic and latency benchmarks. |

## Request Flow

```text
Browser
  -> Next.js /audit
  -> POST /api/v1/audit/evaluate/stream
  -> FastAPI validation
  -> configured LLM provider
  -> status/token/done/error SSE events
  -> validated report rendering
```

FastAPI remains the source of truth. The frontend never receives provider credentials and does not duplicate clinical audit logic.

## Extension Rules

1. Define backend contracts in Pydantic.
2. Add or update FastAPI route tests.
3. Run `pnpm contracts:generate`.
4. Consume generated frontend types from `@medv/api-client`.
5. Add component and end-to-end coverage for user-visible behavior.
