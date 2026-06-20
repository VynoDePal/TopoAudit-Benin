from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

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
        self.committed = False

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM projects" in sql:
            if self.project and self.project.id == params["project_id"]:
                return FakeResult({"id": self.project.id, "status": self.project.status})
            return FakeResult(None)
        if "FROM documents" in sql:
            if self.document and self.document.id == params["document_id"]:
                return FakeResult(vars(self.document))
            return FakeResult(None)
        if "UPDATE projects SET status" in sql and self.project:
            self.project.status = params["status"]
            return FakeResult(None)
        return FakeResult(None)

    def commit(self):
        self.committed = True


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


class FakeGeminiResponse:
    def __init__(self, payload: dict | None = None, status_error: Exception | None = None) -> None:
        self.payload = payload or {}
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class FakeGeminiClient:
    last_request = None
    response = FakeGeminiResponse(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Surface déclarée: 05a 49ca\nP1 403825.84 707630.38\nP2 403836.57 707626.36"
                            }
                        ]
                    }
                }
            ]
        }
    )

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def post(self, url: str, headers: dict[str, str], json: dict):
        FakeGeminiClient.last_request = {"url": url, "headers": headers, "json": json, "timeout": self.timeout}
        return FakeGeminiClient.response


def test_ocr_returns_mock_text_when_azure_key_is_missing():
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
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
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
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


def test_ocr_uses_gemini_provider_for_utm_coordinates_and_surface(monkeypatch, tmp_path):
    document_path = tmp_path / "plan.png"
    document_path.write_bytes(b"fake image bytes")
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path=str(document_path),
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    monkeypatch.setattr("app.ocr.settings.ocr_provider", "gemini")
    monkeypatch.setattr("app.ocr.settings.gemini_api_key", "test-gemini-key")
    monkeypatch.setattr("app.ocr.httpx.Client", FakeGeminiClient)
    FakeGeminiClient.last_request = None
    FakeGeminiClient.response = FakeGeminiResponse(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": "Surface déclarée: 05a 49ca\nP1 403825.84 707630.38\nP2 403836.57 707626.36"
                            }
                        ]
                    }
                }
            ]
        }
    )
    client = TestClient(app)

    response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "gemini"
    assert "Surface déclarée: 05a 49ca" in payload["text"]
    assert "403825.84 707630.38" in payload["text"]
    assert FakeGeminiClient.last_request is not None
    assert FakeGeminiClient.last_request["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert FakeGeminiClient.last_request["headers"] == {"x-goog-api-key": "test-gemini-key"}
    parts = FakeGeminiClient.last_request["json"]["contents"][0]["parts"]
    assert "UTM zone 31N" in parts[0]["text"]
    assert parts[1]["inline_data"]["mime_type"] == "image/png"


def test_ocr_falls_back_to_mock_when_gemini_key_is_missing(monkeypatch):
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path="/tmp/plan.png",
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    monkeypatch.setattr("app.ocr.settings.ocr_provider", "gemini")
    monkeypatch.setattr("app.ocr.settings.gemini_api_key", "")
    client = TestClient(app)

    response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert response.status_code == 200
    assert response.json()["provider"] == "mock"
    assert response.json()["text"] == MOCK_OCR_TEXT


def test_ocr_maps_gemini_http_errors_to_bad_gateway(monkeypatch, tmp_path):
    document_path = tmp_path / "plan.png"
    document_path.write_bytes(b"fake image bytes")
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
    document = SimpleNamespace(
        id="document-1",
        project_id="project-1",
        filename="plan.png",
        content_type="image/png",
        storage_path=str(document_path),
    )
    request = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    response = httpx.Response(500, request=request)
    FakeGeminiClient.response = FakeGeminiResponse(
        status_error=httpx.HTTPStatusError("boom", request=request, response=response)
    )
    app.dependency_overrides[get_db] = override_db(project, document)
    monkeypatch.setattr("app.ocr.settings.ocr_provider", "gemini")
    monkeypatch.setattr("app.ocr.settings.gemini_api_key", "test-gemini-key")
    monkeypatch.setattr("app.ocr.httpx.Client", FakeGeminiClient)
    client = TestClient(app)

    api_response = client.post("/api/projects/project-1/documents/document-1/ocr")

    assert api_response.status_code == 502
    assert api_response.json()["detail"] == "Gemini OCR request failed"


def test_ocr_rate_limit_is_enforced(monkeypatch):
    monkeypatch.setattr("app.ocr.settings.ocr_rate_limit_per_minute", 1)
    project = SimpleNamespace(id="project-1", name="Demo", status="UPLOADED")
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
