from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.crs import GEOJSON_CRS, SUPPORTED_SOURCE_CRS, transform_coordinates_to_wgs84
from app.database import get_db, get_engine
from app.geometry_engine import PolygonValidationResult, validate_polygon
from app.ocr import OcrResult, enforce_ocr_rate_limit, extract_text_from_document
from app.risk_scoring import SurfaceRiskScore, score_surface_deviation
from app.uploads import DocumentUploadResponse, create_document_from_upload
from app.workflow import (
    AuditResponse,
    ProjectValidationResponse,
    ProjectWorkflowResponse,
    create_project_audit,
    get_project_state,
    mark_project_ocr_extracted,
    validate_project_for_audit,
)

app = FastAPI(
    title=settings.app_name,
    description="API prototype pour audit préliminaire de plans topographiques au Bénin.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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


@app.post(
    "/api/projects/{project_id}/validate",
    response_model=ProjectValidationResponse,
    tags=["workflow"],
)
def validate_project(project_id: str, db: Session = Depends(get_db)) -> ProjectValidationResponse:
    return validate_project_for_audit(project_id, db)


@app.post("/api/projects/{project_id}/audit", response_model=AuditResponse, tags=["audits"])
def run_project_audit(project_id: str, db: Session = Depends(get_db)) -> AuditResponse:
    return create_project_audit(project_id, db)


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
