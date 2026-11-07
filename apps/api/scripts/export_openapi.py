#!/usr/bin/env python3
"""Export the FastAPI OpenAPI contract deterministically for frontend generation."""

import json
import os
import sys
from pathlib import Path


API_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = API_ROOT.parents[1]
OUTPUT_PATH = REPOSITORY_ROOT / "packages" / "api-client" / "openapi" / "openapi.json"

sys.path.insert(0, str(API_ROOT))
os.environ.setdefault("LLM_PROVIDER", "mock")

from app.main import app  # noqa: E402


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI contract written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
