# V1 Vercel Deployment Guide

This guide deploys MedV V1 with both application stages:

- Stage 1: Medical Gap Analyzer with streamed Server-Sent Events (SSE)
- Stage 2: Renal Safety Auditor with Gemini tool calling and PostgreSQL data

The guide is written for this specific V1 deployment profile:

| Setting | V1 choice |
| --- | --- |
| Data classification | Synthetic or fully de-identified demonstration data only |
| Frontend hosting | Vercel Hobby, Next.js project |
| API hosting | Vercel Hobby, FastAPI project |
| Database | Existing Supabase PostgreSQL project |
| LLM provider | Gemini for both stages |
| Repository topology | Two Vercel projects from the same monorepo |

> [!WARNING]
> This V1 must not process real protected health information (PHI). The current application does not yet provide the authentication, patient-level authorization, audit logging, vendor compliance controls, or PHI-safe logging required for a real clinical deployment.

## 1. Target Architecture

Deploy the repository as two independent Vercel projects:

```text
Browser
  |
  v
medv-web (Next.js on Vercel)
  |
  | /api/* rewrite using API_PROXY_TARGET
  v
medv-api (FastAPI on Vercel)
  |                         |
  |                         +--> Gemini API
  v
Supabase PostgreSQL
```

The projects use these root directories:

| Vercel project | Root directory | Purpose |
| --- | --- | --- |
| `medv-api` | `apps/api` | FastAPI, Stage 1 endpoints, Stage 2 endpoints, SQLAlchemy |
| `medv-web` | `apps/web` | Next.js UI and same-origin API proxy |

The deployment order is important:

1. Secure and prepare the repository.
2. Prepare Supabase and apply migrations.
3. Seed deterministic synthetic Stage 2 data.
4. Deploy and verify `medv-api`.
5. Configure `API_PROXY_TARGET` with the API URL.
6. Deploy and verify `medv-web`.
7. Run end-to-end Stage 1 and Stage 2 smoke tests.

## 2. Release Blockers

Complete every item in this section before the first public deployment.

### 2.1 Rotate the exposed Supabase credential

`apps/api/.env.example` currently contains a complete database connection string with a password. Treat that password as compromised because the file is tracked by Git.

Required actions:

1. Reset the database password in the Supabase dashboard.
2. Revoke or replace any other credential that reused the password.
3. Replace the value in `apps/api/.env.example` with a placeholder such as:

   ```dotenv
   DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
   ```

4. Review repository history and Supabase database logs.
5. Consider removing the credential from Git history if it was valid.
6. Never put a production or preview secret in `.env.example`.

Vercel environment variables, not repository files, must store production secrets.

### 2.2 Commit the intended V1 source

Vercel Git deployments use committed and pushed files only. Before deployment:

```powershell
git status --short
git diff
```

Review and commit all intended Stage 2 safety changes and tests. Do not commit local `.env` files, Vercel credentials, database URLs, or LLM keys.

Confirm that the branch deployed by Vercel contains the intended code:

```powershell
git log -5 --oneline
git status --short
```

The final status should be clean.

### 2.3 Finish the Stage 2 safety gate

Stage 2 produces a clinical-looking dose safety verdict. For V1, the backend must at minimum enforce these invariants in code rather than relying only on the system prompt:

- The patient identifier passed to database tools must come from validated request data.
- The model must not supply serum creatinine or other trusted biomarkers.
- A non-`insufficient_data` verdict must require successful medication and renal evidence tools.
- The report's patient, medication, dose, metric, renal value, bracket, and verdict must match server-observed tool results.
- Missing or contradictory evidence must force `insufficient_data`.
- Raw internal exceptions must not be returned to the UI.

For a stronger implementation, calculate the guideline bracket and verdict deterministically in Python and use the LLM only for extraction or rationale generation.

### 2.4 Regenerate API contracts

The frontend currently has a handwritten Stage 2 response interface. Regenerate the OpenAPI and TypeScript artifacts after the renal route and schema are finalized:

```powershell
pnpm contracts:generate
pnpm contracts:check
```

Verify that both files include `/api/v1/renal/evaluate`:

- `packages/api-client/openapi/openapi.json`
- `packages/api-client/src/generated/schema.d.ts`

Replace unchecked frontend response casts with generated types and runtime validation before treating API responses as trusted.

### 2.5 Make Stage 2 seed data reproducible

The existing Synthea seed script is not deployment-ready:

- `apps/api/scripts/seed_synthea.py` contains a hard-coded Windows path.
- The source CSV files are outside the repository.
- It seeds patients and labs but not medications or renal dosing guidelines.
- The UI samples use `patient-001`, which is not created by the current seed.

Before deploying Stage 2:

1. Make the Synthea CSV directory a command argument or environment variable.
2. Add an idempotent medication and renal-guideline seed based on a reviewed source.
3. Add a deterministic synthetic patient and renal labs for each sample workflow.
4. Update the frontend samples to use actual seeded identifiers.
5. Record the seed version and guideline source.
6. Do not invent clinical bracket values merely to make a sample pass.

## 3. Repository Changes Required for Vercel

### 3.1 Add the API Vercel configuration

Vercel recognizes `apps/api/app/main.py` as a supported FastAPI entrypoint. A wrapper under `api/index.py` is not required.

Create `apps/api/vercel.json`:

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "functions": {
    "app/main.py": {
      "maxDuration": 300,
      "excludeFiles": "{tests/**,scripts/**,**/__pycache__/**,**/*.pyc}"
    }
  }
}
```

Vercel Hobby currently permits a maximum function duration of 300 seconds with Fluid compute. Application-level deadlines should expire before that platform limit, preferably around 240 seconds for the entire request.

### 3.2 Pin the Python version

Vercel supports Python 3.12, 3.13, and 3.14. The repository documentation expects Python 3.13.

Create `apps/api/.python-version`:

```text
3.13
```

Use the same Python minor version locally, in CI, and on Vercel.

### 3.3 Pin production Python dependencies

`apps/api/requirements.txt` currently uses broad minimum versions and includes test-only packages. Before release:

1. Pin versions that have passed the complete test suite.
2. Keep only runtime dependencies in `requirements.txt`.
3. Move `pytest`, `pytest-asyncio`, `aiosqlite`, and similar development packages to a development requirements file.
4. Keep Alembic and its migration driver available to the external migration job, not necessarily the runtime function.
5. Confirm the deployed Python function is below Vercel's uncompressed bundle limit.

### 3.4 Make SQLAlchemy safe for serverless execution

The current engine permits up to 30 connections per warm Vercel function instance:

```text
pool_size=10
max_overflow=20
```

That configuration can exhaust Supabase connections when Vercel scales horizontally.

For this low-traffic V1 demo, use the Supabase transaction pooler and configure the application-side SQLAlchemy pool to at most one connection per warm instance:

```text
pool_size=1
max_overflow=0
pool_pre_ping=true
```

Alternatively, use SQLAlchemy `NullPool` after measuring connection latency. Do not retain the existing `10 + 20` pool.

The Supabase shared transaction pooler does not support prepared statements. Configure asyncpg statement caching off and require SSL. Validate the exact SQLAlchemy/asyncpg settings against a preview deployment before production.

Also address the Stage 2 request lifecycle: a database transaction should not remain checked out while the application waits for Gemini. Prefer short-lived read sessions around each tool query or end the transaction before awaiting the next provider call.

### 3.5 Separate runtime and migration database URLs

Use two database URLs:

| Variable | Connection mode | Used by |
| --- | --- | --- |
| `DATABASE_URL` | Supabase transaction pooler, port 6543 | FastAPI runtime on Vercel |
| `MIGRATION_DATABASE_URL` | Direct connection or session pooler, port 5432 | Alembic from a trusted workstation or CI |

Update `Settings.get_sync_database_url()` to prefer `MIGRATION_DATABASE_URL`. Until that change exists, set `DATABASE_URL` temporarily to the migration URL only in the shell that runs Alembic. Never replace the Vercel runtime variable with the direct migration URL.

### 3.6 Add application and provider deadlines

Both stages need timeouts shorter than the 300-second Vercel function limit.

Recommended V1 limits:

| Operation | Suggested upper bound |
| --- | --- |
| Single provider request | 45-60 seconds |
| Stage 1 complete request | 180 seconds |
| Stage 2 complete request | 240 seconds |
| Database statement | 10-15 seconds |

Keep retries bounded. Retrying every provider failure can exceed the platform duration and multiply cost.

### 3.7 Fix API documentation routing

The sidebar currently links to `/docs` on the web origin, while Next.js only rewrites `/api/*`. The link will return a Next.js 404 after deployment.

Either link directly to the API project's `/docs` URL or add these rewrites in `apps/web/next.config.ts`:

```ts
{
  source: "/docs",
  destination: `${apiTarget}/docs`,
},
{
  source: "/redoc",
  destination: `${apiTarget}/redoc`,
},
{
  source: "/openapi.json",
  destination: `${apiTarget}/openapi.json`,
},
```

For a synthetic public demo, documentation may remain enabled. Disable or protect it before any non-demo deployment.

## 4. Pre-Deployment Verification

### 4.1 Install dependencies

From the repository root:

```powershell
corepack enable
pnpm install --frozen-lockfile
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r apps/api/requirements.txt
```

### 4.2 Run repository checks

Run all checks from a clean checkout with the intended V1 environment:

```powershell
pnpm contracts:generate
pnpm contracts:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Also run the browser tests:

```powershell
pnpm test:e2e
```

Add a Stage 2 browser E2E test before release. The existing E2E coverage only verifies Stage 1.

### 4.3 Required Stage 2 tests

The release test suite should include:

- A successful CrCl case.
- A successful eGFR case.
- A dose-adjustment case.
- Missing patient, medication, guideline, lab, weight, age, and sex cases.
- Stale, future-dated, zero, negative, and implausible labs.
- A model attempting to use a different patient identifier.
- A model attempting to provide serum creatinine.
- A model returning a verdict without required tools.
- A report contradicting tool values or the selected guideline bracket.
- Ambiguous medication names and brand names.
- Provider timeout, rate limit, malformed output, and retry exhaustion.
- Database unavailable and pool exhausted scenarios.

## 5. Supabase Preparation

### 5.1 Rotate the password first

Reset the exposed database password before copying any new connection string. Updating the password invalidates old connections, so update local secrets and Vercel only after rotation.

### 5.2 Collect two connection strings

In the Supabase dashboard, open **Connect**.

For the Vercel runtime:

1. Select **Transaction pooler**.
2. Copy the shared pooler URL.
3. Confirm it uses the provider-supplied pooler host, pooler username, and port `6543`.
4. Replace the password placeholder with the rotated, URL-encoded password.
5. Require SSL.
6. Configure asyncpg prepared-statement caching off in application code.

For Alembic migrations:

1. Prefer the direct connection when the migration machine supports Supabase IPv6.
2. Otherwise use the Supabase session pooler on port `5432`.
3. Store this separately as `MIGRATION_DATABASE_URL`.

Do not construct a pooler hostname manually. Copy it from the Supabase dashboard.

### 5.3 Use least-privilege roles

Do not run the deployed API as the Supabase `postgres` owner role.

Create separate roles:

- Migration role: allowed to create and alter the application schema.
- Runtime role: only the `SELECT`, `INSERT`, `UPDATE`, and `DELETE` privileges required by the API.

For this V1, Stage 2 currently performs reads. Keep runtime privileges correspondingly narrow.

### 5.4 Back up before migration

Before applying Alembic migrations:

1. Verify the database is the synthetic V1 database.
2. Take a Supabase backup or snapshot where available.
3. Record the existing Alembic revision.
4. Verify the migration chain is complete and no previously applied revision was deleted.

### 5.5 Apply Alembic migrations

Run migrations from a trusted workstation or CI job, never from every Vercel function startup.

With a separate migration URL implemented:

```powershell
$env:MIGRATION_DATABASE_URL = "<SUPABASE_DIRECT_OR_SESSION_POOLER_URL>"
pnpm --filter @medv/api db:status
pnpm --filter @medv/api db:migrate
pnpm --filter @medv/api db:status
```

If the code has not yet added `MIGRATION_DATABASE_URL`, use a temporary local shell variable:

```powershell
$env:DATABASE_URL = "<SUPABASE_DIRECT_OR_SESSION_POOLER_URL>"
pnpm --filter @medv/api db:status
pnpm --filter @medv/api db:migrate
pnpm --filter @medv/api db:status
Remove-Item Env:DATABASE_URL
```

Do not place this URL in shell history, screenshots, tickets, or committed files.

### 5.6 Verify the schema

The database should contain:

- `alembic_version`
- `patients`
- `patient_labs`
- `medications`
- `renal_dosing_guidelines`

Example verification queries:

```sql
select version_num from alembic_version;
select count(*) from patients;
select count(*) from patient_labs;
select count(*) from medications;
select count(*) from renal_dosing_guidelines;
```

### 5.7 Seed synthetic V1 data

Run seeds outside Vercel after they have been made portable and idempotent.

The seed must provide at least:

- One synthetic patient with a recent SCr result for a CrCl workflow.
- One synthetic patient with a recent eGFR result for an eGFR workflow.
- Valid age, sex, measured weight, and collection timestamps.
- Gabapentin or another reviewed CrCl-based medication guideline.
- Metformin or another reviewed eGFR-based medication guideline.
- One dose that produces `safe`.
- One dose that produces `dose_adjustment_required`.
- One missing-data case.

After seeding, update the Stage 2 UI samples with the real synthetic patient identifiers.

Never run the current destructive lab reseed against a database containing non-synthetic data.

## 6. Deploy the FastAPI Project

### 6.1 Create `medv-api`

In Vercel:

1. Select **Add New -> Project**.
2. Import this Git repository.
3. Set **Root Directory** to `apps/api`.
4. Allow Vercel to detect FastAPI from `requirements.txt` and `app/main.py`.
5. Do not set a Next.js framework preset.
6. Leave Build Command and Output Directory unset unless the Vercel FastAPI detector requires an override.
7. Select Python 3.13 through `.python-version`.
8. Select the Vercel function region nearest the Supabase project.
9. Keep Fluid compute enabled.

Vercel packages the complete FastAPI application as one Python function.

### 6.2 API environment variables

Configure the following for Preview and Production. Use separate values where possible.

| Variable | Required value for V1 | Secret |
| --- | --- | --- |
| `APP_NAME` | `MedV Microservice` | No |
| `APP_VERSION` | V1 release identifier, for example `1.0.0` | No |
| `DEBUG` | `false` | No |
| `API_V1_PREFIX` | `/api/v1` | No |
| `CORS_ORIGINS` | Exact deployed web origins | No |
| `LLM_PROVIDER` | `gemini` | No |
| `LLM_MODEL` | A tested Gemini model supporting structured output and function calling | No |
| `GEMINI_API_KEY` | Gemini API key | Yes |
| `DATABASE_URL` | Supabase transaction-pooler runtime URL | Yes |

Avoid setting the generic `LLM_API_KEY` when `GEMINI_API_KEY` is sufficient. Do not set `OPENAI_API_KEY` for this Gemini-only V1.

The current code shares `LLM_MODEL` between Stage 1 and Stage 2. Select one Gemini model that supports both structured output and function calling. If different models are required, add separate settings before deployment.

Do not configure `MIGRATION_DATABASE_URL` on the runtime project unless an explicit protected migration workflow needs it.

### 6.3 CORS configuration

The UI normally calls the API through a same-origin Next.js rewrite, but the API should still use an explicit allowlist.

Example production value:

```text
CORS_ORIGINS=https://medv-web.vercel.app,https://medv.example
```

Do not use `*`. Do not allow arbitrary `*.vercel.app` origins.

For preview deployments, either:

- use an explicit protected preview origin and a synthetic preview database, or
- keep previews pointed at a stable synthetic demo API and do not treat them as isolated environments.

### 6.4 Deploy API preview

Deploy through the Git integration or Vercel CLI. Dashboard deployment is the simplest path for this two-project monorepo.

Record the stable API project URL, for example:

```text
https://medv-api.vercel.app
```

Do not continue until direct API tests pass.

### 6.5 Verify the API directly

Set the preview URL in PowerShell:

```powershell
$api = "https://medv-api.vercel.app"
```

Verify liveness:

```powershell
Invoke-RestMethod "$api/api/v1/health"
```

Verify readiness:

```powershell
Invoke-RestMethod "$api/api/v1/ready"
```

The current readiness route always reports ready. Before relying on it, update it to check required configuration, a short database query, and the presence of Stage 2 reference data. It should return HTTP 503 when a required dependency is unavailable.

Verify documentation:

```text
https://medv-api.vercel.app/docs
https://medv-api.vercel.app/openapi.json
```

Verify that `/openapi.json` contains both:

```text
/api/v1/audit/evaluate/stream
/api/v1/renal/evaluate
```

## 7. Stage 1 API Verification

### 7.1 Non-streaming request

Use a short synthetic note and rubric:

```powershell
$body = @{
  clinical_note = "Synthetic patient reports low back pain for eight weeks. Physical therapy completed for six weeks."
  policy_rubric = "Criterion 1: symptoms documented. Criterion 2: duration at least six weeks."
  rubric_id = "DEPLOYMENT_SMOKE_001"
  temperature = 0
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "$api/api/v1/audit/evaluate" `
  -ContentType "application/json" `
  -Body $body
```

Confirm the response is a valid `ClinicalGapReport` and does not expose provider internals.

### 7.2 SSE request

Stage 1 must be tested as a real stream, not only as a completed response.

Create a temporary `stage1-smoke.json` outside the repository or in an ignored temporary directory:

```json
{
  "clinical_note": "Synthetic patient reports low back pain for eight weeks.",
  "policy_rubric": "Criterion: symptoms and duration are documented.",
  "rubric_id": "DEPLOYMENT_STREAM_001",
  "temperature": 0
}
```

Then run:

```powershell
curl.exe -N `
  -H "Content-Type: application/json" `
  --data-binary "@stage1-smoke.json" `
  "$api/api/v1/audit/evaluate/stream"
```

Expected sequence:

```text
event: status
event: token
event: token
...
event: done
```

Failure conditions:

- The connection closes before `done`.
- All tokens arrive at once after a long delay.
- Provider or stack-trace details appear in an `error` event.
- The function reaches its duration limit.

## 8. Stage 2 API Verification

Use a patient identifier and medication that were actually inserted into the synthetic Supabase database.

```powershell
$discharge = @{
  patient_id = "<SEEDED_SYNTHETIC_PATIENT_ID>"
  medication_name = "<SEEDED_MEDICATION_NAME>"
  prescribed_daily_dose_mg = 900
} | ConvertTo-Json

$renalBody = @{
  discharge_json = $discharge
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "$api/api/v1/renal/evaluate" `
  -ContentType "application/json" `
  -Body $renalBody
```

Verify all returned fields:

- `patient_id` matches the request-bound identifier.
- `medication_name` matches the selected database medication.
- `prescribed_daily_dose_mg` matches the input.
- `required_renal_metric` matches the stored guideline.
- `renal_metric_value` matches database/tool evidence.
- `verdict` matches a deterministic server-side bracket check.
- `lab_warning` is populated for stale data where applicable.
- `rationale` does not contain secrets or unrelated patient information.
- `tool_trace` does not contain data that should not be exposed publicly.

Run at least three cases:

1. A verified safe dose.
2. A verified dose-adjustment case.
3. An insufficient-data case.

Inspect Vercel duration and Supabase connection count during these requests.

## 9. Deploy the Next.js Project

### 9.1 Create `medv-web`

In Vercel:

1. Import the same Git repository as a second project.
2. Set **Root Directory** to `apps/web`.
3. Select the Next.js framework preset.
4. Set Node.js to version 22.
5. Use the repository's pinned pnpm version through Corepack.
6. Ensure Vercel includes workspace dependencies outside `apps/web`:
   - `packages/api-client`
   - `packages/ui`
   - `packages/typescript-config`
7. Prefer Vercel's detected monorepo install settings.
8. If an explicit install command is required, use:

   ```text
   pnpm install --frozen-lockfile
   ```

9. Use this build command if detection does not select it automatically:

   ```text
   pnpm build
   ```

10. Leave the output directory at the Next.js default.

`output: "standalone"` in `apps/web/next.config.ts` is intended mainly for self-hosting. It is unnecessary on Vercel and may be removed after confirming the normal Vercel build.

### 9.2 Web environment variables

Configure:

| Variable | Value | Environments |
| --- | --- | --- |
| `API_PROXY_TARGET` | Stable `medv-api` HTTPS origin without a trailing slash | Preview and Production |

Example:

```text
API_PROXY_TARGET=https://medv-api.vercel.app
```

This value is consumed while evaluating `next.config.ts`, so changing it requires a new web deployment.

Never expose database or LLM credentials with `NEXT_PUBLIC_*` variables.

### 9.3 Deploy web preview

Deploy the web project only after the API URL has been verified.

Open:

```text
https://<WEB_DEPLOYMENT>/audit
```

Use the browser network panel to confirm requests go to the web origin's `/api/v1/...` paths and are rewritten to the deployed API. No request should target `127.0.0.1` or `localhost`.

## 10. End-to-End Verification

### 10.1 Stage 1 UI

1. Open the Stage 1 workspace.
2. Submit the included synthetic note and rubric.
3. Confirm the status changes from connecting to streaming.
4. Confirm incremental stream chunks appear before completion.
5. Confirm the validated report renders.
6. Start another request and press Stop.
7. Confirm the browser request closes and provider work is cancelled.
8. Confirm no raw provider or server exception is displayed.

### 10.2 Stage 2 UI

1. Select Renal Safety Auditor in the sidebar.
2. Load a sample tied to an actual seeded synthetic patient.
3. Run the audit.
4. Confirm the displayed patient, medication, dose, metric, units, verdict, and rationale are correct.
5. Change the input after a result and verify the old report is cleared or explicitly marked stale.
6. Switch stages during a request and verify the request is cancelled or intentionally preserved with visible status.
7. Test safe, adjustment, and insufficient-data cases.

### 10.3 Mobile and accessibility smoke test

Test at widths of 320px, 375px, 768px, and desktop:

- Header controls do not overflow.
- Start/Stop controls remain reachable.
- The sidebar is not keyboard-focusable while closed.
- Opening the sidebar moves focus appropriately.
- Escape closes the mobile sidebar.
- Focus returns to the opener.
- Active stage is exposed with `aria-current` or equivalent state.

### 10.4 Deployed contract test

Download the deployed API's OpenAPI document and compare it with the committed contract:

```powershell
Invoke-WebRequest "$api/openapi.json" -OutFile "$env:TEMP\medv-openapi.json"
```

The deployed contract should match the release commit.

## 11. Custom Domains

Custom domains are optional for V1, but stable domains simplify configuration.

Suggested domains:

```text
https://medv.example       -> medv-web
https://api.medv.example   -> medv-api
```

After adding domains:

1. Set `API_PROXY_TARGET=https://api.medv.example` in the web project.
2. Set `CORS_ORIGINS=https://medv.example` in the API project.
3. Redeploy both projects.
4. Retest Stage 1 SSE and Stage 2.
5. Confirm HTTPS is enforced.

## 12. Preview Environment Policy

Vercel creates preview deployments for branches and pull requests. A preview web URL does not automatically know the matching API preview URL.

For this Hobby V1, choose one documented policy:

### Option A: Stable synthetic API for all web previews

- Every web preview uses the stable synthetic `medv-api` project URL.
- Preview changes must remain backward compatible with the deployed API.
- This is simplest but does not test API changes from the same branch.

### Option B: Manually paired preview deployments

- Deploy the API branch first.
- Set the web preview's `API_PROXY_TARGET` to that API preview URL.
- Redeploy the web preview.
- Use a separate synthetic preview Supabase project when schema changes are involved.

Vercel Related Projects or Services can automate this later, but they are not required for the V1 Hobby deployment.

Never point untrusted pull-request previews at a database containing real or sensitive data.

## 13. Security and Cost Controls for the Demo

Synthetic data removes PHI risk, but the application still exposes billable LLM endpoints.

Minimum controls:

- Configure Gemini project quotas and budget alerts.
- Configure Vercel usage alerts.
- Configure Supabase connection and usage alerts.
- Add request body limits.
- Add per-IP or per-session rate limits.
- Cap Stage 1 note/rubric sizes and Stage 2 discharge payload size.
- Cap Stage 2 tool calls and total iterations.
- Reject duplicate or repeated tool calls.
- Keep `DEBUG=false`.
- Sanitize client-facing errors.
- Do not log note bodies, discharge payloads, patient names, labs, database URLs, provider responses, or secrets.
- Do not use production-looking patient data in a public demo.

Do not rely on CORS as authentication. CORS controls browser behavior; it does not prevent direct API calls.

## 14. Observability

Monitor all three external systems.

### Vercel

- Function invocation count
- Error rate by route
- Cold starts
- p50, p95, and p99 duration
- Function timeout count
- API and web deployment IDs
- Function bundle size

### Supabase

- Active and waiting connections
- Pooler errors
- Slow queries
- Transaction duration
- Storage and backup status
- Authentication failures

### Gemini

- Request count
- Token usage and cost
- 429 and 5xx responses
- Latency
- Structured-output failures
- Tool-call loops and retry counts

Use opaque request IDs to correlate systems. Do not put clinical content or patient identifiers in the correlation metadata.

## 15. Rollback

### 15.1 Application rollback

Vercel stores previous deployments independently for API and web.

If the API fails:

1. Promote the previous successful `medv-api` deployment.
2. Verify `/api/v1/health` and both stage endpoints.
3. Keep or restore the web version compatible with that API contract.

If the web fails:

1. Promote the previous successful `medv-web` deployment.
2. Verify `API_PROXY_TARGET` still points to the intended API.
3. Run both UI smoke tests.

Record the deployment IDs used for every V1 release.

### 15.2 Database rollback

Prefer application rollback and forward-compatible database migrations. Do not automatically run `alembic downgrade` in production.

Reasons:

- Downgrading the medication migration drops medication and guideline tables.
- Making serum creatinine non-null again can fail if null rows exist.
- A previous application can often run safely against an additive schema.

If a migration or seed corrupts data:

1. Stop or disable Stage 2.
2. Promote a web version that hides Stage 2 if necessary.
3. Restore the Supabase backup or snapshot.
4. Apply a forward repair migration.
5. Re-run deterministic seed verification.

## 16. Troubleshooting

### Web requests target localhost

Cause: `API_PROXY_TARGET` was not set during the web build.

Fix:

1. Set `API_PROXY_TARGET` to the deployed API HTTPS origin.
2. Redeploy `medv-web`.
3. Inspect the browser network panel.

### `/docs` returns a Next.js 404

Cause: the sidebar opens `/docs` on the web project, but only `/api/*` is rewritten.

Fix: add docs rewrites or link directly to the API project's `/docs` URL.

### FastAPI is not detected

Verify:

- API project root is `apps/api`.
- `requirements.txt` includes FastAPI.
- `app/main.py` defines a top-level variable named `app`.
- `.python-version` contains a supported version.
- The Vercel function configuration key is `app/main.py`.

### Database hostname is unreachable

Cause: the direct Supabase endpoint may be IPv6-only.

Fix: use the shared transaction pooler for Vercel runtime and the session pooler for migrations when direct IPv6 is unavailable.

### Prepared statement or PgBouncer errors

Cause: Supabase transaction mode does not support prepared statements.

Fix: disable asyncpg statement caching, verify the transaction-pooler URL, and retest with one application connection per function instance.

### Too many database connections

Cause: each warm function instance creates too many application-side connections.

Fix:

- Reduce SQLAlchemy to `pool_size=1`, `max_overflow=0`, or use `NullPool`.
- Confirm the runtime uses the transaction pooler.
- Shorten transactions held across LLM waits.
- Inspect Supabase connection activity.

### Stage 1 stream arrives all at once

1. Test the API deployment directly with `curl.exe -N`.
2. If direct streaming works, test through the web `/api` rewrite.
3. Verify no proxy or cache transforms `text/event-stream`.
4. Confirm `Cache-Control: no-cache, no-transform`.
5. Confirm the API function has sufficient duration.

### Stage 1 stream times out

- Add bounded provider deadlines.
- Reduce retries.
- Confirm the selected Gemini model is available.
- Keep the complete request below 300 seconds.
- Add safe heartbeat/status frames if long idle periods occur.

### Stage 2 always returns insufficient data

Verify:

- The request patient ID exists exactly in `patients.patient_id`.
- The patient has the required recent SCr or eGFR data.
- Measured weight, age, and sex are valid for CrCl.
- The medication exists.
- Renal guidelines exist for the medication.
- The guideline metric is normalized to `crcl` or `egfr`.
- The model actually called the required tools.

### Stage 2 exceeds function duration

- Add an overall deadline below 300 seconds.
- Reduce `max_iterations` after measuring normal behavior.
- Add per-provider-call timeouts.
- Stop retrying permanent failures.
- Consider moving the agent to a durable workflow before increasing platform limits.

### API says healthy while Stage 2 fails

Cause: `/ready` currently returns a static success response.

Fix: implement real readiness checks for configuration, database connectivity, migration state, and required reference data.

## 17. Final Release Checklist

### Source and secrets

- [ ] Supabase password rotated.
- [ ] Real credential removed from `.env.example` and repository history reviewed.
- [ ] Intended Stage 2 safety changes committed and pushed.
- [ ] Git working tree clean.
- [ ] No `.env`, database URL, or API key committed.

### Repository

- [ ] `apps/api/vercel.json` added.
- [ ] `apps/api/.python-version` added.
- [ ] Python runtime dependencies pinned and reduced.
- [ ] Serverless database pool configured.
- [ ] Provider and application deadlines implemented.
- [ ] Stage 2 seed made portable and complete.
- [ ] Frontend samples reference seeded synthetic IDs.
- [ ] API documentation routing fixed.
- [ ] OpenAPI and TypeScript contracts regenerated.

### Verification

- [ ] Lint passes.
- [ ] Typecheck passes.
- [ ] API tests pass.
- [ ] Web tests pass.
- [ ] Stage 1 E2E passes.
- [ ] Stage 2 E2E passes.
- [ ] Production web build passes.
- [ ] PostgreSQL migration test passes.
- [ ] Adversarial Stage 2 safety tests pass.

### Supabase

- [ ] Runtime transaction-pooler URL created.
- [ ] Migration URL created separately.
- [ ] SSL required.
- [ ] Runtime role uses least privilege.
- [ ] Backup taken before migration.
- [ ] Alembic upgraded successfully.
- [ ] Synthetic patient/lab data seeded.
- [ ] Medication and guideline data seeded.
- [ ] Connection count verified under concurrent requests.

### Vercel API

- [ ] Root directory is `apps/api`.
- [ ] Python 3.13 detected.
- [ ] Function duration is 300 seconds.
- [ ] Region is near Supabase.
- [ ] Gemini and database secrets configured.
- [ ] `DEBUG=false`.
- [ ] Health and readiness checked.
- [ ] Stage 1 direct SSE checked.
- [ ] Stage 2 direct request checked.

### Vercel web

- [ ] Root directory is `apps/web`.
- [ ] Node.js 22 selected.
- [ ] pnpm workspace packages included.
- [ ] `API_PROXY_TARGET` points to the deployed API.
- [ ] No browser request targets localhost.
- [ ] Stage 1 streams through the rewrite.
- [ ] Stage 2 renders verified synthetic results.
- [ ] Mobile and keyboard smoke tests pass.

### Demo policy

- [ ] Only synthetic or fully de-identified data is used.
- [ ] Gemini quota and budget controls enabled.
- [ ] Rate and payload limits enabled.
- [ ] Logs contain no clinical payloads or secrets.
- [ ] The UI clearly identifies the application as a V1 demonstration.

## 18. Official References

- Vercel FastAPI deployment: <https://vercel.com/docs/frameworks/backend/fastapi>
- Vercel Python runtime: <https://vercel.com/docs/functions/runtimes/python>
- Vercel function duration: <https://vercel.com/docs/functions/configuring-functions/duration>
- Vercel monorepos: <https://vercel.com/docs/monorepos>
- Supabase PostgreSQL connections: <https://supabase.com/docs/guides/database/connecting-to-postgres>
- Supabase serverless drivers: <https://supabase.com/docs/guides/database/connecting-to-postgres/serverless-drivers>

The Vercel and Supabase limits in this guide were checked against documentation available in November 2026. Recheck plan limits and runtime support before each release.
