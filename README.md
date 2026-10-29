# MedV Microservice

FastAPI microservice featuring structured settings validation, CORS configuration, and an automated test suite.

---

## Documentation

Comprehensive guides are organized in the [`docs/`](file:///e:/Projects/MedV_micro_service/docs/) directory:

- 📖 **[Getting Started & Setup Guide](file:///e:/Projects/MedV_micro_service/docs/getting_started.md)**: Virtual environment setup, PowerShell formalities, dependency installation, and `.env` configuration.
- 🚀 **[Running & Testing Guide](file:///e:/Projects/MedV_micro_service/docs/running_and_testing.md)**: Launching Uvicorn, accessing Swagger UI `/docs`, manual CLI testing, and automated `pytest` commands.
- 🏛️ **[Project Structure & Architecture](file:///e:/Projects/MedV_micro_service/docs/project_structure.md)**: Folder layout, architectural layers, and instructions for adding new endpoints and tests.

---

## Quick Reference

### 1. Activate Environment
```powershell
.venv\Scripts\Activate.ps1
```

### 2. Start Development Server
```powershell
uvicorn app.main:app --reload --port 8000
```
- Interactive Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health Check: [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

### 3. Run Test Suite
```powershell
pytest -v
```
