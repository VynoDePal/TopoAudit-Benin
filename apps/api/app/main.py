from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text

from app.config import settings

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


@app.get("/api", tags=["system"])
def api_root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "docs": "/api/docs"}


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"message": "TopoAudit Benin API", "health": "/api/health"}
