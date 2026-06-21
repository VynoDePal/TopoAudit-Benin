import json
from pathlib import Path

from app.main import app
from scripts.generate_openapi import OPENAPI_OUTPUT_PATH


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def load_committed_openapi_spec() -> dict:
    return json.loads((REPOSITORY_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))


def test_committed_openapi_spec_matches_fastapi_schema():
    assert load_committed_openapi_spec() == app.openapi()


def test_openapi_spec_includes_every_documented_fastapi_endpoint():
    spec = load_committed_openapi_spec()

    assert set(spec["paths"]) == set(app.openapi()["paths"])


def test_openapi_spec_documents_multi_parcel_audit_contract():
    spec = load_committed_openapi_spec()

    assert OPENAPI_OUTPUT_PATH == REPOSITORY_ROOT / "docs" / "openapi.json"
    assert spec["paths"]["/api/projects/{project_id}/audit"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/AuditResponse"
    assert spec["paths"]["/api/projects/{project_id}/documents"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/DocumentUploadResponse"
    assert spec["paths"]["/api/projects/{project_id}/audit/report.pdf"]["post"]["responses"]["200"]["content"] == {"application/pdf": {}}

    audit_response = spec["components"]["schemas"]["AuditResponse"]
    assert audit_response["properties"]["parcels"]["items"]["$ref"] == "#/components/schemas/ParcelAuditResult"

    parcel_result = spec["components"]["schemas"]["ParcelAuditResult"]
    assert {"parcel_id", "label", "declared_surface_m2", "calculated_surface_m2", "invalid_geometry"}.issubset(
        parcel_result["properties"]
    )
