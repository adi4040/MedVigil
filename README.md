# MedVigil Monorepo

MedVigil evaluates clinical documentation against a policy rubric and returns a structured gap report. FastAPI owns the clinical audit API and LLM integrations. Next.js provides the browser workflow and consumes the POST SSE stream.

## Applications

| Application | Path | Local URL |
| --- | --- | --- |
| Next.js web | `apps/web` | http://127.0.0.1:3000/audit |
| FastAPI API | `apps/api` | http://127.0.0.1:8000 |
| Swagger UI | `apps/api` | http://127.0.0.1:8000/docs |

## Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r apps/api/requirements.txt
Copy-Item apps/api/.env.example apps/api/.env
corepack enable
pnpm install
```

Use `LLM_PROVIDER=mock` in `apps/api/.env` for local development without provider credentials.

## Development

Start both applications after activating the Python environment:

```powershell
pnpm dev
```

Run one application:

```powershell
pnpm dev:api
pnpm dev:web
```

## Verification

```powershell
pnpm test
pnpm typecheck
pnpm lint
pnpm build
```

Generate the frontend API contract after changing FastAPI routes or schemas:

```powershell
pnpm contracts:generate
```

## Documentation

- [Getting started](docs/getting_started.md)
- [Running and testing](docs/running_and_testing.md)
- [Project structure](docs/project_structure.md)
- [Next.js monorepo implementation plan](docs/nextjs_monorepo_implementation_plan.md)
