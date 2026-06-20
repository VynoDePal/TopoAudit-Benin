from uuid import UUID

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeWorkflowSession:
    def __init__(
        self,
        *,
        project_exists: bool = True,
        status: str | None = "UPLOADED",
        audit_inputs: dict[str, object] | None = None,
    ) -> None:
        self.project_exists = project_exists
        self.status = status
        self.audit_inputs = audit_inputs
        self.committed = False

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM audit_inputs" in sql:
            return FakeResult(self.audit_inputs)
        if "FROM projects" in sql:
            if self.project_exists:
                return FakeResult({"id": params["project_id"], "status": self.status})
            return FakeResult(None)
        if "UPDATE projects SET status" in sql:
            self.status = params["status"]
            return FakeResult(None)
        return FakeResult(None)

    def commit(self):
        self.committed = True


def override_db(session: FakeWorkflowSession):
    def _override():
        yield session

    return _override


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_workflow_endpoint_returns_current_project_state():
    session = FakeWorkflowSession(status="OCR_EXTRACTED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.get("/api/projects/project-1/workflow")

    assert response.status_code == 200
    assert response.json() == {"project_id": "project-1", "state": "OCR_EXTRACTED"}


def test_validation_requires_ocr_extracted_state():
    session = FakeWorkflowSession(status="UPLOADED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/validate")

    assert response.status_code == 409
    assert session.status == "UPLOADED"
    assert session.committed is False


def test_validation_moves_project_to_validated():
    session = FakeWorkflowSession(status="OCR_EXTRACTED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/validate")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["state"] == "VALIDATED"
    assert payload["validated_at"]
    assert session.status == "VALIDATED"
    assert session.committed is True


def test_audit_requires_validated_state():
    session = FakeWorkflowSession(status="OCR_EXTRACTED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 409
    assert session.status == "OCR_EXTRACTED"


def test_audit_moves_project_to_audited_and_returns_default_scores():
    session = FakeWorkflowSession(status="VALIDATED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["state"] == "AUDITED"
    assert payload["extraction_score"] == 87
    assert payload["technical_score"] == 60
    assert payload["risk_level"] == "moderate"
    assert payload["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Données de surface insuffisantes pour un scoring technique complet.",
    ]
    UUID(payload["audit_id"])
    assert session.status == "AUDITED"
    assert session.committed is True


def test_audit_uses_surface_deviation_to_score_risk():
    session = FakeWorkflowSession(
        status="VALIDATED",
        audit_inputs={
            "extraction_score": 91,
            "declared_surface_m2": 100.0,
            "calculated_surface_m2": 103.0,
            "invalid_geometry": False,
        },
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["extraction_score"] == 91
    assert payload["technical_score"] == 74
    assert payload["risk_level"] == "moderate"
    assert payload["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Écart modéré entre surface déclarée et surface calculée.",
    ]


def test_audit_prioritizes_invalid_geometry_as_high_risk():
    session = FakeWorkflowSession(
        status="VALIDATED",
        audit_inputs={
            "extraction_score": 55,
            "declared_surface_m2": 100.0,
            "calculated_surface_m2": 100.0,
            "invalid_geometry": True,
        },
    )
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["technical_score"] == 35
    assert payload["risk_level"] == "high"
    assert payload["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Incohérence géométrique détectée sur la parcelle validée.",
    ]
