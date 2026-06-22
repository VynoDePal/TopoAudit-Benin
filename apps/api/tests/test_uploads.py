import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.sql.elements import TextClause

from app.config import settings
from app.database import get_db
from app.main import app


class FakeResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeUploadSession:
    def __init__(self, *, project_exists: bool = True) -> None:
        self.project_exists = project_exists
        self.project_status: str | None = None
        self.inserted: dict[str, object] | None = None
        self.levees: list[dict[str, object]] = []
        self.parcels: list[dict[str, object]] = []
        self.survey_points: list[dict[str, object]] = []
        self.committed = False
        self.rolled_back = False

    def execute(self, statement: TextClause, params: dict[str, object]):
        sql = str(statement)
        if "FROM projects" in sql:
            return FakeResult({"id": params["project_id"], "status": self.project_status} if self.project_exists else None)
        if "INSERT INTO documents" in sql:
            self.inserted = dict(params)
            return FakeResult(None)
        if "FROM documents" in sql:
            return FakeResult(self.inserted)
        if "INSERT INTO levees" in sql:
            self.levees.append(dict(params))
            return FakeResult(None)
        if "INSERT INTO parcels" in sql:
            self.parcels.append(dict(params))
            return FakeResult(None)
        if "INSERT INTO survey_points" in sql:
            self.survey_points.append(dict(params))
            return FakeResult(None)
        if "UPDATE projects SET status" in sql:
            self.project_status = str(params["status"])
            return FakeResult(None)
        return FakeResult(None)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def override_db(session: FakeUploadSession):
    def _override():
        yield session

    return _override


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def test_upload_document_persists_file_and_database_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)
    content = b"\x89PNG\r\n\x1a\nnot a real png but has a valid signature"

    response = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("../plan.png", content, "image/png")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["project_id"] == "project-1"
    assert payload["filename"] == "plan.png"
    assert payload["content_type"] == "image/png"
    assert payload["size_bytes"] == len(content)
    assert payload["sha256"] == hashlib.sha256(content).hexdigest()
    assert payload["storage_path"].startswith(str(tmp_path / "project-1"))
    assert Path(payload["storage_path"]).read_bytes() == content

    assert session.inserted is not None
    created_at = session.inserted.pop("created_at")
    assert created_at is not None
    assert session.inserted == {
        "id": payload["id"],
        "project_id": "project-1",
        "filename": "plan.png",
        "content_type": "image/png",
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "storage_path": payload["storage_path"],
    }
    # P0.3 : l'upload STOCKE seulement le fichier → état UPLOADED ; aucune parcelle
    # n'est extraite ici (l'OCR est déclenché explicitement via /ocr).
    assert session.project_status == "UPLOADED"
    assert session.levees == []
    assert session.parcels == []
    assert session.committed is True
    assert session.rolled_back is False


def test_ocr_extracts_multiple_coordinate_groups_into_distinct_parcels(tmp_path, monkeypatch):
    # P0.3 : l'extraction multi-parcelles se fait au stade OCR (pas à l'upload).
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    monkeypatch.setattr(
        "app.main.extract_text_from_document",
        lambda storage_path, content_type: (
            """
            Plan multi-parcelles
            Parcelle A
            Surface déclarée: 05a 49ca
            P1 403825.84 707630.38
            P2 403836.57 707626.36
            P3 403840.12 707641.10
            P4 403829.20 707645.42

            Parcelle B
            Surface déclarée: 02a 10ca
            P1 403850.00 707650.00
            P2 403860.00 707650.00
            P3 403860.00 707660.00
            P4 403850.00 707660.00
            """.strip(),
            "mock",
        ),
    )
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)
    content = b"%PDF-1.4 multi parcel plan"

    upload = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("plan.pdf", content, "application/pdf")},
    )
    assert upload.status_code == 201
    document_id = upload.json()["id"]
    # L'upload ne pose AUCUNE parcelle.
    assert session.levees == []
    assert session.parcels == []

    ocr = client.post(f"/api/projects/project-1/documents/{document_id}/ocr")
    assert ocr.status_code == 200
    body = ocr.json()
    assert [p["label"] for p in body["parsed_parcels"]] == ["Parcelle A", "Parcelle B"]
    assert body["detected_crs"] == "EPSG_32631"

    assert len(session.levees) == 1
    assert session.levees[0]["project_id"] == "project-1"
    assert session.levees[0]["source_document_id"] == document_id
    assert [parcel["label"] for parcel in session.parcels] == ["Parcelle A", "Parcelle B"]
    assert [parcel["declared_surface_m2"] for parcel in session.parcels] == [549, 210]
    assert {parcel["levee_id"] for parcel in session.parcels} == {session.levees[0]["id"]}
    assert len(session.survey_points) == 8
    assert {point["parcel_id"] for point in session.survey_points[:4]} == {session.parcels[0]["id"]}
    assert {point["parcel_id"] for point in session.survey_points[4:]} == {session.parcels[1]["id"]}
    assert session.project_status == "OCR_EXTRACTED"


def test_upload_rejects_unsupported_mime_without_database_insert(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("plan.txt", b"text", "text/plain")},
    )

    assert response.status_code == 415
    assert session.inserted is None
    assert not any(tmp_path.iterdir())


def test_upload_rejects_declared_mime_when_content_signature_does_not_match(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("plan.png", b"not a png", "image/png")},
    )

    assert response.status_code == 415
    assert session.inserted is None
    assert list((tmp_path / "project-1").glob("*")) == []


def test_upload_rejects_files_larger_than_max_upload_mb(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)
    content = b"%PDF-" + (b"x" * (1024 * 1024))

    response = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("plan.pdf", content, "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "File exceeds the 1 MB limit"
    assert session.inserted is None
    assert list((tmp_path / "project-1").glob("*")) == []


def test_upload_rejects_missing_project_before_writing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    session = FakeUploadSession(project_exists=False)
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post(
        "/api/projects/missing/documents",
        files={"file": ("plan.jpg", b"jpg", "image/jpeg")},
    )

    assert response.status_code == 404
    assert session.inserted is None
    assert not tmp_path.exists() or not any(tmp_path.iterdir())
