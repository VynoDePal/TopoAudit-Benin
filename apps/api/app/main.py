import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crs import (
    GEOJSON_CRS,
    SUPPORTED_SOURCE_CRS,
    transform_coordinate_to_wgs84,
    transform_coordinates_to_wgs84,
)
from app.database import get_db, get_engine
from app.geometry_engine import PolygonValidationResult, validate_polygon
from app.auth import (
    AuthUser,
    authenticate_user,
    authorized_project_user,
    create_token,
    ensure_project_access,
    get_current_user,
    register_user,
)
from app.extraction_score import extraction_score_calculator
from app.models import Base, Project
from app.ocr import (
    OcrParsedParcel,
    OcrPoint,
    OcrResult,
    enforce_ocr_rate_limit,
    extract_text_from_document,
)
from app.pdf_report import generate_audit_report_pdf
from app.risk_scoring import SurfaceRiskScore, score_surface_deviation
from app.uploads import (
    DocumentUploadResponse,
    create_document_from_upload,
    store_extracted_parcels,
)
from app.workflow import (
    AuditResponse,
    ProjectValidationResponse,
    ProjectWorkflowResponse,
    _ensure_project_exists,
    create_project_audit,
    ensure_audit_inputs_table,
    get_project_state,
    mark_project_ocr_extracted,
    upsert_audit_inputs,
    validate_project_for_audit,
)


@asynccontextmanager
async def lifespan(_app: "FastAPI"):
    # Applique le schéma au DÉMARRAGE (pas de migration Alembic au runtime sinon la base
    # déployée reste vide → toutes les routes DB en 500). create_all couvre l'ORM ; la
    # table audit_inputs (SQL brut, hors ORM) est créée explicitement.
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    ensure_audit_inputs_table(engine)
    # Migrations idempotentes (bases créées avant P0.2/P1.1) :
    #  - geom nullable (point sans CRS géoréférencé) ;
    #  - colonne owner_id sur projects (propriété SaaS).
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE survey_points ALTER COLUMN geom DROP NOT NULL"))
        conn.execute(text("ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_id VARCHAR(36)"))
    # Log de démarrage : provider OCR + modèle actifs (le filtre anti-secret installé par
    # app.config garantit qu'aucune clé n'apparaît dans les logs).
    # logger "uvicorn.error" : visible dans la sortie de démarrage (le logger applicatif
    # par défaut hériterait du niveau WARNING et l'INFO serait masqué).
    logging.getLogger("uvicorn.error").info(
        "Démarrage TopoAudit | APP_ENV=%s | OCR_PROVIDER=%s | modèle vision=%s",
        settings.app_env,
        settings.ocr_provider,
        settings.gemini_model,
    )
    yield


app = FastAPI(
    title=settings.app_name,
    description="API prototype pour audit préliminaire de plans topographiques au Bénin.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CoordinateXY = Annotated[list[float], Field(min_length=2, max_length=2)]


class CoordinateTransformRequest(BaseModel):
    source_crs: SUPPORTED_SOURCE_CRS = Field(default="EPSG:32631", examples=["EPSG:32631"])
    coordinates: list[CoordinateXY] = Field(
        min_length=1,
        examples=[[[403825.84, 707630.38], [403836.57, 707626.36]]],
    )


class CoordinateTransformResponse(BaseModel):
    source_crs: str
    target_crs: str
    coordinates: list[list[float]]


class PolygonValidationRequest(BaseModel):
    source_crs: SUPPORTED_SOURCE_CRS = Field(default="EPSG:32631", examples=["EPSG:4326"])
    coordinates: list[CoordinateXY] = Field(
        min_length=3,
        examples=[[[2.13, 6.4], [2.14, 6.4], [2.14, 6.41], [2.13, 6.41]]],
    )


class SurfaceRiskRequest(BaseModel):
    declared_surface_m2: float = Field(gt=0, examples=[549])
    calculated_surface_m2: float = Field(ge=0, examples=[551])


class OcrRequest(BaseModel):
    project_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)


def _database_ready() -> bool:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/api/health", tags=["system"])
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "database": _database_ready(),
    }


@app.post("/api/crs/transform", response_model=CoordinateTransformResponse, tags=["crs"])
def transform_crs(payload: CoordinateTransformRequest) -> CoordinateTransformResponse:
    return CoordinateTransformResponse(
        source_crs=payload.source_crs,
        target_crs=GEOJSON_CRS,
        coordinates=transform_coordinates_to_wgs84(payload.coordinates, payload.source_crs),
    )


@app.post("/api/geometry/validate-polygon", response_model=PolygonValidationResult, tags=["geometry"])
def validate_polygon_geometry(payload: PolygonValidationRequest) -> PolygonValidationResult:
    return validate_polygon(payload.coordinates, payload.source_crs)


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Audit parcelle Cotonou"])


class ProjectCreateResponse(BaseModel):
    id: str
    name: str
    status: str | None


class AuthRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255, examples=["arpenteur@example.bj"])
    password: str = Field(min_length=8, max_length=128)


class AuthResponse(BaseModel):
    token: str
    user_id: str
    email: str


@app.post("/api/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, tags=["auth"])
def register(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = register_user(payload.email, payload.password, db)
    return AuthResponse(token=create_token(user_id=user.id, email=user.email), user_id=user.id, email=user.email)


@app.post("/api/auth/login", response_model=AuthResponse, tags=["auth"])
def login(payload: AuthRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate_user(payload.email, payload.password, db)
    return AuthResponse(token=create_token(user_id=user.id, email=user.email), user_id=user.id, email=user.email)


@app.post(
    "/api/projects",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(
    payload: ProjectCreateRequest,
    db: Session = Depends(get_db),
    current_user: AuthUser | None = Depends(get_current_user),
) -> ProjectCreateResponse:
    # owner_id : l'utilisateur authentifié (None en mode démo local).
    project = Project(name=payload.name, owner_id=current_user.id if current_user else None)
    db.add(project)
    db.commit()
    db.refresh(project)
    return ProjectCreateResponse(id=project.id, name=project.name, status=project.status)


@app.post(
    "/api/projects/{project_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
def upload_project_document(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> DocumentUploadResponse:
    return create_document_from_upload(project_id, file, db)


@app.get("/api/projects/{project_id}/workflow", response_model=ProjectWorkflowResponse, tags=["workflow"])
def get_project_workflow(
    project_id: str,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> ProjectWorkflowResponse:
    state = get_project_state(project_id, db)
    return ProjectWorkflowResponse(project_id=project_id, state=state)


class ParcelPointIO(BaseModel):
    label: str
    x: float
    y: float
    confidence: float | None = None


class ParcelIO(BaseModel):
    id: str | None = None
    label: str
    declared_surface_m2: float | None = None
    detected_crs: str = "EPSG:32631"
    points: list[ParcelPointIO] = Field(default_factory=list)


class ParcelsResponse(BaseModel):
    parcels: list[ParcelIO]


def _read_project_parcels(project_id: str, db: Session) -> ParcelsResponse:
    _ensure_project_exists(project_id, db)
    rows = (
        db.execute(
            text(
                """
                SELECT p.id AS parcel_id, p.label AS label, p.declared_surface_m2 AS declared_surface_m2,
                       p.detected_crs AS detected_crs, sp.label AS point_label,
                       sp.source_x AS x, sp.source_y AS y, sp.confidence AS confidence
                FROM parcels p
                LEFT JOIN survey_points sp ON sp.parcel_id = p.id
                WHERE p.project_id = :project_id
                ORDER BY p.created_at, p.id, sp.point_index
                """
            ),
            {"project_id": project_id},
        )
        .mappings()
        .all()
    )
    ordered: list[str] = []
    by_id: dict[str, ParcelIO] = {}
    for row in rows:
        pid = str(row["parcel_id"])
        if pid not in by_id:
            by_id[pid] = ParcelIO(
                id=pid,
                label=str(row["label"]),
                declared_surface_m2=row["declared_surface_m2"],
                detected_crs=str(row["detected_crs"] or "EPSG:32631"),
                points=[],
            )
            ordered.append(pid)
        if row["point_label"] is not None and row["x"] is not None and row["y"] is not None:
            by_id[pid].points.append(
                ParcelPointIO(label=str(row["point_label"]), x=float(row["x"]), y=float(row["y"]), confidence=row["confidence"])
            )
    return ParcelsResponse(parcels=[by_id[pid] for pid in ordered])


@app.get("/api/projects/{project_id}/parcels", response_model=ParcelsResponse, tags=["parcels"])
def get_project_parcels(
    project_id: str,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> ParcelsResponse:
    return _read_project_parcels(project_id, db)


@app.put("/api/projects/{project_id}/parcels", response_model=ParcelsResponse, tags=["parcels"])
def replace_project_parcels(
    project_id: str,
    payload: ParcelsResponse,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> ParcelsResponse:
    # Persiste les corrections humaines : on remplace les parcelles du projet par celles
    # fournies (l'audit lit ces tables). geom WGS84 dérivé du CRS source de chaque parcelle.
    _ensure_project_exists(project_id, db)
    db.execute(text("DELETE FROM parcels WHERE project_id = :project_id"), {"project_id": project_id})
    now = datetime.now(UTC)
    for parcel in payload.parcels:
        parcel_id = str(uuid4())
        db.execute(
            text(
                """
                INSERT INTO parcels (id, project_id, levee_id, label, declared_surface_m2, detected_crs, created_at)
                VALUES (:id, :project_id, NULL, :label, :declared, :crs, :created_at)
                """
            ),
            {"id": parcel_id, "project_id": project_id, "label": parcel.label, "declared": parcel.declared_surface_m2, "crs": parcel.detected_crs, "created_at": now},
        )
        # P0.2 : on ne transforme vers WGS84 QUE si le CRS est géoréférencé. Pour un CRS
        # local/inconnu, on conserve les coordonnées source SANS géométrie WGS84 inventée
        # (geom NULL) — pas de fausse projection des coordonnées locales.
        crs = parcel.detected_crs
        transformable = crs in ("EPSG:32631", "EPSG:4326", "EPSG_32631", "EPSG_4326")
        for index, point in enumerate(parcel.points):
            params = {
                "id": str(uuid4()), "parcel_id": parcel_id, "label": point.label, "idx": index,
                "sx": point.x, "sy": point.y, "conf": point.confidence, "created_at": now,
            }
            if transformable:
                longitude, latitude = transform_coordinate_to_wgs84(point.x, point.y, crs)
                params["lon"], params["lat"] = longitude, latitude
                geom_sql = "ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)"
            else:
                geom_sql = "NULL"
            db.execute(
                text(
                    f"""
                    INSERT INTO survey_points
                        (id, parcel_id, label, point_index, source_x, source_y, confidence, geom, created_at)
                    VALUES (:id, :parcel_id, :label, :idx, :sx, :sy, :conf, {geom_sql}, :created_at)
                    """
                ),
                params,
            )
    db.commit()
    return _read_project_parcels(project_id, db)


class ProjectValidationRequest(BaseModel):
    source_crs: SUPPORTED_SOURCE_CRS = Field(default="EPSG:32631", examples=["EPSG:32631"])
    declared_surface_m2: float | None = Field(default=None, gt=0, examples=[549])
    # Optionnel : sans coordonnées, la validation ne fait que transiter l'état
    # (rétro-compatible). Avec coordonnées, on calcule la géométrie + l'audit réel.
    coordinates: list[CoordinateXY] | None = Field(
        default=None,
        min_length=3,
        examples=[[[403825.84, 707630.38], [403836.57, 707626.36], [403840.12, 707641.10], [403829.20, 707645.42]]],
    )


@app.post(
    "/api/projects/{project_id}/validate",
    response_model=ProjectValidationResponse,
    tags=["workflow"],
)
def validate_project(
    project_id: str,
    payload: ProjectValidationRequest | None = None,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> ProjectValidationResponse:
    # La transition (donc le contrôle d'état) D'ABORD : un appel sans corps reste
    # valide (rétro-compat) et un mauvais état renvoie 409 avant tout calcul.
    response = validate_project_for_audit(project_id, db)
    # Corps optionnel : si des coordonnées validées sont fournies, on calcule la
    # géométrie (Shapely) et on persiste les entrées d'audit → l'audit reflète la
    # VRAIE parcelle. Sinon l'audit retombe sur ses valeurs par défaut (historique).
    if payload is not None and payload.coordinates:
        geometry = validate_polygon(payload.coordinates, payload.source_crs)
        # Géométrie calculée, mais la confiance OCR n'est pas connue ici : on ne stocke
        # pas de score d'extraction inventé → l'audit signalera « validation humaine requise ».
        upsert_audit_inputs(
            project_id,
            db,
            extraction_score=None,
            declared_surface_m2=payload.declared_surface_m2,
            calculated_surface_m2=geometry.area_m2,
            invalid_geometry=not geometry.valid,
        )
    return response


@app.post("/api/projects/{project_id}/audit", response_model=AuditResponse, tags=["audits"])
def run_project_audit(
    project_id: str,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> AuditResponse:
    return create_project_audit(project_id, db)


@app.post(
    "/api/projects/{project_id}/audit/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    tags=["reports"],
)
def download_project_audit_report(
    project_id: str,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> Response:
    audit = create_project_audit(project_id, db)
    pdf_bytes = generate_audit_report_pdf(audit)
    headers = {"Content-Disposition": f'attachment; filename="topoaudit-{project_id}-report.pdf"'}
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


def _run_scoped_document_ocr(project_id: str, document_id: str, db: Session) -> OcrResult:
    project = (
        db.execute(text("SELECT id FROM projects WHERE id = :project_id"), {"project_id": project_id})
        .mappings()
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    document = (
        db.execute(
            text("SELECT id, project_id, content_type, storage_path FROM documents WHERE id = :document_id"),
            {"document_id": document_id},
        )
        .mappings()
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    if document["project_id"] != project_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Document does not belong to project")

    text_content, provider = extract_text_from_document(document["storage_path"], document["content_type"])
    # P0.3 : c'est ICI (et non à l'upload) que l'OCR parse et persiste les parcelles.
    parcels, detection = store_extracted_parcels(
        project_id=project_id,
        document_id=document["id"],
        ocr_text=text_content,
        db=db,
    )
    mark_project_ocr_extracted(project_id, db)

    parsed_parcels = [
        OcrParsedParcel(
            label=parcel.label,
            declared_surface_m2=parcel.declared_surface_m2,
            point_count=len(parcel.points),
            points=[OcrPoint(label=p.label, x=p.x, y=p.y) for p in parcel.points],
        )
        for parcel in parcels
    ]
    # Statut du score d'extraction au stade OCR : sans confiance OCR ni validation
    # humaine, on signale needs_human_validation (jamais de score inventé).
    total_points = sum(parcel.point_count for parcel in parsed_parcels)
    score_status = extraction_score_calculator.calculate(
        point_count=total_points,
        declared_surface_m2=next((p.declared_surface_m2 for p in parsed_parcels), None),
        detected_crs=detection.epsg,
        average_point_confidence=None,
    ).status

    configured = str(settings.ocr_provider).strip().lower()
    return OcrResult(
        provider=provider,
        configured_provider=configured,
        actual_provider=provider,
        is_mock_result=(provider == "mock"),
        extracted_text=text_content,
        parsed_parcels=parsed_parcels,
        detected_crs=detection.status.value,
        extraction_score_status=score_status,
        document_id=document["id"],
        project_id=project["id"],
    )


@app.post("/api/projects/{project_id}/documents/{document_id}/ocr", response_model=OcrResult, tags=["ocr"])
def run_document_ocr(
    project_id: str,
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _user: AuthUser | None = Depends(authorized_project_user),
) -> OcrResult:
    enforce_ocr_rate_limit(request)
    return _run_scoped_document_ocr(project_id, document_id, db)


@app.post("/api/ocr", response_model=OcrResult, tags=["ocr"])
def run_document_ocr_from_body(
    payload: OcrRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthUser | None = Depends(get_current_user),
) -> OcrResult:
    enforce_ocr_rate_limit(request)
    # project_id provient du corps : on vérifie la propriété manuellement.
    row = (
        db.execute(
            text("SELECT owner_id FROM projects WHERE id = :project_id"),
            {"project_id": payload.project_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    ensure_project_access(row.get("owner_id"), current_user)
    return _run_scoped_document_ocr(payload.project_id, payload.document_id, db)


@app.post("/api/risk/score-surface", response_model=SurfaceRiskScore, tags=["risk"])
def score_surface_risk(payload: SurfaceRiskRequest) -> SurfaceRiskScore:
    return score_surface_deviation(payload.declared_surface_m2, payload.calculated_surface_m2)


@app.get("/api", tags=["system"])
def api_root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "docs": "/api/docs"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "health": "/api/health"}
