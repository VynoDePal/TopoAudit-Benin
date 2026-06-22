"""Tests du service de score d'extraction (P0 hardening V2).

Garantit qu'aucun score n'est inventé : sans preuve de qualité d'extraction
(confiance OCR absente et pas de validation humaine) → statut
``needs_human_validation`` et jamais l'ancienne valeur codée en dur ``87``.
"""

import pytest

from app.extraction_score import (
    SCORE_STATUS_COMPUTED,
    SCORE_STATUS_NEEDS_HUMAN_VALIDATION,
    ExtractionScoreCalculator,
)

calculator = ExtractionScoreCalculator()


def test_returns_needs_human_validation_when_confidence_absent():
    result = calculator.calculate(
        point_count=4,
        declared_surface_m2=176.0,
        detected_crs="EPSG:32631",
        average_point_confidence=None,
    )
    assert result.score is None
    assert result.status == SCORE_STATUS_NEEDS_HUMAN_VALIDATION
    assert result.needs_human_validation is True


def test_never_returns_87_by_default_without_evidence():
    # Quelles que soient les autres entrées, l'absence de confiance OCR ne doit
    # jamais produire un score (et surtout pas l'ancien 87 codé en dur).
    for point_count in (0, 1, 3, 6):
        for surface in (None, 176.0):
            for crs in (None, "EPSG:32631", "LOCAL"):
                result = calculator.calculate(
                    point_count=point_count,
                    declared_surface_m2=surface,
                    detected_crs=crs,
                    average_point_confidence=None,
                )
                assert result.score is None
                assert result.status == SCORE_STATUS_NEEDS_HUMAN_VALIDATION


def test_computes_score_from_evidence_when_confidence_present():
    result = calculator.calculate(
        point_count=4,
        declared_surface_m2=176.0,
        detected_crs="EPSG:32631",
        average_point_confidence=0.5,
    )
    # 30 (≥3 points) + 30*0.5 + 15 (surface) + 15 (CRS connu) + 10 (≥3 & surface) = 85
    assert result.score == 85
    assert result.status == SCORE_STATUS_COMPUTED


def test_high_confidence_yields_high_score():
    result = calculator.calculate(
        point_count=5,
        declared_surface_m2=200.0,
        detected_crs="EPSG:4326",
        average_point_confidence=1.0,
    )
    assert result.score == 100
    assert result.status == SCORE_STATUS_COMPUTED


def test_human_validation_allows_score_without_ocr_confidence():
    result = calculator.calculate(
        point_count=4,
        declared_surface_m2=176.0,
        detected_crs="EPSG:32631",
        average_point_confidence=None,
        human_validated=True,
    )
    assert result.status == SCORE_STATUS_COMPUTED
    assert result.score is not None
    assert result.score >= 90


def test_unknown_crs_reduces_score_but_stays_computed():
    result = calculator.calculate(
        point_count=4,
        declared_surface_m2=176.0,
        detected_crs="LOCAL",
        average_point_confidence=0.8,
    )
    # Pas de bonus CRS (15) car CRS non reconnu.
    assert result.status == SCORE_STATUS_COMPUTED
    assert result.score == pytest.approx(30 + 30 * 0.8 + 15 + 10)
