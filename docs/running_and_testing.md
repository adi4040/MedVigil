# Running the Server & Testing Endpoints

This guide details how to launch the FastAPI server, interact with the API endpoints, and execute automated tests.

---

## 1. Running the Development Server

Make sure your virtual environment is active:
```powershell
.venv\Scripts\Activate.ps1
```

Start the Uvicorn ASGI server with live reloading enabled:
```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Server Flag Breakdown:
- `app.main:app`: Refers to the `app` instance inside `app/main.py`.
- `--reload`: Auto-reloads the server whenever code changes are saved.
- `--host 127.0.0.1`: Binds the server to localhost (use `0.0.0.0` for Docker/network exposure).
- `--port 8000`: The local port to listen on.

---

## 2. Interactive Documentation & Endpoints

Once the server is running, you can explore and test the endpoints directly in your browser:

| Interface | URL | Description |
| :--- | :--- | :--- |
| **Swagger UI** | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) | Interactive API exploration and testing |
| **ReDoc UI** | [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc) | Clean, responsive technical API documentation |
| **Root Welcome** | [http://127.0.0.1:8000/](http://127.0.0.1:8000/) | Service welcome message |
| **Health Check** | [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health) | Returns service health, name, and version |
| **Readiness Check** | [http://127.0.0.1:8000/api/v1/ready](http://127.0.0.1:8000/api/v1/ready) | Liveness / readiness probe for orchestration |
| **Clinical Audit** | `POST http://127.0.0.1:8000/api/v1/audit/evaluate` | Evaluates clinical note against policy rubric |
| **Audit SSE Stream** | `POST http://127.0.0.1:8000/api/v1/audit/evaluate/stream` | Streams real-time token deltas and validated report via SSE |

---

## 3. Manual Endpoint Testing (CLI)

You can test the endpoints directly from PowerShell without leaving the terminal:

### Root Endpoint:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/" -Method Get
```

### Health Check Endpoint:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get
```

### Clinical Audit Endpoint:
```powershell
$body = @{
    clinical_note = (Get-Content clinical_notes/note_001.txt -Raw)
    policy_rubric = (Get-Content policy_rubrics/mri_lumbar_spine.txt -Raw)
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/audit/evaluate" -Method Post -ContentType "application/json" -Body $body
```
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/health" -Method Get
```

### Using `curl.exe`:
```powershell
curl.exe -i http://127.0.0.1:8000/api/v1/health
```

### Testing the SSE Streaming Endpoint with `curl.exe`:
```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/audit/evaluate/stream" `
  -H "Content-Type: application/json" `
  -d '{\"clinical_note\": \"Patient has severe back pain for 8 weeks.\", \"policy_rubric\": \"RUBRIC ID: MRI_01\n1. Symptoms and Duration\"}'
```
*(The `-N` flag disables buffering so you can see SSE chunks stream in real time.)*

---

## 4. Automated Testing with Pytest

The project uses `pytest` alongside FastAPI's `TestClient` (backed by `httpx`).

### Run all tests:
```powershell
pytest -v
```

### Run a specific test file:
```powershell
pytest tests/test_health.py -v
```

### Run tests with print outputs displayed:
```powershell
pytest -v -s
```

> [!NOTE]
> All automated tests execute in-process without needing a running Uvicorn server, making them fast and suitable for continuous integration (CI) pipelines.



---

## 5. Stage 1 Evaluation Benchmark Runner

You can evaluate your synthetic clinical notes against ground-truth expectations in [`eval_cases/eval_cases.json`](file:///e:/Projects/MedV_micro_service/eval_cases/eval_cases.json) using the dedicated evaluation runner:

### Run all 5 evaluation cases:
```powershell
python scripts/run_eval.py
```

### Run a specific evaluation case:
```powershell
python scripts/run_eval.py --case-id eval_001
```

### Run with offline Mock client (zero API cost):
```powershell
python scripts/run_eval.py --provider mock
```

### Custom model or output path:
```powershell
python scripts/run_eval.py --model gemini-2.5-pro --output eval_cases/pro_results.json
```

Detailed metrics and per-criterion comparison logs are automatically exported to [`eval_cases/eval_results.json`](file:///e:/Projects/MedV_micro_service/eval_cases/eval_results.json).
