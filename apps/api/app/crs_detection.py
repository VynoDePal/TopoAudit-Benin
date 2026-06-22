"""Détection du système de coordonnées (CRS) d'un plan topographique.

Objectif métier (anti fausse-confiance) : ne JAMAIS transformer vers WGS84 des
coordonnées dont le référentiel est inconnu ou purement local. On classe le CRS à
partir des mentions du texte OCR (WGS84, UTM 31, ITRF, EPSG) et/ou de la plausibilité
géographique des coordonnées (plages UTM 31N du Bénin), puis on autorise la
transformation uniquement pour les CRS réellement géoréférencés.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum


class CRSStatus(StrEnum):
    EPSG_32631 = "EPSG_32631"           # UTM zone 31N (WGS84) — usuel au Bénin
    EPSG_4326 = "EPSG_4326"             # géographique WGS84 (lon/lat)
    LOCAL_ONLY = "LOCAL_ONLY"           # coordonnées locales/relatives, non géoréférencées
    UNKNOWN_CRS = "UNKNOWN_CRS"         # impossible à déterminer
    NEEDS_GEOREFERENCING = "NEEDS_GEOREFERENCING"  # coords présentes mais à corriger (ex. axes inversés)


# Seuls ces statuts correspondent à un référentiel transformable vers WGS84.
_EPSG_BY_STATUS: dict[CRSStatus, str] = {
    CRSStatus.EPSG_32631: "EPSG:32631",
    CRSStatus.EPSG_4326: "EPSG:4326",
}
TRANSFORMABLE_STATUSES = frozenset(_EPSG_BY_STATUS)

# Plages plausibles UTM 31N pour le Bénin (easting / northing, en mètres).
_BENIN_UTM_X = (200_000.0, 800_000.0)
_BENIN_UTM_Y = (600_000.0, 1_500_000.0)
# Plages géographiques (EPSG:4326) du Bénin : longitude ~0–4°E, latitude ~6–13°N.
_BENIN_LON = (-0.5, 4.5)
_BENIN_LAT = (5.5, 13.5)
# En-dessous de ce seuil, des coordonnées sont considérées locales/relatives.
_LOCAL_MAX = 200_000.0


@dataclass(frozen=True)
class CRSDetectionResult:
    status: CRSStatus
    epsg: str | None
    confidence: float
    reason: str

    @property
    def is_transformable(self) -> bool:
        return self.status in TRANSFORMABLE_STATUSES


def epsg_for_status(status: CRSStatus) -> str | None:
    return _EPSG_BY_STATUS.get(status)


def detect_crs_from_text(text: str | None) -> CRSDetectionResult | None:
    """Détecte le CRS via les mentions explicites du texte OCR. ``None`` si rien."""
    if not text:
        return None
    upper = text.upper()

    match = re.search(r"EPSG\s*[:\s]\s*(\d{4,5})", upper)
    if match:
        code = match.group(1)
        if code == "32631":
            return CRSDetectionResult(CRSStatus.EPSG_32631, "EPSG:32631", 0.95, "Mention explicite EPSG:32631")
        if code == "4326":
            return CRSDetectionResult(CRSStatus.EPSG_4326, "EPSG:4326", 0.95, "Mention explicite EPSG:4326")
        return CRSDetectionResult(CRSStatus.UNKNOWN_CRS, None, 0.4, f"EPSG:{code} non pris en charge")

    # UTM 31 (avec ou sans « zone ») → projeté UTM 31N.
    if re.search(r"\bUTM\b\s*(ZONE\s*)?31", upper):
        return CRSDetectionResult(CRSStatus.EPSG_32631, "EPSG:32631", 0.85, "Mention UTM zone 31N")

    # Mentions GÉOGRAPHIQUES explicites (lon/lat, degrés) → EPSG:4326.
    if re.search(r"LONGITUDE|LATITUDE|\bLAT\b|\bLON\b|DEGR|OGRAPHI", upper):
        return CRSDetectionResult(CRSStatus.EPSG_4326, "EPSG:4326", 0.8, "Mention géographique explicite (lon/lat)")

    # « WGS84 » / « ITRF » SEULS = datum, PAS une projection → ambigu : on ne force rien
    # (surtout pas EPSG:4326). Les coordonnées décideront (anti fausse-confiance).
    return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def detect_crs_from_coordinates(coordinates: Sequence[Sequence[float]] | None) -> CRSDetectionResult:
    """Classe le CRS via la plausibilité géographique des coordonnées."""
    coords = [c for c in (coordinates or []) if c is not None and len(c) == 2]
    if not coords:
        return CRSDetectionResult(CRSStatus.UNKNOWN_CRS, None, 0.0, "Aucune coordonnée exploitable")

    xs = [float(c[0]) for c in coords]
    ys = [float(c[1]) for c in coords]
    mx, my = _median(xs), _median(ys)

    in_utm_x = _BENIN_UTM_X[0] <= mx <= _BENIN_UTM_X[1]
    in_utm_y = _BENIN_UTM_Y[0] <= my <= _BENIN_UTM_Y[1]
    if in_utm_x and in_utm_y:
        return CRSDetectionResult(CRSStatus.EPSG_32631, "EPSG:32631", 0.8, "Coordonnées plausibles UTM 31N (Bénin)")

    # Axes inversés : easting/northing intervertis (X dans la plage northing et vice-versa).
    if _BENIN_UTM_Y[0] <= mx <= _BENIN_UTM_Y[1] and _BENIN_UTM_X[0] <= my <= _BENIN_UTM_X[1]:
        return CRSDetectionResult(
            CRSStatus.NEEDS_GEOREFERENCING,
            None,
            0.5,
            "Axes X/Y probablement inversés (easting/northing intervertis)",
        )

    if _BENIN_LON[0] <= mx <= _BENIN_LON[1] and _BENIN_LAT[0] <= my <= _BENIN_LAT[1]:
        return CRSDetectionResult(CRSStatus.EPSG_4326, "EPSG:4326", 0.7, "Coordonnées géographiques plausibles (Bénin)")

    if all(abs(v) < _LOCAL_MAX for v in xs + ys):
        return CRSDetectionResult(
            CRSStatus.LOCAL_ONLY, None, 0.6, "Coordonnées locales/relatives sans référentiel global"
        )

    return CRSDetectionResult(CRSStatus.UNKNOWN_CRS, None, 0.2, "Système de coordonnées indéterminé")


def detect_crs(
    text: str | None = None,
    coordinates: Sequence[Sequence[float]] | None = None,
) -> CRSDetectionResult:
    """Combine mentions OCR et plausibilité géométrique pour classer le CRS."""
    text_result = detect_crs_from_text(text)
    coord_result = detect_crs_from_coordinates(coordinates) if coordinates else None

    # Règle métier : des coordonnées clairement UTM 31N (Bénin) l'emportent — même si le
    # texte mentionne WGS84/géographique (souvent juste le datum). Anti fausse-confiance.
    if coord_result and coord_result.status == CRSStatus.EPSG_32631:
        return coord_result
    # Inversion d'axes détectée sur les coordonnées → géoréférencement requis.
    if coord_result and coord_result.status == CRSStatus.NEEDS_GEOREFERENCING:
        return coord_result
    # Mention texte transformable EXPLICITE (EPSG / UTM 31 / géographique lon-lat).
    if text_result and text_result.is_transformable:
        return text_result
    # Sinon, ce que disent les coordonnées (lon/lat Bénin → EPSG_4326, local, etc.).
    if coord_result and coord_result.status != CRSStatus.UNKNOWN_CRS:
        return coord_result
    if text_result:
        return text_result
    return coord_result or CRSDetectionResult(CRSStatus.UNKNOWN_CRS, None, 0.0, "Aucune information CRS")
