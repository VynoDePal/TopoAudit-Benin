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
from app.territory_check import TerritoryCheckResult, validate_benin_territory


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
    # Indicateur SÉPARÉ de la validation humaine — n'influence PAS extraction_score.
    human_validated: bool = False
    declared_surface_m2: float | None = Field(default=None, gt=0)
    calculated_surface_m2: float | None = Field(default=None, ge=0)
    invalid_geometry: bool = False
    technical_score: int = Field(ge=0, le=100)
    risk_level: str
    warnings: list[str]
    # Contrôle territorial Bénin (P0) — non juridique, prototype grossier.
    territory_status: str = "unknown"
    territory_risk_level: str = "not_applicable"
    territory_message: str = ""
    territory_intersection_ratio: float | None = None
    territory_centroid_lon: float | None = None
    territory_centroid_lat: float | None = None


class AuditResponse(ProjectWorkflowResponse):
    audit_id: str
    extraction_score: int | None = Field(default=None, ge=0, le=100)
    extraction_score_status: str = SCORE_STATUS_COMPUTED
    human_validated: bool = False
    technical_score: int = Field(ge=0, le=100)
    risk_level: str
    warnings: list[str]
    parcels: list[ParcelAuditResult] = Field(default_factory=list)
    # Contrôle territorial Bénin agrégé (pire cas des parcelles).
    territory_status: str = "unknown"
    territory_risk_level: str = "not_applicable"
    territory_warnings: list[str] = Field(default_factory=list)
    territory_centroid_lon: float | None = None
    territory_centroid_lat: float | None = None


class _AuditInputs(BaseModel):
    extraction_score: int | None = Field(default=None, ge=0, le=100)
    extraction_score_status: str = SCORE_STATUS_NEEDS_HUMAN_VALIDATION
    human_validated: bool = False
    declared_surface_m2: float | None = Field(default=None, gt=0)
    calculated_surface_m2: float | None = Field(default=None, ge=0)
    invalid_geometry: bool = False
    parcel_id: str | None = None
    label: str = "Parcelle validée"
    detected_crs: str | None = None
    point_count: int = 0
    average_point_confidence: float | None = Field(default=None, ge=0, le=1)
    territory: TerritoryCheckResult | None = None


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
                    sp.confidence AS confidence,
                    sp.human_validated AS human_validated
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
                # Pas de défaut silencieux EPSG:32631 : CRS absent → UNKNOWN_CRS
                # (l'audit ne calculera pas de surface UTM sur un CRS non confirmé).
                "detected_crs": row.get("detected_crs") or "UNKNOWN_CRS",
                "coordinates": [],
                "confidences": [],
                "human_validated": [],
            },
        )
        source_x = _coerce_source_coordinate(row.get("source_x"))
        source_y = _coerce_source_coordinate(row.get("source_y"))
        if source_x is not None and source_y is not None:
            parcel["coordinates"].append([source_x, source_y])
            # Validation humaine par borne (indicateur séparé — jamais une confiance OCR).
            parcel["human_validated"].append(bool(row.get("human_validated")))
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
            geometry = validate_polygon(coordinates, str(parcel["detected_crs"] or "UNKNOWN_CRS"))
            calculated_surface_m2 = geometry.area_m2
            invalid_geometry = not geometry.valid
        average_confidence = sum(confidences) / len(confidences) if isinstance(confidences, list) and confidences else None
        point_count = len(coordinates) if isinstance(coordinates, list) else 0
        hv_list = parcel["human_validated"] if isinstance(parcel["human_validated"], list) else []
        parcel_human_validated = len(hv_list) > 0 and all(hv_list)
        # IMPORTANT : la validation humaine N'est PAS passée à _compute_extraction_score —
        # le score d'extraction reste fondé sur les preuves OCR réelles (confiance machine).
        score_result = _compute_extraction_score(
            point_count=point_count,
            declared_surface_m2=parcel["declared_surface_m2"],
            detected_crs=str(parcel["detected_crs"] or ""),
            average_point_confidence=average_confidence,
        )
        # Contrôle territorial Bénin : sur les coordonnées SOURCE + le CRS détecté. Pour un
        # CRS local/inconnu, validate_benin_territory renvoie not_applicable (jamais de
        # transformation forcée).
        detected_crs = str(parcel["detected_crs"] or "UNKNOWN_CRS")
        territory = validate_benin_territory(coordinates if isinstance(coordinates, list) else [], detected_crs)
        inputs.append(
            _AuditInputs(
                parcel_id=str(parcel["parcel_id"]),
                label=str(parcel["label"]),
                extraction_score=score_result.score,
                extraction_score_status=score_result.status,
                human_validated=parcel_human_validated,
                declared_surface_m2=parcel["declared_surface_m2"],
                calculated_surface_m2=calculated_surface_m2,
                invalid_geometry=invalid_geometry,
                detected_crs=detected_crs,
                point_count=point_count,
                average_point_confidence=average_confidence,
                territory=territory,
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


def _escalate_risk(current: str, target: str) -> str:
    """Remonte le niveau de risque au max (parmi les types EXISTANTS low/moderate/high)."""
    return current if _RISK_ORDER.get(current, -1) >= _RISK_ORDER.get(target, -1) else target


# Sévérité territoriale pour choisir la « pire » parcelle (agrégat projet).
_TERRITORY_SEVERITY = {
    "outside_benin": 4,
    "near_border_partial": 3,
    "invalid_geometry": 2,
    "inside_benin": 1,
    "not_applicable_local_crs": 0,
    "unknown": 0,
}
_TERRITORY_OUTSIDE_WARNING = "Le tracé géoréférencé tombe hors du territoire béninois."
_TERRITORY_NEAR_WARNING = "Le tracé géoréférencé chevauche la frontière béninoise (partiellement hors Bénin)."
_TERRITORY_NOT_APPLICABLE_WARNING = "Contrôle territorial non applicable : CRS local ou inconnu."


def _apply_territory_scoring(
    technical_score: int, risk_level: str, warnings: list[str], territory: TerritoryCheckResult
) -> tuple[int, str, list[str]]:
    """Pénalise le score / escalade le risque selon le contrôle territorial (non juridique)."""
    warnings = list(warnings)

    def add(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    if territory.status == "outside_benin":
        # Hors Bénin = incohérence grave (CRS/projection) → plafonne le score technique.
        technical_score = min(technical_score, 20)
        risk_level = _escalate_risk(risk_level, "high")
        add(_TERRITORY_OUTSIDE_WARNING)
    elif territory.status == "near_border_partial":
        risk_level = _escalate_risk(risk_level, "high")
        add(_TERRITORY_NEAR_WARNING)
    elif territory.status == "not_applicable_local_crs":
        # CRS local/inconnu : NE PAS pénaliser comme un faux levé.
        add(_TERRITORY_NOT_APPLICABLE_WARNING)
    return technical_score, risk_level, warnings


def create_project_audit(project_id: str, db: Session) -> AuditResponse:
    inputs_by_parcel = _load_audit_inputs(project_id, db)
    parcel_results: list[ParcelAuditResult] = []
    for inputs in inputs_by_parcel:
        technical_score, risk_level, warnings = _compute_audit_result(inputs)
        territory = inputs.territory or TerritoryCheckResult(
            status="unknown", risk_level="not_applicable", message=""
        )
        technical_score, risk_level, warnings = _apply_territory_scoring(
            technical_score, risk_level, warnings, territory
        )
        parcel_results.append(
            ParcelAuditResult(
                parcel_id=inputs.parcel_id,
                label=inputs.label,
                extraction_score=inputs.extraction_score,
                extraction_score_status=inputs.extraction_score_status,
                human_validated=inputs.human_validated,
                declared_surface_m2=inputs.declared_surface_m2,
                calculated_surface_m2=inputs.calculated_surface_m2,
                invalid_geometry=inputs.invalid_geometry,
                technical_score=technical_score,
                risk_level=risk_level,
                warnings=warnings,
                territory_status=territory.status,
                territory_risk_level=territory.risk_level,
                territory_message=territory.message,
                territory_intersection_ratio=territory.intersection_ratio,
                territory_centroid_lon=territory.centroid_lon,
                territory_centroid_lat=territory.centroid_lat,
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

    # Indicateur projet : toutes les bornes de toutes les parcelles validées humainement.
    project_human_validated = len(parcel_results) > 0 and all(parcel.human_validated for parcel in parcel_results)

    # Agrégat territorial : la « pire » parcelle (hors Bénin > frontière > … > non applicable).
    worst_territory = max(parcel_results, key=lambda p: _TERRITORY_SEVERITY.get(p.territory_status, 0))
    territory_warnings: list[str] = []
    for parcel in parcel_results:
        if parcel.territory_status == "outside_benin" and _TERRITORY_OUTSIDE_WARNING not in territory_warnings:
            territory_warnings.append(_TERRITORY_OUTSIDE_WARNING)
        elif parcel.territory_status == "near_border_partial" and _TERRITORY_NEAR_WARNING not in territory_warnings:
            territory_warnings.append(_TERRITORY_NEAR_WARNING)
        elif (
            parcel.territory_status == "not_applicable_local_crs"
            and _TERRITORY_NOT_APPLICABLE_WARNING not in territory_warnings
        ):
            territory_warnings.append(_TERRITORY_NOT_APPLICABLE_WARNING)

    state = transition_project_state(project_id, ProjectWorkflowState.AUDITED, db)
    return AuditResponse(
        project_id=project_id,
        state=state,
        audit_id=str(uuid4()),
        extraction_score=project_extraction_score,
        extraction_score_status=project_extraction_status,
        human_validated=project_human_validated,
        technical_score=min(parcel.technical_score for parcel in parcel_results),
        risk_level=_aggregate_risk_level(parcel_results),
        warnings=project_warnings,
        parcels=parcel_results,
        territory_status=worst_territory.territory_status,
        territory_risk_level=worst_territory.territory_risk_level,
        territory_warnings=territory_warnings,
        territory_centroid_lon=worst_territory.territory_centroid_lon,
        territory_centroid_lat=worst_territory.territory_centroid_lat,
    )
