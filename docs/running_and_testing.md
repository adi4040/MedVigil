# Running and Testing

## Start Development Services

Activate the Python environment first:

```powershell
.venv\Scripts\Activate.ps1
pnpm dev
```

This starts:

- Next.js at http://127.0.0.1:3000
- FastAPI at http://127.0.0.1:8000

Run services separately when needed:

```powershell
pnpm dev:api
pnpm dev:web
```

The Next.js development server rewrites `/api/*` requests to FastAPI.

## Interfaces

| Interface | URL |
| --- | --- |
| Audit workspace | http://127.0.0.1:3000/audit |
| Swagger UI | http://127.0.0.1:8000/docs |
| ReDoc | http://127.0.0.1:8000/redoc |
| Health | http://127.0.0.1:8000/api/v1/health |
| SSE audit | `POST http://127.0.0.1:8000/api/v1/audit/evaluate/stream` |

## Test Commands

Run all workspace tests after activating the Python environment:

```powershell
pnpm test
```

Run suites independently:

```powershell
python -m pytest -c apps/api/pytest.ini -v
pnpm test:web
pnpm test:e2e
```

Run static verification and production builds:

```powershell
pnpm typecheck
pnpm lint
pnpm build
```

## API Contracts

Regenerate OpenAPI and TypeScript contracts after backend route or schema changes:

```powershell
pnpm contracts:generate
```

CI can detect stale generated contracts with:

```powershell
pnpm contracts:check
```

## Benchmarks

The evaluation assets remain at the repository root.

```powershell
python scripts/run_eval.py --provider mock --output eval_cases/mock_results.json
python scripts/test_stream.py --provider mock
python scripts/benchmark_latency.py --provider mock --runs 1 --temperatures 0 --delay 0
```

Provider-backed benchmarks should be run manually because they incur external cost and variable provider latency.
