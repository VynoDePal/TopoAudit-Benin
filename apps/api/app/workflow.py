from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.extraction_score import (
    SCORE_STATUS_COMPUTED,
    SCORE_STATUS_NEEDS_HUMAN_VALIDATION,
    extraction_score_calculator,
)
from app.geometry_engine import validate_polygon
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


class ParcelAuditResult(BaseModel):
    parcel_id: str | None = None
    label: str
    # ``None`` + statut ``needs_human_validation`` quand aucune preuve d'extraction
    # n'est disponible : on n'invente jamais de score.
    extraction_score: int | None = Field(default=None, ge=0, le=100)
    extraction_score_status: str = SCORE_STATUS_COMPUTED
    declared_surface_m2: float | None = Field(default=None, gt=0)
    calculated_surface_m2: float | None = Field(default=None, ge=0)
    invalid_geometry: bool = False
    technical_score: int = Field(ge=0, le=100)
    risk_level: str
    warnings: list[str]


class AuditResponse(ProjectWorkflowResponse):
    audit_id: str
    extraction_score: int | None = Field(default=None, ge=0, le=100)
    extraction_score_status: str = SCORE_STATUS_COMPUTED
    technical_score: int = Field(ge=0, le=100)
    risk_level: str
    warnings: list[str]
    parcels: list[ParcelAuditResult] = Field(default_factory=list)


class _AuditInputs(BaseModel):
    extraction_score: int | None = Field(default=None, ge=0, le=100)
    extraction_score_status: str = SCORE_STATUS_NEEDS_HUMAN_VALIDATION
    declared_surface_m2: float | None = Field(default=None, gt=0)
    calculated_surface_m2: float | None = Field(default=None, ge=0)
    invalid_geometry: bool = False
    parcel_id: str | None = None
    label: str = "Parcelle validée"
    detected_crs: str | None = None
    point_count: int = 0
    average_point_confidence: float | None = Field(default=None, ge=0, le=1)


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


def _ensure_project_exists(project_id: str, db: Session) -> None:
    row = (
        db.execute(text("SELECT id FROM projects WHERE id = :project_id"), {"project_id": project_id})
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


def _load_project_audit_input(project_id: str, db: Session) -> _AuditInputs | None:
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
        return None

    payload = dict(audit_data)
    payload.setdefault("invalid_geometry", False)
    payload["label"] = "Parcelle validée"
    # Pas de score stocké → on ne fabrique rien : validation humaine requise.
    if payload.get("extraction_score") is None:
        payload["extraction_score_status"] = SCORE_STATUS_NEEDS_HUMAN_VALIDATION
    else:
        payload["extraction_score_status"] = SCORE_STATUS_COMPUTED
    try:
        return _AuditInputs.model_validate(payload)
    except Exception:
        return None


def _coerce_source_coordinate(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_confidence(value: object) -> float | None:
    if value is None:
        return None
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return None
    if confidence > 1:
        confidence = confidence / 100
    return max(0.0, min(1.0, confidence))


def _compute_extraction_score(
    *,
    point_count: int,
    declared_surface_m2: float | None,
    detected_crs: str | None,
    average_point_confidence: float | None,
    human_validated: bool = False,
):
    """Délègue au service ExtractionScoreCalculator (preuve-based, jamais de 87 inventé)."""
    return extraction_score_calculator.calculate(
        point_count=point_count,
        declared_surface_m2=declared_surface_m2,
        detected_crs=detected_crs,
        average_point_confidence=average_point_confidence,
        human_validated=human_validated,
    )


def _load_parcel_audit_inputs(project_id: str, db: Session) -> list[_AuditInputs]:
    rows = (
        db.execute(
            text(
                """
                SELECT
                    p.id AS parcel_id,
                    p.label AS label,
                    p.declared_surface_m2 AS declared_surface_m2,
                    p.detected_crs AS detected_crs,
                    sp.source_x AS source_x,
                    sp.source_y AS source_y,
                    sp.confidence AS confidence
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
    parcels: dict[str, dict[str, object]] = {}
    for row in rows:
        parcel_id = str(row["parcel_id"])
        parcel = parcels.setdefault(
            parcel_id,
            {
                "parcel_id": parcel_id,
                "label": row.get("label") or "Parcelle sans libellé",
                "declared_surface_m2": row.get("declared_surface_m2"),
                "detected_crs": row.get("detected_crs") or "EPSG:32631",
                "coordinates": [],
                "confidences": [],
            },
        )
        source_x = _coerce_source_coordinate(row.get("source_x"))
        source_y = _coerce_source_coordinate(row.get("source_y"))
        if source_x is not None and source_y is not None:
            parcel["coordinates"].append([source_x, source_y])
        confidence = _coerce_confidence(row.get("confidence"))
        if confidence is not None:
            parcel["confidences"].append(confidence)

    inputs: list[_AuditInputs] = []
    for parcel in parcels.values():
        coordinates = parcel["coordinates"]
        confidences = parcel["confidences"]
        calculated_surface_m2: float | None = None
        invalid_geometry = True
        if isinstance(coordinates, list) and len(coordinates) >= 3:
            geometry = validate_polygon(coordinates, str(parcel["detected_crs"] or "EPSG:32631"))
            calculated_surface_m2 = geometry.area_m2
            invalid_geometry = not geometry.valid
        average_confidence = sum(confidences) / len(confidences) if isinstance(confidences, list) and confidences else None
        point_count = len(coordinates) if isinstance(coordinates, list) else 0
        score_result = _compute_extraction_score(
            point_count=point_count,
            declared_surface_m2=parcel["declared_surface_m2"],
            detected_crs=str(parcel["detected_crs"] or ""),
            average_point_confidence=average_confidence,
        )
        inputs.append(
            _AuditInputs(
                parcel_id=str(parcel["parcel_id"]),
                label=str(parcel["label"]),
                extraction_score=score_result.score,
                extraction_score_status=score_result.status,
                declared_surface_m2=parcel["declared_surface_m2"],
                calculated_surface_m2=calculated_surface_m2,
                invalid_geometry=invalid_geometry,
                detected_crs=str(parcel["detected_crs"] or ""),
                point_count=point_count,
                average_point_confidence=average_confidence,
            )
        )
    return inputs


def _load_audit_inputs(project_id: str, db: Session) -> list[_AuditInputs]:
    _ensure_project_exists(project_id, db)
    parcel_inputs = _load_parcel_audit_inputs(project_id, db)
    project_input = _load_project_audit_input(project_id, db)

    if parcel_inputs:
        has_dynamic_parcel_metrics = any(
            parcel_input.calculated_surface_m2 is not None or parcel_input.average_point_confidence is not None
            for parcel_input in parcel_inputs
        )
        if has_dynamic_parcel_metrics or project_input is None:
            return parcel_inputs

    # Aucune donnée exploitable : on ne fabrique pas de score, on signale la validation humaine.
    return [
        project_input
        or _AuditInputs(
            extraction_score=None,
            extraction_score_status=SCORE_STATUS_NEEDS_HUMAN_VALIDATION,
            label="Parcelle en attente de validation",
        )
    ]


def _compute_audit_result(inputs: _AuditInputs) -> tuple[int, str, list[str]]:
    warnings = ["Aucune comparaison cadastrale officielle effectuée."]

    if inputs.invalid_geometry:
        warnings.append(f"Incohérence géométrique détectée sur {inputs.label}.")
        technical_score = 35
        risk_level = "high"
    elif inputs.declared_surface_m2 is not None and inputs.calculated_surface_m2 is not None:
        surface_risk = score_surface_deviation(inputs.declared_surface_m2, inputs.calculated_surface_m2)
        risk_level = surface_risk.risk_level
        if risk_level == "low":
            technical_score = 92
        elif risk_level == "moderate":
            technical_score = 74
            warnings.append(f"Écart modéré entre surface déclarée et surface calculée pour {inputs.label}.")
        else:
            technical_score = 48
            warnings.append(f"Écart élevé entre surface déclarée et surface calculée pour {inputs.label}.")
    else:
        technical_score = 60
        risk_level = "moderate"
        warnings.append(f"Données de surface insuffisantes pour un scoring technique complet de {inputs.label}.")

    return technical_score, risk_level, warnings


AUDIT_INPUTS_DDL = text(
    """
    CREATE TABLE IF NOT EXISTS audit_inputs (
        project_id VARCHAR(36) PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
        extraction_score INTEGER,
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
        # Migration idempotente : retirer l'ancien défaut/NOT NULL (score 87 en dur)
        # sur les bases déjà créées avant le passage au score « preuve-based ».
        conn.execute(text("ALTER TABLE audit_inputs ALTER COLUMN extraction_score DROP DEFAULT"))
        conn.execute(text("ALTER TABLE audit_inputs ALTER COLUMN extraction_score DROP NOT NULL"))


def upsert_audit_inputs(
    project_id: str,
    db: Session,
    *,
    extraction_score: int | None = None,
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


_RISK_ORDER = {"low": 0, "moderate": 1, "high": 2}


def _aggregate_risk_level(parcel_results: list[ParcelAuditResult]) -> str:
    return max(parcel_results, key=lambda result: _RISK_ORDER.get(result.risk_level, -1)).risk_level


def create_project_audit(project_id: str, db: Session) -> AuditResponse:
    inputs_by_parcel = _load_audit_inputs(project_id, db)
    parcel_results: list[ParcelAuditResult] = []
    for inputs in inputs_by_parcel:
        technical_score, risk_level, warnings = _compute_audit_result(inputs)
        parcel_results.append(
            ParcelAuditResult(
                parcel_id=inputs.parcel_id,
                label=inputs.label,
                extraction_score=inputs.extraction_score,
                extraction_score_status=inputs.extraction_score_status,
                declared_surface_m2=inputs.declared_surface_m2,
                calculated_surface_m2=inputs.calculated_surface_m2,
                invalid_geometry=inputs.invalid_geometry,
                technical_score=technical_score,
                risk_level=risk_level,
                warnings=warnings,
            )
        )

    project_warnings = ["Aucune comparaison cadastrale officielle effectuée."]
    for parcel in parcel_results:
        project_warnings.extend(warning for warning in parcel.warnings[1:] if warning not in project_warnings)

    # Agrégat du score d'extraction : si une parcelle requiert une validation humaine,
    # le projet l'exige aussi et le score reste indisponible (jamais inventé).
    computed_scores = [
        parcel.extraction_score for parcel in parcel_results if parcel.extraction_score is not None
    ]
    project_needs_validation = any(
        parcel.extraction_score_status == SCORE_STATUS_NEEDS_HUMAN_VALIDATION for parcel in parcel_results
    )
    if project_needs_validation:
        project_extraction_score: int | None = None
        project_extraction_status = SCORE_STATUS_NEEDS_HUMAN_VALIDATION
        validation_warning = "Score d'extraction indisponible : validation humaine des coordonnées requise."
        if validation_warning not in project_warnings:
            project_warnings.append(validation_warning)
    else:
        project_extraction_score = min(computed_scores) if computed_scores else None
        project_extraction_status = SCORE_STATUS_COMPUTED

    state = transition_project_state(project_id, ProjectWorkflowState.AUDITED, db)
    return AuditResponse(
        project_id=project_id,
        state=state,
        audit_id=str(uuid4()),
        extraction_score=project_extraction_score,
        extraction_score_status=project_extraction_status,
        technical_score=min(parcel.technical_score for parcel in parcel_results),
        risk_level=_aggregate_risk_level(parcel_results),
        warnings=project_warnings,
        parcels=parcel_results,
    )
