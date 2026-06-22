"""Métriques d'évaluation OCR/parser (P0 hardening V2, benchmark).

Compare l'extraction (parser + détection CRS) à une vérité terrain :
- point_recall : part des bornes attendues retrouvées (à une tolérance près) ;
- coordinate_mae : erreur moyenne (euclidienne, mètres) sur les bornes appariées ;
- surface_accuracy : 1 − |surface_extraite − surface_attendue| / attendue (borné [0,1]) ;
- parcel_count_accuracy : exactitude du nombre de parcelles ;
- crs_detection_accuracy : CRS détecté == CRS attendu (1/0).

Aucun appel réseau : on travaille sur du texte OCR fourni (evaluate_parser) ou sur le
texte renvoyé par un provider réel appelé en amont (evaluate_real_ocr).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from app.crs_detection import detect_crs
from app.uploads import extract_parcels_from_ocr_text

# Tolérance d'appariement d'une borne (mètres en UTM ; les coords sont en mètres).
DEFAULT_MATCH_TOLERANCE_M = 2.0


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    point_recall: float
    coordinate_mae: float | None
    surface_accuracy: float | None
    parcel_count_accuracy: float
    crs_detection_accuracy: float
    detected_crs: str
    expected_crs: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _expected_points(case: dict[str, Any]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for raw in case.get("expected_coordinates", []) or []:
        points.append((float(raw["x"]), float(raw["y"])))
    return points


def point_recall_and_mae(
    expected: list[tuple[float, float]],
    parsed: list[tuple[float, float]],
    tolerance: float = DEFAULT_MATCH_TOLERANCE_M,
) -> tuple[float, float | None]:
    """Appariement glouton plus-proche-voisin ; retourne (recall, MAE des appariés)."""
    if not expected:
        return 1.0, None
    used: set[int] = set()
    errors: list[float] = []
    for ex, ey in expected:
        best_index: int | None = None
        best_distance: float | None = None
        for index, (px, py) in enumerate(parsed):
            if index in used:
                continue
            distance = math.hypot(px - ex, py - ey)
            if best_distance is None or distance < best_distance:
                best_distance, best_index = distance, index
        if best_index is not None and best_distance is not None and best_distance <= tolerance:
            used.add(best_index)
            errors.append(best_distance)
    recall = len(errors) / len(expected)
    mae = sum(errors) / len(errors) if errors else None
    return recall, mae


def surface_accuracy(expected: float | None, parsed: float | None) -> float | None:
    if expected is None or expected == 0:
        return None
    if parsed is None:
        return 0.0
    return max(0.0, 1.0 - abs(parsed - expected) / abs(expected))


def count_accuracy(expected: int, parsed: int) -> float:
    if expected <= 0:
        return 1.0 if parsed == 0 else 0.0
    return max(0.0, 1.0 - abs(parsed - expected) / expected)


def evaluate_parser_case(case: dict[str, Any], tolerance: float = DEFAULT_MATCH_TOLERANCE_M) -> CaseMetrics:
    """Évalue le parser + la détection CRS sur le texte OCR d'un cas (offline)."""
    ocr_text = case.get("ocr_text", "")
    parsed_parcels = extract_parcels_from_ocr_text(ocr_text)
    parsed_points = [(point.x, point.y) for parcel in parsed_parcels for point in parcel.points]
    detection = detect_crs(text=ocr_text, coordinates=parsed_points or None)

    expected_points = _expected_points(case)
    recall, mae = point_recall_and_mae(expected_points, parsed_points, tolerance)

    parsed_surface = next(
        (parcel.declared_surface_m2 for parcel in parsed_parcels if parcel.declared_surface_m2 is not None),
        None,
    )
    expected_crs = str(case.get("expected_crs", "UNKNOWN_CRS"))
    return CaseMetrics(
        case_id=str(case.get("id", "?")),
        point_recall=recall,
        coordinate_mae=mae,
        surface_accuracy=surface_accuracy(case.get("expected_surface_m2"), parsed_surface),
        parcel_count_accuracy=count_accuracy(int(case.get("expected_parcel_count", 0)), len(parsed_parcels)),
        crs_detection_accuracy=1.0 if detection.status.value == expected_crs else 0.0,
        detected_crs=detection.status.value,
        expected_crs=expected_crs,
    )


def aggregate(metrics: list[CaseMetrics]) -> dict[str, Any]:
    def _mean(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None

    return {
        "case_count": len(metrics),
        "point_recall": _mean([m.point_recall for m in metrics]),
        "coordinate_mae": _mean([m.coordinate_mae for m in metrics if m.coordinate_mae is not None]),
        "surface_accuracy": _mean([m.surface_accuracy for m in metrics if m.surface_accuracy is not None]),
        "parcel_count_accuracy": _mean([m.parcel_count_accuracy for m in metrics]),
        "crs_detection_accuracy": _mean([m.crs_detection_accuracy for m in metrics]),
        "cases": [m.as_dict() for m in metrics],
    }
