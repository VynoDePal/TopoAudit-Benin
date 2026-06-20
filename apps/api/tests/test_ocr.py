from fastapi.testclient import TestClient

from types import SimpleNamespace

from app.database import get_db
from app.main import app
from app.ocr import MOCK_OCR_TEXT, ocr_rate_limiter


class FakeResult:
    def __init__(self, row: dict[str, str] | None) -> None:
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class FakeSession:
    def __init__(self, project: SimpleNamespace | None, document: SimpleNamespace | None) -> None:
        self.project = project
        self.document = document

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM projects" in sql:
            if self.project and self.project.id == params["project_id"]:
                return FakeResult({"id": self.project.id})
            return FakeResult(None)
        if "FROM documents" in sql:
            if self.document and self.document.id == params["document_id"]:
                return FakeResult(vars(self.document))
            return FakeResult(None)
        return FakeResult(None)


def override_db(project: SimpleNamespace | None, document: SimpleNamespace | None):
    def _override():
        yield FakeSession(project, document)

    return _override


def setup_function():
    ocr_rate_limiter.reset()
    app.dependency_overrides.clear()


def teardown_function():
    ocr_rate_limiter.reset()
    app.dependency_overrides.clear()


def test_ocr_returns_mock_text_when_azure_key_is_missing():
    project = SimpleNamespace(id="project-1", name="Demo")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path="/tmp/plan.png",
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert response.status_code == 200
    assert response.json() == {
        "provider": "mock",
        "text": MOCK_OCR_TEXT,
        "document_id": "document-1",
        "project_id": "project-1",
    }


def test_ocr_rejects_document_from_another_project():
    project = SimpleNamespace(id="project-1", name="Demo")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-2",
        filename="plan.png",
        content_type="image/png",
        storage_path="/tmp/plan.png",
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert response.status_code == 403


def test_ocr_rejects_missing_project_before_processing_document():
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path="/tmp/plan.png",
    )
    app.dependency_overrides[get_db] = override_db(None, document)
    client = TestClient(app)

    response = client.post("/api/projects/missing/documents/document-1/ocr")

    assert response.status_code == 404


def test_ocr_rate_limit_is_enforced(monkeypatch):
    monkeypatch.setattr("app.ocr.settings.ocr_rate_limit_per_minute", 1)
    project = SimpleNamespace(id="project-1", name="Demo")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path="/tmp/plan.png",
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    client = TestClient(app)

    assert client.post("/api/projects/project-1/documents/document-1/ocr").status_code == 200
    response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert response.status_code == 429
