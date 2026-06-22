import hashlib
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crs import transform_coordinate_to_wgs84
from app.crs_detection import CRSDetectionResult, detect_crs
from app.surface_parser import parse_surface_to_m2
from app.workflow import mark_project_uploaded

BYTES_PER_MB = 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "application/pdf": ".pdf",
}
CHUNK_SIZE = 1024 * 1024


class DocumentUploadResponse(BaseModel):
    id: str
    project_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str
    storage_path: str


@dataclass(frozen=True)
class ExtractedSurveyPoint:
    label: str
    x: float
    y: float


@dataclass(frozen=True)
class ExtractedParcel:
    label: str
    declared_surface_m2: int | None
    points: list[ExtractedSurveyPoint]


# Tolérant aux sorties des modèles vision verbeux (gemma) : « B1 380 747 »,
# « B1: 380 747 », « - B1: X = 380.5, Y = 747.2 », « B3: X=420 Y=706 ». Les
# en-têtes (Borne X Y), surfaces et lignes de consigne ne matchent pas (x/y exigent
# des nombres). Décimale « . » ou « , » ; séparateur X/Y optionnel.
_COORDINATE_LINE_PATTERN = re.compile(
    r"^\s*[-*••\s]*"
    r"(?P<label>[A-Za-z]{0,4}\d+[A-Za-z0-9_-]*)\s*[:;.\-]?\s*"
    r"(?:[Xx]\s*[=:]?\s*)?(?P<x>\d{2,}(?:[.,]\d+)?)\s*[,;]?\s*"
    r"(?:[Yy]\s*[=:]?\s*)?(?P<y>\d{2,}(?:[.,]\d+)?)\s*$"
)
_PARCEL_HEADING_PATTERN = re.compile(r"\bparcelle\s+(?P<label>[A-Za-z0-9_-]+)", re.IGNORECASE)
_SURFACE_LINE_PATTERN = re.compile(r"\b(surface|superficie)\b", re.IGNORECASE)


def _parse_coordinate_line(line: str) -> ExtractedSurveyPoint | None:
    match = _COORDINATE_LINE_PATTERN.match(line.strip())
    if match is None:
        return None

    return ExtractedSurveyPoint(
        label=match.group("label"),
        x=float(match.group("x").replace(",", ".")),
        y=float(match.group("y").replace(",", ".")),
    )


def extract_parcels_from_ocr_text(ocr_text: str) -> list[ExtractedParcel]:
    parcels: list[ExtractedParcel] = []
    current_label: str | None = None
    current_surface: int | None = None
    current_points: list[ExtractedSurveyPoint] = []

    def flush() -> None:
        nonlocal current_label, current_surface, current_points
        if len(current_points) >= 3:
            label = current_label or f"Parcelle {len(parcels) + 1}"
            parcels.append(ExtractedParcel(label=label, declared_surface_m2=current_surface, points=current_points))
        current_label = None
        current_surface = None
        current_points = []

    for raw_line in ocr_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        heading = _PARCEL_HEADING_PATTERN.search(line)
        if heading:
            flush()
            current_label = f"Parcelle {heading.group('label')}"

        if _SURFACE_LINE_PATTERN.search(line):
            parsed_surface = parse_surface_to_m2(line)
            if parsed_surface is not None:
                current_surface = parsed_surface

        point = _parse_coordinate_line(line)
        if point is None:
            continue

        existing = next((p for p in current_points if p.label == point.label), None)
        if existing is not None:
            # Même label déjà présent dans la parcelle courante : si les coordonnées sont
            # ~identiques, c'est un ÉCHO (modèle vision verbeux qui re-liste les mêmes
            # bornes lors de sa relecture) → on ignore (sinon le polygone est corrompu par
            # des points dupliqués). Si les coordonnées diffèrent, c'est une nouvelle
            # parcelle qui réutilise les labels (B1, B2, …) → on flush.
            if abs(existing.x - point.x) <= 1.0 and abs(existing.y - point.y) <= 1.0:
                continue
            flush()
        if current_label is None:
            current_label = f"Parcelle {len(parcels) + 1}"
        current_points.append(point)

    flush()
    # Dédup : un modèle OCR verbeux (ex. gemma-4-31b) peut re-lister les mêmes bornes
    # (préambule de raisonnement + réponse finale) → parcelles dupliquées. On élimine
    # celles dont le jeu de points (label + coords arrondies) est identique à une
    # précédente — robuste même si un en-tête « Parcelle » sépare les échos.
    unique: list[ExtractedParcel] = []
    seen: set[tuple] = set()
    for parcel in parcels:
        signature = tuple(sorted((p.label, round(p.x, 1), round(p.y, 1)) for p in parcel.points))
        if signature in seen:
            continue
        seen.add(signature)
        unique.append(parcel)
    return unique


def store_extracted_parcels(
    *,
    project_id: str,
    document_id: str,
    ocr_text: str,
    db: Session,
) -> tuple[list[ExtractedParcel], CRSDetectionResult]:
    """Parse les parcelles du texte OCR, détecte le CRS et les persiste (idempotent).

    Retourne (parcelles parsées, détection CRS) pour enrichir la réponse OCR.
    On ne transforme vers WGS84 que si le CRS est réellement géoréférencé
    (EPSG:32631/4326) ; sinon (LOCAL_ONLY/UNKNOWN/NEEDS_GEOREFERENCING) on conserve
    les coordonnées source SANS géométrie WGS84 inventée.
    """
    parcels = extract_parcels_from_ocr_text(ocr_text)
    all_coordinates = [[point.x, point.y] for parcel in parcels for point in parcel.points]
    detection = detect_crs(text=ocr_text, coordinates=all_coordinates or None)
    if not parcels:
        return [], detection

    # Idempotence : si l'OCR de ce document a déjà posé une levée, ne pas réinsérer.
    existing = db.execute(
        text("SELECT id FROM levees WHERE source_document_id = :doc LIMIT 1"),
        {"doc": document_id},
    ).first()
    if existing is not None:
        return parcels, detection

    stored_crs = detection.epsg if detection.is_transformable else detection.status.value
    transformable = detection.is_transformable

    levee_id = str(uuid4())
    created_at = datetime.now(UTC)
    db.execute(
        text(
            """
            INSERT INTO levees (id, project_id, label, source_document_id, detected_crs, created_at)
            VALUES (:id, :project_id, :label, :source_document_id, :detected_crs, :created_at)
            """
        ),
        {
            "id": levee_id,
            "project_id": project_id,
            "label": "Levée extraite OCR",
            "source_document_id": document_id,
            "detected_crs": stored_crs,
            "created_at": created_at,
        },
    )

    for parcel in parcels:
        parcel_id = str(uuid4())
        db.execute(
            text(
                """
                INSERT INTO parcels (id, project_id, levee_id, label, declared_surface_m2, detected_crs, created_at)
                VALUES (:id, :project_id, :levee_id, :label, :declared_surface_m2, :detected_crs, :created_at)
                """
            ),
            {
                "id": parcel_id,
                "project_id": project_id,
                "levee_id": levee_id,
                "label": parcel.label,
                "declared_surface_m2": parcel.declared_surface_m2,
                "detected_crs": stored_crs,
                "created_at": created_at,
            },
        )
        # point_index = ordre du contour (= ordre de lecture de la table) : critique pour
        # reconstruire un polygone NON auto-intersecté à l'audit (sans lui, le tri par
        # label est alphabétique : B1, B10, B11, …, B2 → polygone en désordre → invalide).
        for point_index, point in enumerate(parcel.points):
            params = {
                "id": str(uuid4()),
                "parcel_id": parcel_id,
                "label": point.label,
                "point_index": point_index,
                "source_x": point.x,
                "source_y": point.y,
                "confidence": None,
                "created_at": created_at,
            }
            if transformable:
                longitude, latitude = transform_coordinate_to_wgs84(point.x, point.y, stored_crs)
                params["longitude"] = longitude
                params["latitude"] = latitude
                geom_sql = "ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)"
            else:
                # CRS non géoréférencé : pas de géométrie WGS84 (coordonnées source conservées).
                geom_sql = "NULL"
            db.execute(
                text(
                    f"""
                    INSERT INTO survey_points
                        (id, parcel_id, label, point_index, source_x, source_y, confidence, geom, created_at)
                    VALUES (:id, :parcel_id, :label, :point_index, :source_x, :source_y, :confidence,
                            {geom_sql}, :created_at)
                    """
                ),
                params,
            )

    return parcels, detection


def _safe_project_segment(project_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", project_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid project id")
    return project_id


def _safe_filename(filename: str | None) -> str:
    name = Path(filename or "document").name.strip()
    return name or "document"


def _extension_for_upload(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only JPG, PNG and PDF files are accepted",
        )
    return extension


def _max_upload_bytes() -> int:
    return settings.max_upload_mb * BYTES_PER_MB


def _content_matches_mime(content_type: str, first_chunk: bytes) -> bool:
    if content_type == "image/jpeg":
        return first_chunk.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return first_chunk.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "application/pdf":
        return first_chunk.startswith(b"%PDF-")
    return False



def _ensure_project_exists(project_id: str, db: Session) -> None:
    project = db.execute(text("SELECT id FROM projects WHERE id = :project_id"), {"project_id": project_id}).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _store_upload(project_id: str, file: UploadFile) -> tuple[str, int, str]:
    project_segment = _safe_project_segment(project_id)
    extension = _extension_for_upload(file)
    content_type = (file.content_type or "").lower()
    storage_dir = Path(settings.local_storage_path) / project_segment
    storage_dir.mkdir(parents=True, exist_ok=True)

    document_id = str(uuid4())
    final_path = storage_dir / f"{document_id}{extension}"
    temporary_path = storage_dir / f".{document_id}.uploading"

    digest = hashlib.sha256()
    size = 0
    checked_signature = False

    try:
        with temporary_path.open("wb") as output:
            while True:
                chunk = file.file.read(CHUNK_SIZE)
                if not chunk:
                    break

                if not checked_signature:
                    checked_signature = True
                    if not _content_matches_mime(content_type, chunk):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="File content does not match the declared MIME type",
                        )

                size += len(chunk)
                if size > _max_upload_bytes():
                    # 413 en littéral : la constante starlette a été renommée selon les
                    # versions (HTTP_413_CONTENT_TOO_LARGE vs _REQUEST_ENTITY_TOO_LARGE) —
                    # l'entier est insensible à la version installée.
                    raise HTTPException(
                        status_code=413,
                        detail=f"File exceeds the {settings.max_upload_mb} MB limit",
                    )

                digest.update(chunk)
                output.write(chunk)

        if not checked_signature:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

        shutil.move(str(temporary_path), final_path)
        return str(final_path), size, digest.hexdigest()
    except Exception:
        temporary_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def create_document_from_upload(project_id: str, file: UploadFile, db: Session) -> DocumentUploadResponse:
    _ensure_project_exists(project_id, db)
    filename = _safe_filename(file.filename)
    content_type = (file.content_type or "").lower()
    storage_path, size, sha256 = _store_upload(project_id, file)
    document_id = Path(storage_path).stem

    try:
        db.execute(
            text(
                """
                INSERT INTO documents (id, project_id, filename, content_type, size_bytes, sha256, storage_path, created_at)
                VALUES (:id, :project_id, :filename, :content_type, :size_bytes, :sha256, :storage_path, :created_at)
                """
            ),
            {
                "id": document_id,
                "project_id": project_id,
                "filename": filename,
                "content_type": content_type,
                "size_bytes": size,
                "sha256": sha256,
                "storage_path": storage_path,
                "created_at": datetime.now(UTC),
            },
        )
        # P0.3 : l'upload STOCKE uniquement le fichier (aucun OCR ici). L'extraction
        # est déclenchée explicitement via POST /documents/{id}/ocr. Le projet reste
        # à l'état UPLOADED tant que l'OCR n'a pas été lancé.
        mark_project_uploaded(project_id, db)
    except Exception:
        db.rollback()
        Path(storage_path).unlink(missing_ok=True)
        raise

    return DocumentUploadResponse(
        id=document_id,
        project_id=project_id,
        filename=filename,
        content_type=content_type,
        size_bytes=size,
        sha256=sha256,
        storage_path=storage_path,
    )
