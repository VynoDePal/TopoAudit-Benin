import hashlib
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.sql.elements import TextClause

from app.config import settings
from app.database import get_db
from app.main import app
from app.ocr import OcrProviderResult
from app.uploads import extract_parcels_from_ocr_text


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
        "app.main.extract_ocr_from_document",
        lambda storage_path, content_type, provider_name=None: OcrProviderResult(
            text="""
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
            provider="mock",
            model=None,
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


# --- Parser : tableaux Markdown (Mistral OCR) + confiance par mot -----------------------


def test_extract_parcels_from_markdown_table():
    # Tableau Markdown Mistral : en-tête + séparateur ignorés ; labels « B.2 » supportés.
    ocr_text = (
        "Parcelle A\n"
        "Surface déclarée: 05a 49ca\n"
        "| Borne | X | Y |\n"
        "|---|---|---|\n"
        "| B1 | 402119.76 | 725732.25 |\n"
        "| B.2 | 402130.00 | 725740.00 |\n"
        "| B3 | 402140.00 | 725730.00 |\n"
    )
    parcels = extract_parcels_from_ocr_text(ocr_text)
    assert len(parcels) == 1
    assert [p.label for p in parcels[0].points] == ["B1", "B.2", "B3"]
    assert parcels[0].points[0].x == 402119.76
    assert parcels[0].points[0].y == 725732.25
    # Sans word scores → confiance OCR null (jamais inventée).
    assert all(p.confidence is None for p in parcels[0].points)


def test_markdown_parser_does_not_break_simple_lines():
    # Le support Markdown ne casse pas le parser des lignes simples existant.
    ocr_text = "Parcelle A\nP1 403825.84 707630.38\nP2 403836.57 707626.36\nP3 403840.12 707641.10"
    parcels = extract_parcels_from_ocr_text(ocr_text)
    assert len(parcels) == 1
    assert [p.label for p in parcels[0].points] == ["P1", "P2", "P3"]


def test_markdown_confidence_from_word_scores_is_numeric_or_null():
    ocr_text = (
        "| Borne | X | Y |\n"
        "| B1 | 402119.76 | 725732.25 |\n"
        "| B2 | 402130.00 | 725740.00 |\n"
        "| B3 | 402140.00 | 725730.00 |\n"
    )
    word_confidences = [
        {"text": "B1", "confidence": 0.9},
        {"text": "402119.76", "confidence": 0.8},
        {"text": "725732.25", "confidence": 0.7},
        # B2 partiel (X/Y manquants) → association incomplète → confiance None.
        {"text": "B2", "confidence": 0.9},
    ]
    parcels = extract_parcels_from_ocr_text(ocr_text, word_confidences=word_confidences)
    points = parcels[0].points
    # B1 entièrement associé → moyenne des 3 scores (0.8), bornée [0,1].
    assert points[0].confidence is not None
    assert abs(points[0].confidence - 0.8) < 1e-9
    assert 0.0 <= points[0].confidence <= 1.0
    # B2 incomplet → jamais inventé.
    assert points[1].confidence is None


# --- Parser : colonnes Markdown réordonnées (détection d'en-tête) -----------------------


def test_markdown_header_reordered_y_before_x():
    # En-tête `| Borne | Y | X |` : X/Y respectés malgré l'ordre inversé.
    ocr_text = (
        "| Borne | Y | X |\n"
        "| B1 | 725732.25 | 402119.76 |\n"
        "| B2 | 725740.00 | 402130.00 |\n"
        "| B3 | 725730.00 | 402140.00 |\n"
    )
    pts = extract_parcels_from_ocr_text(ocr_text)[0].points
    assert [p.label for p in pts] == ["B1", "B2", "B3"]
    assert pts[0].x == 402119.76 and pts[0].y == 725732.25


def test_markdown_header_label_last_with_easting_northing_variants():
    # `| Easting | Northing | Point |` : libellé en dernière colonne + variantes de noms.
    ocr_text = (
        "| Easting | Northing | Point |\n"
        "| 402119.76 | 725732.25 | B1 |\n"
        "| 402130.00 | 725740.00 | B2 |\n"
        "| 402140.00 | 725730.00 | B3 |\n"
    )
    pts = extract_parcels_from_ocr_text(ocr_text)[0].points
    assert [p.label for p in pts] == ["B1", "B2", "B3"]
    assert pts[0].x == 402119.76 and pts[0].y == 725732.25


def test_markdown_header_xest_ynord_parenthesis_variants():
    # `X(EST)` / `Y(NORD)` + libellé « Bornes ».
    ocr_text = (
        "| Bornes | X(EST) | Y(NORD) |\n"
        "|---|---|---|\n"
        "| B1 | 402119.76 | 725732.25 |\n"
        "| B2 | 402130.00 | 725740.00 |\n"
        "| B3 | 402140.00 | 725730.00 |\n"
    )
    pts = extract_parcels_from_ocr_text(ocr_text)[0].points
    assert [p.label for p in pts] == ["B1", "B2", "B3"]
    assert pts[0].x == 402119.76 and pts[0].y == 725732.25


def test_markdown_without_header_keeps_positional_strategy():
    # Sans en-tête : 1re cellule = label, 2 premiers nombres = X/Y (stratégie inchangée).
    ocr_text = "| B1 | 402119.76 | 725732.25 |\n| B2 | 402130.00 | 725740.00 |\n| B3 | 402140.00 | 725730.00 |\n"
    pts = extract_parcels_from_ocr_text(ocr_text)[0].points
    assert [p.label for p in pts] == ["B1", "B2", "B3"]
    assert pts[0].x == 402119.76 and pts[0].y == 725732.25


def test_confidence_matching_normalizes_comma_and_punctuation():
    ocr_text = (
        "| Borne | X | Y |\n"
        "| B1 | 402119.76 | 725732.25 |\n"
        "| B2 | 402130.00 | 725740.00 |\n"
        "| B3 | 402140.00 | 725730.00 |\n"
    )
    # Scores avec virgule décimale + ponctuation périphérique : doivent matcher les tokens.
    word_confidences = [
        {"text": "B1,", "confidence": 0.9},  # ponctuation
        {"text": "402119,76", "confidence": 0.8},  # virgule décimale
        {"text": "(725732,25)", "confidence": 0.7},  # ponctuation + virgule
        {"text": "B2", "confidence": 0.95},  # B2 incomplet → null
    ]
    pts = extract_parcels_from_ocr_text(ocr_text, word_confidences=word_confidences)[0].points
    assert pts[0].confidence is not None and abs(pts[0].confidence - 0.8) < 1e-9  # moy(0.9,0.8,0.7)
    assert pts[1].confidence is None  # association incomplète → jamais inventée
