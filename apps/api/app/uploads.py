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
    # Confiance OCR MACHINE par borne (ex. agrégat des word_confidence_scores Mistral) :
    # None si non fournie ou non associable (jamais inventée). Distincte de human_validated.
    confidence: float | None = None


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
# Tableau Markdown (Mistral OCR) : `| B1 | 402119.76 | 725732.25 |`, `| B.1 | ... |`.
# Un nombre de coordonnée = au moins 2 chiffres, décimale . ou , optionnelle.
_MD_NUMBER_RE = re.compile(r"^-?\d{2,}(?:[.,]\d+)?$")


def _parse_simple_tokens(line: str) -> tuple[str, str, str] | None:
    """Ligne simple `LABEL X Y` (tolérante aux sorties vision verbeux). Renvoie les tokens BRUTS."""
    match = _COORDINATE_LINE_PATTERN.match(line.strip())
    if match is None:
        return None
    return match.group("label"), match.group("x"), match.group("y")


def _parse_markdown_tokens(line: str) -> tuple[str, str, str] | None:
    """Ligne de tableau Markdown `| Borne | X | Y |`. Renvoie les tokens BRUTS, ou None pour
    une ligne d'en-tête (X/Y non numériques) ou un séparateur `|---|---|`."""
    stripped = line.strip()
    if "|" not in stripped:
        return None
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    cells = [cell for cell in cells if cell != ""]
    if len(cells) < 3:
        return None
    # Séparateur Markdown (`---`, `:---:`) : aucune donnée.
    if all(set(cell) <= set("-:= ") for cell in cells):
        return None
    label = cells[0]
    numbers = [cell for cell in cells[1:] if _MD_NUMBER_RE.match(cell)]
    if len(numbers) < 2:
        # En-tête (Borne | X | Y) : X/Y non numériques → ignoré, ne casse pas le parser.
        return None
    if not re.search(r"\d", label):
        # Libellé sans chiffre (ex. en-tête « Borne ») → pas une vraie borne.
        return None
    return label, numbers[0], numbers[1]


def _parse_point_tokens(line: str) -> tuple[str, str, str] | None:
    """Tokens bruts d'une borne : ligne simple d'abord, puis tableau Markdown."""
    return _parse_simple_tokens(line) or _parse_markdown_tokens(line)


# En-tête de tableau Markdown : noms de colonnes reconnus (insensible casse/ponctuation).
_HEADER_LABEL_NAMES = {"borne", "bornes", "bnes", "point", "points", "label", "sommet", "pt"}
_HEADER_X_NAMES = {"x", "xest", "xeast", "easting", "est", "east"}
_HEADER_Y_NAMES = {"y", "ynord", "ynorth", "northing", "nord", "north"}


def _normalize_header_cell(cell: str) -> str:
    return re.sub(r"[^a-z0-9]", "", cell.lower())


def _split_markdown_cells(line: str) -> list[str]:
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return [cell for cell in cells if cell != ""]


def _detect_markdown_header(cells: list[str]) -> dict[str, int] | None:
    """Mappe un en-tête `| Borne | X | Y |` (dans N'IMPORTE quel ordre) → indices de colonnes.

    Détecte X et Y par nom (variantes : X(EST)/Easting, Y(NORD)/Northing…) ; le libellé par
    nom, sinon la première colonne restante. None si X ou Y introuvable (pas un en-tête)."""
    label_i = x_i = y_i = None
    for index, cell in enumerate(cells):
        norm = _normalize_header_cell(cell)
        if x_i is None and norm in _HEADER_X_NAMES:
            x_i = index
        elif y_i is None and norm in _HEADER_Y_NAMES:
            y_i = index
        elif label_i is None and norm in _HEADER_LABEL_NAMES:
            label_i = index
    if x_i is None or y_i is None:
        return None
    if label_i is None:
        remaining = [i for i in range(len(cells)) if i not in (x_i, y_i)]
        if not remaining:
            return None
        label_i = remaining[0]
    return {"label": label_i, "x": x_i, "y": y_i}


def _parse_markdown_row_with_header(cells: list[str], header: dict[str, int]) -> tuple[str, str, str] | None:
    """Données d'une ligne Markdown via le mapping d'en-tête (colonnes réordonnées)."""
    if max(header.values()) >= len(cells):
        return None
    x_raw, y_raw = cells[header["x"]], cells[header["y"]]
    if not _MD_NUMBER_RE.match(x_raw) or not _MD_NUMBER_RE.match(y_raw):
        return None  # ligne non-données (séparateur, ré-en-tête, total…)
    return cells[header["label"]], x_raw, y_raw


def _parse_line_with_state(
    line: str, md_header: dict[str, int] | None
) -> tuple[tuple[str, str, str] | None, dict[str, int] | None]:
    """Parse une ligne en tenant compte d'un éventuel en-tête Markdown mémorisé.

    Retourne (tokens, md_header) — md_header est mis à jour si un en-tête est rencontré."""
    stripped = line.strip()
    if "|" in stripped:
        cells = _split_markdown_cells(stripped)
        if cells and all(set(cell) <= set("-:= ") for cell in cells):
            return None, md_header  # séparateur Markdown
        if len(cells) >= 3:
            header = _detect_markdown_header(cells)
            if header is not None:
                return None, header  # en-tête : mémorise l'ordre, pas de données
        if md_header is not None:
            return _parse_markdown_row_with_header(cells, md_header), md_header
        return _parse_markdown_tokens(line), md_header  # pas d'en-tête connu → positionnel
    return _parse_simple_tokens(line), md_header


def _normalize_conf_token(value: object) -> str:
    """Normalise un token pour l'appariement des confiances OCR (robuste aux variantes).

    - retire pipes/ponctuation périphérique (garde . et - internes) ;
    - virgule décimale → point (« 402119,76 » → « 402119.76 ») ;
    - supprime les espaces internes des nombres (« 402 119,76 » → « 402119.76 ») ;
    - minuscule. Permet de matcher « B1, » / « (402119,76) » / « 402 119.76 »."""
    text = re.sub(r"\s+", "", str(value).lower())  # minuscule + espaces internes (nombres scindés)
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)  # virgule décimale INTERNE → point
    text = re.sub(r"^[^\w]+|[^\w]+$", "", text)  # ponctuation/pipe périphérique (garde . interne)
    return text


def _build_confidence_lookup(word_confidences: list[dict] | None) -> dict[str, float]:
    """Index {token normalisé → confiance} depuis les word_confidence_scores (ex. Mistral)."""
    lookup: dict[str, float] = {}
    for entry in word_confidences or []:
        if not isinstance(entry, dict):
            continue
        text_value = entry.get("text")
        score = entry.get("confidence")
        if isinstance(text_value, str) and isinstance(score, (int, float)) and not isinstance(score, bool):
            key = _normalize_conf_token(text_value)
            if key and key not in lookup:
                lookup[key] = float(score)
    return lookup


def _confidence_for_tokens(tokens: tuple[str, str, str], lookup: dict[str, float]) -> float | None:
    """Confiance OCR d'une borne = MOYENNE des confiances (normalisées) de label + X + Y.

    Stratégie prudente : si UN seul token n'a pas de score associable, on renvoie None
    (jamais de confiance inventée). Distincte de la validation humaine."""
    if not lookup:
        return None
    scores: list[float] = []
    for token in tokens:
        score = lookup.get(_normalize_conf_token(token))
        if score is None:
            return None  # association impossible → ne jamais inventer
        scores.append(score)
    return sum(scores) / len(scores)


def _parse_coordinate_line(line: str) -> ExtractedSurveyPoint | None:
    """Compat : conserve l'API d'origine (sans confiance)."""
    tokens = _parse_point_tokens(line)
    if tokens is None:
        return None
    label, x_raw, y_raw = tokens
    return ExtractedSurveyPoint(label=label, x=float(x_raw.replace(",", ".")), y=float(y_raw.replace(",", ".")))


def extract_parcels_from_ocr_text(
    ocr_text: str, word_confidences: list[dict] | None = None
) -> list[ExtractedParcel]:
    lookup = _build_confidence_lookup(word_confidences)
    parcels: list[ExtractedParcel] = []
    current_label: str | None = None
    current_surface: int | None = None
    current_points: list[ExtractedSurveyPoint] = []
    # Ordre de colonnes du dernier en-tête Markdown rencontré (colonnes réordonnées).
    md_header: dict[str, int] | None = None

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

        tokens, md_header = _parse_line_with_state(line, md_header)
        if tokens is None:
            continue
        point = ExtractedSurveyPoint(
            label=tokens[0],
            x=float(tokens[1].replace(",", ".")),
            y=float(tokens[2].replace(",", ".")),
            confidence=_confidence_for_tokens(tokens, lookup),
        )

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
    word_confidences: list[dict] | None = None,
) -> tuple[list[ExtractedParcel], CRSDetectionResult]:
    """Parse les parcelles du texte OCR, détecte le CRS et les persiste (idempotent).

    Retourne (parcelles parsées, détection CRS) pour enrichir la réponse OCR.
    On ne transforme vers WGS84 que si le CRS est réellement géoréférencé
    (EPSG:32631/4326) ; sinon (LOCAL_ONLY/UNKNOWN/NEEDS_GEOREFERENCING) on conserve
    les coordonnées source SANS géométrie WGS84 inventée.
    """
    parcels = extract_parcels_from_ocr_text(ocr_text, word_confidences=word_confidences)
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
                # Confiance OCR MACHINE par borne (Mistral word scores agrégés) ou None si le
                # provider n'en fournit pas / non associable (jamais inventée, jamais 0) ;
                # validation humaine = False à l'extraction (indicateur séparé).
                "confidence": point.confidence,
                "human_validated": False,
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
                        (id, parcel_id, label, point_index, source_x, source_y, confidence, human_validated, geom, created_at)
                    VALUES (:id, :parcel_id, :label, :point_index, :source_x, :source_y, :confidence, :human_validated,
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
