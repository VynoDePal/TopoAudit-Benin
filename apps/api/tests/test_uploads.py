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
        self.committed = False
        self.rolled_back = False

    def execute(self, statement: TextClause, params: dict[str, object]):
        sql = str(statement)
        if "FROM projects" in sql:
            return FakeResult({"id": params["project_id"], "status": self.project_status} if self.project_exists else None)
        if "INSERT INTO documents" in sql:
            self.inserted = dict(params)
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
    assert session.project_status == "UPLOADED"
    assert session.committed is True
    assert session.rolled_back is False


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


def test_upload_rejects_files_larger_than_25_mb(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "local_storage_path", str(tmp_path))
    session = FakeUploadSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)
    content = b"%PDF-" + (b"x" * (25 * 1024 * 1024 - 4))

    response = client.post(
        "/api/projects/project-1/documents",
        files={"file": ("plan.pdf", content, "application/pdf")},
    )

    assert response.status_code == 413
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
