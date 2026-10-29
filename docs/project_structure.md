# Project Structure & Architecture

This document describes the architectural layout of `MedV_micro_service` and provides a quick guide for extending it with new endpoints.

---

## 1. Directory Layout

```
MedV_micro_service/
├── .env                       # Local environment variables (do not commit)
├── .env.example               # Template for environment configuration
├── .gitignore                 # Files and folders ignored by Git
├── pytest.ini                 # Pytest configuration and warning filters
├── README.md                  # Project overview and quick links
├── requirements.txt           # Python package dependencies
├── docs/                      # Project documentation
│   ├── getting_started.md     # Setup, venv, and initial formalities
│   ├── running_and_testing.md # Starting server, docs, and test commands
│   └── project_structure.md   # Architectural breakdown (this file)
├── app/                       # Application source code
│   ├── __init__.py
│   ├── main.py                # FastAPI initialization, middleware, router registration
│   ├── core/                  # Core modules and configurations
│   │   ├── __init__.py
│   │   └── config.py          # Pydantic Settings management
│   └── api/                   # API routing layer
│       ├── __init__.py
│       └── v1/                # Version 1 API routes
│           ├── __init__.py
│           └── health.py      # Health & readiness endpoints
└── tests/                     # Automated test suite
    ├── __init__.py
    ├── conftest.py            # Global test fixtures (e.g. TestClient)
    └── test_health.py         # Tests for health endpoints
```

---

## 2. Key Modules & Responsibilities

| Path | Purpose |
| :--- | :--- |
| `app/main.py` | Entrypoint. Sets up the FastAPI application, CORS middleware, lifespan events, and registers top-level routers. |
| `app/core/config.py` | Reads environment variables with `pydantic-settings` into a strongly-typed `Settings` object. |
| `app/api/v1/health.py` | Contains system health monitoring endpoints (`/health`, `/ready`). |
| `tests/conftest.py` | Houses test fixtures, including the session-scoped `client` fixture using FastAPI's `TestClient`. |
| `tests/test_health.py` | Verifies status codes and JSON payloads for root and health routes. |

---

## 3. Guide: Adding a New Feature / Endpoint

When you are ready to expand the microservice (e.g., adding medical data or vision endpoints):

1. **Define Schema (DTO)**:
   Create a schema file (e.g., `app/schemas/item.py`) using `pydantic.BaseModel` to validate input and output data.

2. **Create the Route Handler**:
   Create a route file (e.g., `app/api/v1/items.py`):
   ```python
   from fastapi import APIRouter

   router = APIRouter(prefix="/items", tags=["Items"])

   @router.get("/")
   def get_items():
       return [{"id": 1, "name": "Item 1"}]
   ```

3. **Register the Router in `app/main.py`**:
   ```python
   from app.api.v1.items import router as items_router
   app.include_router(items_router, prefix=settings.API_V1_PREFIX)
   ```

4. **Write an Automated Test**:
   Create `tests/test_items.py`:
   ```python
   def test_get_items(client):
       response = client.get("/api/v1/items")
       assert response.status_code == 200
       assert isinstance(response.json(), list)
   ```

5. **Run Tests**:
   ```powershell
   pytest -v
   ```

