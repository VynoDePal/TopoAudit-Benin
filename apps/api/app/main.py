from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crs import GEOJSON_CRS, SUPPORTED_SOURCE_CRS, transform_coordinates_to_wgs84
from app.database import get_db, get_engine
from app.geometry_engine import PolygonValidationResult, validate_polygon
from app.models import Base, Project
from app.ocr import OcrResult, enforce_ocr_rate_limit, extract_text_from_document
from app.pdf_report import generate_audit_report_pdf
from app.risk_scoring import SurfaceRiskScore, score_surface_deviation
from app.uploads import DocumentUploadResponse, create_document_from_upload
from app.workflow import (
    AuditResponse,
    ProjectValidationResponse,
    ProjectWorkflowResponse,
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


@app.post(
    "/api/projects",
    response_model=ProjectCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
)
def create_project(payload: ProjectCreateRequest, db: Session = Depends(get_db)) -> ProjectCreateResponse:
    project = Project(name=payload.name)
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
) -> DocumentUploadResponse:
    return create_document_from_upload(project_id, file, db)


@app.get("/api/projects/{project_id}/workflow", response_model=ProjectWorkflowResponse, tags=["workflow"])
def get_project_workflow(project_id: str, db: Session = Depends(get_db)) -> ProjectWorkflowResponse:
    state = get_project_state(project_id, db)
    return ProjectWorkflowResponse(project_id=project_id, state=state)


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
) -> ProjectValidationResponse:
    # La transition (donc le contrôle d'état) D'ABORD : un appel sans corps reste
    # valide (rétro-compat) et un mauvais état renvoie 409 avant tout calcul.
    response = validate_project_for_audit(project_id, db)
    # Corps optionnel : si des coordonnées validées sont fournies, on calcule la
    # géométrie (Shapely) et on persiste les entrées d'audit → l'audit reflète la
    # VRAIE parcelle. Sinon l'audit retombe sur ses valeurs par défaut (historique).
    if payload is not None and payload.coordinates:
        geometry = validate_polygon(payload.coordinates, payload.source_crs)
        upsert_audit_inputs(
            project_id,
            db,
            extraction_score=87,
            declared_surface_m2=payload.declared_surface_m2,
            calculated_surface_m2=geometry.area_m2,
            invalid_geometry=not geometry.valid,
        )
    return response


@app.post("/api/projects/{project_id}/audit", response_model=AuditResponse, tags=["audits"])
def run_project_audit(project_id: str, db: Session = Depends(get_db)) -> AuditResponse:
    return create_project_audit(project_id, db)


@app.post(
    "/api/projects/{project_id}/audit/report.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
    tags=["reports"],
)
def download_project_audit_report(project_id: str, db: Session = Depends(get_db)) -> Response:
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
    mark_project_ocr_extracted(project_id, db)
    return OcrResult(provider=provider, text=text_content, document_id=document["id"], project_id=project["id"])


@app.post("/api/projects/{project_id}/documents/{document_id}/ocr", response_model=OcrResult, tags=["ocr"])
def run_document_ocr(
    project_id: str,
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> OcrResult:
    enforce_ocr_rate_limit(request)
    return _run_scoped_document_ocr(project_id, document_id, db)


@app.post("/api/ocr", response_model=OcrResult, tags=["ocr"])
def run_document_ocr_from_body(
    payload: OcrRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> OcrResult:
    enforce_ocr_rate_limit(request)
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
