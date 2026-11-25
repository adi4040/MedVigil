# MedVigil

<div align="center">

**A two-stage clinical review workspace for documentation gaps and renal dosing safety.**

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/Gemini-Tool_Calling-8E75B2?logo=googlegemini&logoColor=white)](https://ai.google.dev)
[![pnpm](https://img.shields.io/badge/pnpm-11-F69220?logo=pnpm&logoColor=white)](https://pnpm.io)

</div>

> [!IMPORTANT]
> MedVigil V1 is a demonstration system for synthetic or de-identified data. It is not a substitute for clinician or pharmacist review.

## What It Does

| Stage | Purpose | Result |
| --- | --- | --- |
| **Stage 1: Medical Gap Analyzer** | Compares a clinical note with a policy rubric. | Criterion-level `met`, `unclear`, or `missing` findings with supporting evidence. |
| **Stage 2: Renal Safety Auditor** | Checks a prescribed daily dose against patient renal data and stored dosing guidelines. | `safe`, `dose_adjustment_required`, or `insufficient_data` with rationale and tool trace. |

## Architecture

```mermaid
flowchart LR
    U[User] --> W[Next.js Review Workspace]
    W -->|Stage 1: POST SSE| A[FastAPI]
    W -->|Stage 2: POST JSON| A

    A --> S1[Documentation Audit Engine]
    S1 --> LLM[Gemini / OpenAI / Mock]
    S1 -->|status, token, done, error| W

    A --> S2[Renal Agent Runner]
    S2 --> G[Gemini Tool Calling]
    G --> T[Clinical Database Tools]
    T --> DB[(PostgreSQL)]
    S2 --> R[Validated Renal Audit Report]
    R --> W
```

The frontend uses same-origin `/api/*` requests. Next.js rewrites them to FastAPI, keeping provider and database credentials on the server.

## Stage 2 Flow

Stage 2 accepts a discharge medication payload, retrieves database-backed renal data, and returns a schema-validated report. The diagram shows the expected tool path; Gemini selects calls inside a bounded loop while the backend records the available tool evidence.

```mermaid
flowchart TD
    A[Discharge JSON] --> B[Pydantic Request Validation]
    B --> C[Gemini Agent Loop]
    C --> D[get_renal_metric]
    D --> E[fetch_patient_crcl]
    E -->|CrCl required and SCr exists| F[calculate_crcl]
    E -->|eGFR required| G[Use latest eGFR]
    F --> H[Tool Evidence Guard]
    G --> H
    H --> I[Pydantic RenalAuditReport]
    I --> J[Renal Safety Auditor UI]
```

### Agent Tools

| Tool | Responsibility |
| --- | --- |
| `get_renal_metric` | Finds the medication and its renal dosing brackets. |
| `fetch_patient_crcl` | Retrieves the latest non-null SCr and eGFR values. |
| `calculate_crcl` | Calculates Cockcroft-Gault CrCl from database demographics and SCr. |

### Implemented V1 Guardrails

- `discharge_json` must contain a valid JSON object.
- When a non-empty `patient_id` is supplied, renal tool calls are forced to use it.
- The agent-facing CrCl tool excludes serum creatinine input and uses the database value.
- A `safe` report with a missing renal metric or value is rejected.
- Missing successful medication or renal tool evidence forces `insufficient_data`.
- The agent stops after a bounded number of iterations.
- HTTP endpoint errors are sanitized before reaching the browser.

## Technology

- **Frontend:** Next.js 16, React 19, Tailwind CSS, shared `@medv/ui` components
- **Backend:** FastAPI, Pydantic v2, SQLAlchemy async
- **Database:** PostgreSQL with Alembic migrations
- **AI:** Gemini tool calling; Stage 1 also supports OpenAI-compatible and mock providers
- **Monorepo:** pnpm workspaces and Turborepo
- **Testing:** Pytest, Vitest, Testing Library, Playwright

## Quick Start

### Requirements

- Python 3.13+
- Node.js 20+
- pnpm 11+
- Docker, or an existing PostgreSQL database

### 1. Install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r apps/api/requirements.txt

corepack enable
pnpm install
```

### 2. Configure the API

Create `apps/api/.env` with placeholder values replaced locally:

```dotenv
APP_NAME=MedV Microservice
APP_VERSION=0.1.0
DEBUG=false
API_V1_PREFIX=/api/v1
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

LLM_PROVIDER=gemini
LLM_MODEL=<SUPPORTED_GEMINI_MODEL>
GEMINI_API_KEY=<YOUR_GEMINI_API_KEY>

DATABASE_URL=postgresql://medv_user:medv_password@localhost:5432/medv_db
```

Use `LLM_PROVIDER=mock` for Stage 1 development without provider cost. Stage 2 currently requires Gemini and populated PostgreSQL data.

### 3. Start PostgreSQL and migrate

```powershell
pnpm db:up
pnpm db:migrate
```

Stage 2 additionally requires synthetic patients, renal labs, medications, and renal dosing guidelines. The current Synthea script contains a local hard-coded CSV path that must be updated before running:

```powershell
pnpm seed:synthea
```

The Synthea script loads patients and labs only. Medication and renal-guideline reference data must be seeded separately from a reviewed source.

### 4. Start the application

```powershell
pnpm dev
```

| Interface | URL |
| --- | --- |
| Web workspace | <http://127.0.0.1:3000/audit> |
| Swagger API docs | <http://127.0.0.1:8000/docs> |
| API health | <http://127.0.0.1:8000/api/v1/health> |

## API Summary

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Service liveness and version information |
| `POST` | `/api/v1/audit/evaluate` | Stage 1 non-streaming audit |
| `POST` | `/api/v1/audit/evaluate/stream` | Stage 1 SSE audit |
| `POST` | `/api/v1/renal/evaluate` | Stage 2 renal safety audit |

### Stage 2 Request

`discharge_json` is currently sent as a JSON-encoded object string:

```json
{
  "discharge_json": "{\"patient_id\":\"synthetic-patient-id\",\"medication_name\":\"Gabapentin\",\"prescribed_daily_dose_mg\":900}"
}
```

### Stage 2 Response

```json
{
  "patient_id": "synthetic-patient-id",
  "medication_name": "Gabapentin",
  "prescribed_daily_dose_mg": 900,
  "required_renal_metric": "crcl",
  "renal_metric_value": 52.4,
  "verdict": "safe",
  "lab_warning": null,
  "rationale": "Dose evaluated against the matching renal guideline.",
  "tool_trace": [
    "get_renal_metric(...)",
    "fetch_patient_crcl(...)",
    "calculate_crcl(...)"
  ]
}
```

The values above are illustrative. Actual results depend on seeded synthetic records and guidelines.

## Repository Layout

```text
apps/
  api/                         FastAPI routes, schemas, agent tools, DB models
  web/                         Next.js Stage 1 and Stage 2 workspace
packages/
  api-client/                  Stage 1 contracts, Zod schemas, SSE client
  ui/                          Shared React UI components
  typescript-config/           Shared TypeScript settings
scripts/                        Evaluation and latency utilities
```

## Common Commands

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Run API and web applications |
| `pnpm test` | Run workspace tests |
| `pnpm test:e2e` | Run Playwright tests |
| `pnpm lint` | Run lint checks |
| `pnpm typecheck` | Run TypeScript checks |
| `pnpm build` | Build production packages |
| `pnpm contracts:generate` | Regenerate OpenAPI and TypeScript contracts |
| `pnpm db:migrate` | Apply Alembic migrations |

## Documentation

- [Getting Started](docs/getting_started.md)
- [Running and Testing](docs/running_and_testing.md)
- [Project Structure](docs/project_structure.md)
- [V1 Vercel Deployment Guide](docs/vercel_v1_deployment_guide.md)

## Current V1 Limitations

- Use synthetic or fully de-identified data only.
- Stage 2 requires pre-populated patient, lab, medication, and guideline tables.
- Stage 2 discharge fields and frontend response types are not yet generated from a canonical typed contract.
- The final renal value and verdict are not yet deterministically recomputed from tool outputs.
- The renal result supports review; it does not replace clinical judgment.
- Authentication, patient-level authorization, and production PHI controls are not yet implemented.

## License

Licensed under the [MIT License](LICENSE).
