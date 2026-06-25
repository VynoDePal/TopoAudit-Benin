from uuid import UUID

from fastapi.testclient import TestClient
from pyproj import Transformer

from app.database import get_db
from app.main import app

_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True)


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


class FakeWorkflowSession:
    def __init__(
        self,
        *,
        project_exists: bool = True,
        status: str | None = "UPLOADED",
        audit_inputs: dict[str, object] | None = None,
        parcel_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.project_exists = project_exists
        self.status = status
        self.audit_inputs = audit_inputs
        self.parcel_rows = parcel_rows or []
        self.committed = False

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM parcels p" in sql:
            return FakeResult(rows=self.parcel_rows)
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


def test_audit_without_evidence_requires_human_validation_no_default_score():
    session = FakeWorkflowSession(status="VALIDATED")
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["state"] == "AUDITED"
    # Aucune preuve d'extraction → pas de score inventé (jamais 87).
    assert payload["extraction_score"] is None
    assert payload["extraction_score_status"] == "needs_human_validation"
    assert payload["technical_score"] == 60
    assert payload["risk_level"] == "moderate"
    assert payload["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Données de surface insuffisantes pour un scoring technique complet de Parcelle en attente de validation.",
        "Score d'extraction indisponible : validation humaine des coordonnées requise.",
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
        "Écart modéré entre surface déclarée et surface calculée pour Parcelle validée.",
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
        "Incohérence géométrique détectée sur Parcelle validée.",
    ]


def test_audit_scores_each_extracted_parcel_independently_and_aggregates_worst_risk():
    first_parcel_points = [
        ("P1", 403825.84, 707630.38),
        ("P2", 403836.57, 707626.36),
        ("P3", 403840.12, 707641.10),
        ("P4", 403829.20, 707645.42),
    ]
    second_parcel_points = [
        ("P1", 403850.0, 707650.0),
        ("P2", 403860.0, 707650.0),
        ("P3", 403860.0, 707660.0),
        ("P4", 403850.0, 707660.0),
    ]
    parcel_rows = [
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 176,
            "detected_crs": "EPSG:32631",
            "source_x": x,
            "source_y": y,
        }
        for _label, x, y in first_parcel_points
    ] + [
        {
            "parcel_id": "parcel-b",
            "label": "Parcelle B",
            "declared_surface_m2": 20,
            "detected_crs": "EPSG:32631",
            "source_x": x,
            "source_y": y,
        }
        for _label, x, y in second_parcel_points
    ]
    session = FakeWorkflowSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "high"
    assert payload["technical_score"] == 48
    assert [parcel["label"] for parcel in payload["parcels"]] == ["Parcelle A", "Parcelle B"]
    assert [parcel["risk_level"] for parcel in payload["parcels"]] == ["low", "high"]
    assert payload["parcels"][0]["declared_surface_m2"] == 176
    assert payload["parcels"][1]["declared_surface_m2"] == 20
    assert "Parcelle B" in payload["warnings"][1]


def test_audit_computes_extraction_score_from_extracted_data_quality():
    parcel_rows = [
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 176,
            "detected_crs": "EPSG:32631",
            "source_x": x,
            "source_y": y,
            "confidence": confidence,
        }
        for x, y, confidence in [
            (403825.84, 707630.38, 0.5),
            (403836.57, 707626.36, 0.5),
            (403840.12, 707641.10, 0.5),
            (403829.20, 707645.42, 0.5),
        ]
    ]
    session = FakeWorkflowSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["extraction_score"] == 85
    assert payload["parcels"][0]["extraction_score"] == 85


def test_human_validation_is_separate_and_never_becomes_extraction_score():
    # Bornes validées humainement MAIS aucune confiance OCR machine (None).
    parcel_rows = [
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 176,
            "detected_crs": "EPSG:32631",
            "source_x": x,
            "source_y": y,
            "confidence": None,
            "human_validated": True,
        }
        for x, y in [(403825.84, 707630.38), (403836.57, 707626.36), (403840.12, 707641.10), (403829.20, 707645.42)]
    ]
    session = FakeWorkflowSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    payload = client.post("/api/projects/project-1/audit").json()
    # La validation humaine ne devient JAMAIS le score d'extraction : sans confiance OCR
    # réelle, le score reste « à valider ».
    assert payload["extraction_score"] is None
    assert payload["extraction_score_status"] == "needs_human_validation"
    assert payload["parcels"][0]["extraction_score"] is None
    # Indicateur SÉPARÉ de validation humaine.
    assert payload["human_validated"] is True
    assert payload["parcels"][0]["human_validated"] is True


def test_audit_marks_parcel_without_enough_points_as_invalid_geometry():
    parcel_rows = [
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 176,
            "detected_crs": "EPSG:32631",
            "source_x": 403825.84,
            "source_y": 707630.38,
        },
        {
            "parcel_id": "parcel-a",
            "label": "Parcelle A",
            "declared_surface_m2": 176,
            "detected_crs": "EPSG:32631",
            "source_x": 403836.57,
            "source_y": 707626.36,
        },
    ]
    session = FakeWorkflowSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit")

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "high"
    assert payload["technical_score"] == 35
    assert len(payload["parcels"]) == 1
    parcel = payload["parcels"][0]
    assert parcel["parcel_id"] == "parcel-a"
    assert parcel["label"] == "Parcelle A"
    assert parcel["extraction_score"] is None
    assert parcel["extraction_score_status"] == "needs_human_validation"
    assert parcel["human_validated"] is False
    assert parcel["declared_surface_m2"] == 176.0
    assert parcel["calculated_surface_m2"] is None
    assert parcel["invalid_geometry"] is True
    assert parcel["technical_score"] == 35
    assert parcel["risk_level"] == "high"
    assert parcel["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Incohérence géométrique détectée sur Parcelle A.",
    ]
    # Contrôle territorial : 2 bornes (< 3) → géométrie invalide pour le contrôle.
    assert parcel["territory_status"] == "invalid_geometry"
    assert payload["warnings"] == [
        "Aucune comparaison cadastrale officielle effectuée.",
        "Incohérence géométrique détectée sur Parcelle A.",
        "Score d'extraction indisponible : validation humaine des coordonnées requise.",
    ]



def test_audit_penalizes_technical_score_when_outside_benin():
    # 8. Parcelle valide géométriquement mais géoréférencée HORS Bénin (Paris) →
    # technical_score plafonné, risque escaladé, warning territorial.
    paris = [(2.34, 48.85), (2.36, 48.85), (2.36, 48.87), (2.34, 48.87)]
    parcel_rows = [
        {
            "parcel_id": "parcel-paris",
            "label": "Parcelle hors Bénin",
            "declared_surface_m2": 500,
            "detected_crs": "EPSG:32631",
            "source_x": _TO_UTM.transform(lon, lat)[0],
            "source_y": _TO_UTM.transform(lon, lat)[1],
        }
        for lon, lat in paris
    ]
    session = FakeWorkflowSession(status="VALIDATED", parcel_rows=parcel_rows)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    payload = client.post("/api/projects/project-1/audit").json()
    parcel = payload["parcels"][0]
    assert parcel["territory_status"] == "outside_benin"
    assert parcel["technical_score"] <= 20
    assert "Le tracé géoréférencé tombe hors du territoire béninois." in parcel["warnings"]
    # Agrégat projet exposé.
    assert payload["territory_status"] == "outside_benin"
    assert payload["territory_risk_level"] == "critical"
    assert "Le tracé géoréférencé tombe hors du territoire béninois." in payload["territory_warnings"]
