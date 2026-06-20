from typing import Annotated

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

from app.config import settings
from app.crs import GEOJSON_CRS, SUPPORTED_SOURCE_CRS, transform_coordinates_to_wgs84
from app.geometry_engine import PolygonValidationResult, validate_polygon
from app.risk_scoring import SurfaceRiskScore, score_surface_deviation

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


def _database_ready() -> bool:
    try:
        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
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


@app.post("/api/risk/score-surface", response_model=SurfaceRiskScore, tags=["risk"])
def score_surface_risk(payload: SurfaceRiskRequest) -> SurfaceRiskScore:
    return score_surface_deviation(payload.declared_surface_m2, payload.calculated_surface_m2)


@app.get("/api", tags=["system"])
def api_root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "docs": "/api/docs"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "health": "/api/health"}
