from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader

from app.database import get_db
from app.main import app
from app.pdf_report import LEGAL_DISCLAIMER, generate_audit_report_pdf
from app.workflow import AuditResponse, ParcelAuditResult, ProjectWorkflowState


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


class FakeReportSession:
    def __init__(self) -> None:
        self.status = "VALIDATED"
        self.committed = False

    def execute(self, statement, params: dict[str, str]):
        sql = str(statement)
        if "FROM parcels p" in sql:
            return FakeResult(rows=[])
        if "FROM audit_inputs" in sql:
            return FakeResult(
                {
                    "extraction_score": 91,
                    "declared_surface_m2": 100.0,
                    "calculated_surface_m2": 103.0,
                    "invalid_geometry": False,
                }
            )
        if "FROM projects" in sql:
            return FakeResult({"id": params["project_id"], "status": self.status})
        if "UPDATE projects SET status" in sql:
            self.status = params["status"]
            return FakeResult(None)
        return FakeResult(None)

    def commit(self):
        self.committed = True


def override_db(session: FakeReportSession):
    def _override():
        yield session

    return _override


def setup_function():
    app.dependency_overrides.clear()


def teardown_function():
    app.dependency_overrides.clear()


def extract_pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() for page in reader.pages)


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def test_generate_audit_report_pdf_contains_scores_and_legal_disclaimer():
    audit = AuditResponse(
        project_id="project-1",
        state=ProjectWorkflowState.AUDITED,
        audit_id="audit-1",
        extraction_score=91,
        technical_score=74,
        risk_level="moderate",
        warnings=["Écart modéré entre surface déclarée et surface calculée."],
    )

    pdf_bytes = generate_audit_report_pdf(audit)
    text = extract_pdf_text(pdf_bytes)
    normalized_text = normalize_text(text)

    assert pdf_bytes.startswith(b"%PDF")
    assert "Score d'extraction" in text
    assert "91/100" in text
    assert "Score technique" in text
    assert "74/100" in text
    assert "Modéré" in text
    assert "ne constitue pas un avis juridique" in normalized_text
    assert LEGAL_DISCLAIMER[:40] in normalized_text


def test_project_audit_report_endpoint_returns_pdf_response():
    session = FakeReportSession()
    app.dependency_overrides[get_db] = override_db(session)
    client = TestClient(app)

    response = client.post("/api/projects/project-1/audit/report.pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="topoaudit-project-1-report.pdf"'
    assert response.content.startswith(b"%PDF")
    assert session.status == "AUDITED"
    assert session.committed is True
    text = extract_pdf_text(response.content)
    normalized_text = normalize_text(text)
    assert "91/100" in text
    assert "74/100" in text
    assert "ne constitue pas un avis juridique" in normalized_text
