from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.database import get_db
from app.main import app
from app.ocr import MOCK_OCR_TEXT


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class FakeEndToEndSession:
    def __init__(self, *, status="UPLOADED", audit_inputs=None, parcel_rows=None) -> None:
        self.status = status
        self.audit_inputs = audit_inputs
        self.parcel_rows = parcel_rows or []
        self.committed = False
        self.documents = {
            "doc-clear-wgs84": {
                "id": "doc-clear-wgs84",
                "project_id": "project-clear-wgs84",
                "content_type": "image/png",
                "storage_path": "/tmp/clear-wgs84.png",
            },
            "doc-blur": {
                "id": "doc-blur",
                "project_id": "project-blur",
                "content_type": "image/png",
                "storage_path": "/tmp/blur.png",
            },
        }

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM parcels p" in sql:
            return FakeResult(rows=self.parcel_rows)
        if "FROM audit_inputs" in sql:
            return FakeResult(self.audit_inputs)
        if "FROM documents" in sql:
            return FakeResult(self.documents.get(params["document_id"]))
        if "FROM projects" in sql:
            return FakeResult({"id": params["project_id"], "status": self.status})
        if "UPDATE projects SET status" in sql:
            self.status = params["status"]
            return FakeResult(None)
        return FakeResult(None)

    def commit(self):
        self.committed = True


def override_db(session: FakeEndToEndSession):
    def _override():
        yield session

    return _override


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return " ".join(page.extract_text() for page in reader.pages)


def test_e2e_clear_wgs84_image_runs_ocr_validation_audit_and_pdf():
    session = FakeEndToEndSession(
        audit_inputs={
            "extraction_score": 96,
            "declared_surface_m2": 100.0,
            "calculated_surface_m2": 101.0,
            "invalid_geometry": False,
        }
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    ocr_response = client.post("/api/projects/project-clear-wgs84/documents/doc-clear-wgs84/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["provider"] == "mock"
    assert "Surface déclarée" in ocr_response.json()["text"]
    assert session.status == "OCR_EXTRACTED"

    validation_response = client.post(
        "/api/geometry/validate-polygon",
        json={
            "source_crs": "EPSG:4326",
            "coordinates": [[2.13, 6.4], [2.131, 6.4], [2.131, 6.401], [2.13, 6.401]],
        },
    )
    assert validation_response.status_code == 200
    assert validation_response.json()["valid"] is True
    assert validation_response.json()["orientation"] == "xy"

    assert client.post("/api/projects/project-clear-wgs84/validate").status_code == 200
    audit_response = client.post("/api/projects/project-clear-wgs84/audit")
    assert audit_response.status_code == 200
    assert audit_response.json()["risk_level"] == "low"
    assert audit_response.json()["technical_score"] == 92

    session.status = "VALIDATED"
    pdf_response = client.post("/api/projects/project-clear-wgs84/audit/report.pdf")
    assert pdf_response.status_code == 200
    assert pdf_response.content.startswith(b"%PDF")
    assert "ne constitue pas un avis juridique" in " ".join(extract_pdf_text(pdf_response.content).split())


def test_e2e_blurry_image_keeps_low_extraction_score_warning_path():
    session = FakeEndToEndSession(
        audit_inputs={
            "extraction_score": 48,
            "declared_surface_m2": 549.0,
            "calculated_surface_m2": 549.5,
            "invalid_geometry": False,
        }
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    ocr_response = client.post("/api/projects/project-blur/documents/doc-blur/ocr")
    assert ocr_response.status_code == 200
    assert ocr_response.json()["text"] == MOCK_OCR_TEXT

    assert client.post("/api/projects/project-blur/validate").status_code == 200
    audit_response = client.post("/api/projects/project-blur/audit")
    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert payload["extraction_score"] == 48
    assert payload["risk_level"] == "low"
    assert payload["warnings"] == ["Aucune comparaison cadastrale officielle effectuée."]


def test_e2e_local_utm_coordinates_transform_and_score_low_surface_delta():
    client = TestClient(app)

    geometry_response = client.post(
        "/api/geometry/validate-polygon",
        json={
            "source_crs": "EPSG:32631",
            "coordinates": [
                [403825.84, 707630.38],
                [403836.57, 707630.38],
                [403836.57, 707626.36],
                [403825.84, 707626.36],
            ],
        },
    )

    assert geometry_response.status_code == 200
    payload = geometry_response.json()
    assert payload["valid"] is True
    assert payload["area_m2"] == pytest.approx(43.1346)
    assert payload["coordinates"][0] == [2.130353989859776, 6.401151000268496]

    score_response = client.post(
        "/api/risk/score-surface",
        json={"declared_surface_m2": 43.0, "calculated_surface_m2": payload["area_m2"]},
    )
    assert score_response.status_code == 200
    assert score_response.json()["risk_level"] == "low"


def test_e2e_surface_deviation_case_becomes_high_risk_and_pdf_mentions_score():
    session = FakeEndToEndSession(
        status="VALIDATED",
        audit_inputs={
            "extraction_score": 88,
            "declared_surface_m2": 549.0,
            "calculated_surface_m2": 620.0,
            "invalid_geometry": False,
        },
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    audit_response = client.post("/api/projects/project-surface-gap/audit")
    assert audit_response.status_code == 200
    assert audit_response.json()["risk_level"] == "high"
    assert audit_response.json()["technical_score"] == 48
    assert "Écart élevé" in audit_response.json()["warnings"][1]

    session.status = "VALIDATED"
    pdf_response = client.post("/api/projects/project-surface-gap/audit/report.pdf")
    pdf_text = extract_pdf_text(pdf_response.content)
    assert pdf_response.status_code == 200
    assert "48/100" in pdf_text
    assert "Élevé" in pdf_text


def test_e2e_self_intersecting_polygon_prioritizes_invalid_geometry_high_risk():
    session = FakeEndToEndSession(
        status="VALIDATED",
        audit_inputs={
            "extraction_score": 81,
            "declared_surface_m2": 100.0,
            "calculated_surface_m2": 100.0,
            "invalid_geometry": True,
        },
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    geometry_response = client.post(
        "/api/geometry/validate-polygon",
        json={
            "source_crs": "EPSG:4326",
            "coordinates": [[2.13, 6.4], [2.14, 6.41], [2.13, 6.41], [2.14, 6.4]],
        },
    )
    assert geometry_response.status_code == 200
    assert geometry_response.json()["self_intersecting"] is True
    assert any(issue["code"] == "self_intersection" for issue in geometry_response.json()["issues"])

    audit_response = client.post("/api/projects/project-bowtie/audit")
    assert audit_response.status_code == 200
    assert audit_response.json()["risk_level"] == "high"
    assert "Incohérence géométrique" in audit_response.json()["warnings"][1]


def test_e2e_xy_inversion_is_normalized_before_audit():
    session = FakeEndToEndSession(
        status="VALIDATED",
        audit_inputs={
            "extraction_score": 90,
            "declared_surface_m2": 100.0,
            "calculated_surface_m2": 101.0,
            "invalid_geometry": False,
        },
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    geometry_response = client.post(
        "/api/geometry/validate-polygon",
        json={
            "source_crs": "EPSG:4326",
            "coordinates": [[6.4, 2.13], [6.4, 2.14], [6.41, 2.14], [6.41, 2.13]],
        },
    )
    assert geometry_response.status_code == 200
    payload = geometry_response.json()
    assert payload["valid"] is True
    assert payload["orientation"] == "yx"
    assert payload["issues"][0]["code"] == "xy_inversion_detected"
    assert payload["coordinates"] == [[2.13, 6.4], [2.14, 6.4], [2.14, 6.41], [2.13, 6.41], [2.13, 6.4]]

    audit_response = client.post("/api/projects/project-inverted/audit")
    assert audit_response.status_code == 200
    assert audit_response.json()["risk_level"] == "low"


def test_e2e_multi_parcel_validates_each_parcel_and_reports_highest_risk():
    parcels = [
        [[2.13, 6.4], [2.131, 6.4], [2.131, 6.401], [2.13, 6.401]],
        [[2.132, 6.4], [2.134, 6.4], [2.134, 6.402], [2.132, 6.402]],
    ]
    parcel_rows = [
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 549,
            "detected_crs": "EPSG:4326",
            "source_x": x,
            "source_y": y,
        }
        for x, y in parcels[0]
    ] + [
        {
            "parcel_id": "parcel-b",
            "label": "Parcelle B",
            "declared_surface_m2": 250,
            "detected_crs": "EPSG:4326",
            "source_x": x,
            "source_y": y,
        }
        for x, y in parcels[1]
    ]
    session = FakeEndToEndSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    geometry_payloads = [
        client.post("/api/geometry/validate-polygon", json={"source_crs": "EPSG:4326", "coordinates": parcel}).json()
        for parcel in parcels
    ]

    assert [payload["valid"] for payload in geometry_payloads] == [True, True]
    assert all(payload["coordinates"][0] == parcel[0] for payload, parcel in zip(geometry_payloads, parcels))

    audit_response = client.post("/api/projects/project-multi-parcel/audit")
    assert audit_response.status_code == 200
    payload = audit_response.json()
    assert payload["risk_level"] == "moderate"
    assert payload["technical_score"] == 60
    assert [parcel["label"] for parcel in payload["parcels"]] == ["Parcelle A", "Parcelle B"]
    assert all(parcel["calculated_surface_m2"] is None for parcel in payload["parcels"])
