# Getting Started & Setup Guide

This guide covers the initial environment setup and formalities required to work with the **MedV Microservice**.

---

## 1. Prerequisites

- **Python**: Version `3.13+` installed on your system.
- **Shell**: PowerShell (Windows) or terminal with administrative/execution permissions.
- **Git** (optional): For version control.

Verify your Python installation:
```powershell
python --version
```

---

## 2. Environment Setup (Step-by-Step)

### Step 2.1: Create the Virtual Environment
An isolated virtual environment ensures that the microservice dependencies do not conflict with system-wide Python packages.

From the repository root (`MedV_micro_service/`):
```powershell
python -m venv .venv
```

### Step 2.2: Activate the Virtual Environment
On Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

> [!IMPORTANT]
> **PowerShell Execution Policy Warning**:
> If you encounter an error stating `running scripts is disabled on this system`, run this command in your PowerShell session to temporarily allow the script to execute:
> ```powershell
> Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
> .venv\Scripts\Activate.ps1
> ```
> You will know activation was successful when your prompt is prefixed with `(.venv)`.

### Step 2.3: Upgrade Package Installer (`pip`)
```powershell
python -m pip install --upgrade pip
```

### Step 2.4: Install Dependencies
Install all required production and testing libraries:
```powershell
pip install -r requirements.txt
```

---

## 3. Environment Configuration (`.env`)

The microservice uses `pydantic-settings` to load and validate environment variables at startup.

1. Copy the template `.env.example` file to create your local `.env`:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Verify or update the variables in `.env`:
   ```ini
   APP_NAME=MedV Microservice
   APP_VERSION=0.1.0
   DEBUG=false
   API_V1_PREFIX=/api/v1
   ```

---

## 4. Summary Checklist

- [x] Python 3.13+ verified
- [x] `.venv` virtual environment created
- [x] `.venv` activated (with execution policy bypassed if needed)
- [x] Packages installed from `requirements.txt`
- [x] `.env` configuration file populated

