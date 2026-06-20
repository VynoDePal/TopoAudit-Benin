"""Generate the committed OpenAPI specification from the FastAPI application."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OPENAPI_OUTPUT_PATH = REPOSITORY_ROOT / "docs" / "openapi.json"


def generate_openapi_spec(output_path: Path = OPENAPI_OUTPUT_PATH) -> dict[str, object]:
    """Write the current FastAPI OpenAPI schema to ``output_path`` and return it."""
    schema = app.openapi()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return schema


if __name__ == "__main__":
    generate_openapi_spec()
    print(f"OpenAPI specification written to {OPENAPI_OUTPUT_PATH}")
