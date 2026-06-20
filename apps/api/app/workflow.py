from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.risk_scoring import score_surface_deviation


class ProjectWorkflowState(StrEnum):
    UPLOADED = "UPLOADED"
    OCR_EXTRACTED = "OCR_EXTRACTED"
    VALIDATED = "VALIDATED"
    AUDITED = "AUDITED"


class ProjectWorkflowResponse(BaseModel):
    project_id: str
    state: ProjectWorkflowState = Field(description="Current audit workflow state")


class ProjectValidationResponse(ProjectWorkflowResponse):
    validated_at: datetime


class AuditResponse(ProjectWorkflowResponse):
    audit_id: str
    extraction_score: int = Field(ge=0, le=100)
    technical_score: int = Field(ge=0, le=100)
    risk_level: str
    warnings: list[str]


class _AuditInputs(BaseModel):
    extraction_score: int = Field(ge=0, le=100)
    declared_surface_m2: float | None = Field(default=None, gt=0)
    calculated_surface_m2: float | None = Field(default=None, ge=0)
    invalid_geometry: bool = False


_ALLOWED_PREVIOUS_STATES: dict[ProjectWorkflowState, set[ProjectWorkflowState | None]] = {
    ProjectWorkflowState.UPLOADED: {None, ProjectWorkflowState.UPLOADED},
    ProjectWorkflowState.OCR_EXTRACTED: {ProjectWorkflowState.UPLOADED, ProjectWorkflowState.OCR_EXTRACTED},
    ProjectWorkflowState.VALIDATED: {ProjectWorkflowState.OCR_EXTRACTED, ProjectWorkflowState.VALIDATED},
    ProjectWorkflowState.AUDITED: {ProjectWorkflowState.VALIDATED, ProjectWorkflowState.AUDITED},
}


def _coerce_state(raw_state: object) -> ProjectWorkflowState | None:
    if raw_state is None:
        return None
    try:
        return ProjectWorkflowState(str(raw_state))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Unsupported project workflow state: {raw_state}",
        ) from exc


def get_project_state(project_id: str, db: Session) -> ProjectWorkflowState:
    project = (
        db.execute(text("SELECT id, status FROM projects WHERE id = :project_id"), {"project_id": project_id})
        .mappings()
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    state = _coerce_state(project.get("status"))
    if state is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project has no workflow state")
    return state


def transition_project_state(project_id: str, target_state: ProjectWorkflowState, db: Session) -> ProjectWorkflowState:
    project = (
        db.execute(text("SELECT id, status FROM projects WHERE id = :project_id"), {"project_id": project_id})
        .mappings()
        .first()
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    current_state = _coerce_state(project.get("status"))
    allowed_states = _ALLOWED_PREVIOUS_STATES[target_state]
    if current_state not in allowed_states:
        allowed = ", ".join(state.value if state else "<unset>" for state in allowed_states)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot move project from {current_state.value if current_state else '<unset>'} to {target_state.value}; expected one of: {allowed}",
        )

    if current_state != target_state:
        db.execute(
            text("UPDATE projects SET status = :status WHERE id = :project_id"),
            {"project_id": project_id, "status": target_state.value},
        )
    db.commit()

    return target_state


def mark_project_uploaded(project_id: str, db: Session) -> ProjectWorkflowState:
    return transition_project_state(project_id, ProjectWorkflowState.UPLOADED, db)


def mark_project_ocr_extracted(project_id: str, db: Session) -> ProjectWorkflowState:
    return transition_project_state(project_id, ProjectWorkflowState.OCR_EXTRACTED, db)


def validate_project_for_audit(project_id: str, db: Session) -> ProjectValidationResponse:
    state = transition_project_state(project_id, ProjectWorkflowState.VALIDATED, db)
    return ProjectValidationResponse(project_id=project_id, state=state, validated_at=datetime.now(UTC))


def _load_audit_inputs(project_id: str, db: Session) -> _AuditInputs:
    row = (
        db.execute(text("SELECT id FROM projects WHERE id = :project_id"), {"project_id": project_id})
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    audit_data = (
        db.execute(
            text(
                """
                SELECT extraction_score, declared_surface_m2, calculated_surface_m2, invalid_geometry
                FROM audit_inputs
                WHERE project_id = :project_id
                """
            ),
            {"project_id": project_id},
        )
        .mappings()
        .first()
    )
    if audit_data is None:
        return _AuditInputs(extraction_score=87)

    payload = dict(audit_data)
    payload.setdefault("extraction_score", 87)
    payload.setdefault("invalid_geometry", False)
    try:
        return _AuditInputs.model_validate(payload)
    except Exception:
        return _AuditInputs(extraction_score=87)


def _compute_audit_result(inputs: _AuditInputs) -> tuple[int, str, list[str]]:
    warnings = ["Aucune comparaison cadastrale officielle effectuée."]

    if inputs.invalid_geometry:
        warnings.append("Incohérence géométrique détectée sur la parcelle validée.")
        technical_score = 35
        risk_level = "high"
    elif inputs.declared_surface_m2 is not None and inputs.calculated_surface_m2 is not None:
        surface_risk = score_surface_deviation(inputs.declared_surface_m2, inputs.calculated_surface_m2)
        risk_level = surface_risk.risk_level
        if risk_level == "low":
            technical_score = 92
        elif risk_level == "moderate":
            technical_score = 74
            warnings.append("Écart modéré entre surface déclarée et surface calculée.")
        else:
            technical_score = 48
            warnings.append("Écart élevé entre surface déclarée et surface calculée.")
    else:
        technical_score = 60
        risk_level = "moderate"
        warnings.append("Données de surface insuffisantes pour un scoring technique complet.")

    return technical_score, risk_level, warnings


AUDIT_INPUTS_DDL = text(
    """
    CREATE TABLE IF NOT EXISTS audit_inputs (
        project_id VARCHAR(36) PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        extraction_score INTEGER NOT NULL DEFAULT 87,
        declared_surface_m2 DOUBLE PRECISION,
        calculated_surface_m2 DOUBLE PRECISION,
        invalid_geometry BOOLEAN NOT NULL DEFAULT FALSE
    )
    """
)


def ensure_audit_inputs_table(bind) -> None:
    """Crée la table ``audit_inputs`` (référencée en SQL brut, hors ORM) — appelée au startup."""
    with bind.begin() as conn:
        conn.execute(AUDIT_INPUTS_DDL)


def upsert_audit_inputs(
    project_id: str,
    db: Session,
    *,
    extraction_score: int = 87,
    declared_surface_m2: float | None = None,
    calculated_surface_m2: float | None = None,
    invalid_geometry: bool = False,
) -> None:
    """Enregistre les entrées d'audit calculées à la validation (upsert par projet)."""
    db.execute(
        text(
            """
            INSERT INTO audit_inputs
                (project_id, extraction_score, declared_surface_m2, calculated_surface_m2, invalid_geometry)
            VALUES (:pid, :es, :dec, :calc, :inv)
            ON CONFLICT (project_id) DO UPDATE SET
                extraction_score = EXCLUDED.extraction_score,
                declared_surface_m2 = EXCLUDED.declared_surface_m2,
                calculated_surface_m2 = EXCLUDED.calculated_surface_m2,
                invalid_geometry = EXCLUDED.invalid_geometry
            """
        ),
        {
            "pid": project_id,
            "es": extraction_score,
            "dec": declared_surface_m2,
            "calc": calculated_surface_m2,
            "inv": invalid_geometry,
        },
    )
    db.commit()


def create_project_audit(project_id: str, db: Session) -> AuditResponse:
    inputs = _load_audit_inputs(project_id, db)
    technical_score, risk_level, warnings = _compute_audit_result(inputs)
    state = transition_project_state(project_id, ProjectWorkflowState.AUDITED, db)
    return AuditResponse(
        project_id=project_id,
        state=state,
        audit_id=str(uuid4()),
        extraction_score=inputs.extraction_score,
        technical_score=technical_score,
        risk_level=risk_level,
        warnings=warnings,
    )
