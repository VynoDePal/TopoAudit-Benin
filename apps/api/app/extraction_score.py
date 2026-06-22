"""Service de calcul du score d'extraction.

Principe métier (anti fausse-confiance) : le score est calculé À PARTIR DE PREUVES
(présence de coordonnées, nombre de bornes, surface déclarée, CRS détecté, confiance
OCR, validation humaine). Si aucune preuve de qualité d'extraction n'est disponible
(confiance OCR absente ET pas de validation humaine), on NE renvoie PAS de score
inventé : on renvoie le statut ``needs_human_validation``.
"""

from __future__ import annotations

from dataclasses import dataclass

# Statuts possibles du score d'extraction.
SCORE_STATUS_COMPUTED = "computed"
SCORE_STATUS_NEEDS_HUMAN_VALIDATION = "needs_human_validation"

_KNOWN_CRS = {"EPSG:32631", "EPSG:4326"}


@dataclass(frozen=True)
class ExtractionScoreResult:
    """Résultat du calcul : un score sur 100 OU un statut « validation humaine requise »."""

    score: int | None
    status: str

    @property
    def needs_human_validation(self) -> bool:
        return self.status == SCORE_STATUS_NEEDS_HUMAN_VALIDATION


class ExtractionScoreCalculator:
    """Calcule le score d'extraction d'une parcelle à partir des preuves disponibles."""

    def calculate(
        self,
        *,
        point_count: int,
        declared_surface_m2: float | None,
        detected_crs: str | None,
        average_point_confidence: float | None,
        human_validated: bool = False,
    ) -> ExtractionScoreResult:
        # Sans confiance OCR ni validation humaine, aucune preuve de qualité
        # d'extraction → on ne fabrique pas de score.
        if average_point_confidence is None and not human_validated:
            return ExtractionScoreResult(score=None, status=SCORE_STATUS_NEEDS_HUMAN_VALIDATION)

        # Validation humaine sans confiance OCR : coordonnées vérifiées par un humain →
        # on traite la fiabilité des points comme avérée (proxy de confiance = 1.0).
        confidence = average_point_confidence if average_point_confidence is not None else 1.0

        score = 0.0
        if point_count >= 3:
            score += 30
        elif point_count > 0:
            score += 10 * point_count

        score += 30 * confidence

        if declared_surface_m2 is not None:
            score += 15
        if detected_crs in _KNOWN_CRS:
            score += 15
        if point_count >= 3 and declared_surface_m2 is not None:
            score += 10

        return ExtractionScoreResult(score=max(0, min(100, round(score))), status=SCORE_STATUS_COMPUTED)


# Instance partagée (sans état) réutilisable par le moteur d'audit.
extraction_score_calculator = ExtractionScoreCalculator()
