"""Contrôle territorial Bénin (P0).

Vérifie qu'une parcelle GÉORÉFÉRENCÉE tombe bien dans le territoire béninois. Un levé
peut être lisible et géométriquement cohérent mais, une fois projeté, tomber hors Bénin
(mauvais CRS, axes inversés, mauvaise projection) ou dans l'océan.

NON JURIDIQUE : on ne parle jamais de « fraude ». Hors Bénin = « probablement mal
géoréférencé / mal projeté / incohérent avec le contexte Bénin ». CRS local/inconnu =
« contrôle impossible » (jamais classé comme faux levé). Frontière = Natural Earth (1:50m),
contrôle GROSSIER de prototype, non référence cadastrale.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field
from shapely.geometry import Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

from app.crs import NonTransformableCRSError, transform_coordinates_to_wgs84

_BOUNDARY_PATH = Path(__file__).parent / "data" / "benin_boundary.geojson"

# CRS transformables vers WGS84 (formes « : » et « _ »). Tout le reste (LOCAL_ONLY,
# UNKNOWN_CRS, NEEDS_GEOREFERENCING) n'est PAS géoréférencé → contrôle non applicable.
_TRANSFORMABLE_CRS = frozenset({"EPSG:32631", "EPSG_32631", "EPSG:4326", "EPSG_4326"})

# Seuil d'inclusion : ≥ 95 % de l'aire dans le Bénin (+ centroïde dedans) = inside.
_INSIDE_RATIO_THRESHOLD = 0.95


class TerritoryCheckResult(BaseModel):
    """Résultat du contrôle territorial Bénin pour un tracé."""

    status: str = Field(
        examples=["inside_benin"],
        description="inside_benin | outside_benin | near_border_partial | not_applicable_local_crs | invalid_geometry | unknown",
    )
    risk_level: str = Field(examples=["low"], description="low | moderate | high | critical | not_applicable")
    is_inside_benin: bool | None = None
    centroid_lon: float | None = None
    centroid_lat: float | None = None
    intersection_ratio: float | None = None
    points_outside_count: int | None = None
    message: str


_OUTSIDE_MESSAGE = (
    "Le tracé géoréférencé est hors du territoire béninois. Le levé est probablement mal "
    "géoréférencé, mal projeté ou incohérent avec le contexte Bénin."
)
_NOT_APPLICABLE_MESSAGE = "CRS non géoréférencé : contrôle territorial impossible."


@lru_cache(maxsize=1)
def load_benin_boundary() -> BaseGeometry:
    """Charge la frontière Bénin (Natural Earth 1:50m) en géométrie shapely (valide)."""
    data = json.loads(_BOUNDARY_PATH.read_text(encoding="utf-8"))
    features = data.get("features") if isinstance(data, dict) else None
    geometry = shape(features[0]["geometry"]) if features else shape(data)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)  # répare une frontière auto-intersectée éventuelle
    return geometry


def is_transformable_crs(crs: str) -> bool:
    """Vrai si le CRS est géoréférencé (transformable vers WGS84). LOCAL/UNKNOWN → False."""
    return str(crs).strip() in _TRANSFORMABLE_CRS


def coordinates_to_wgs84_polygon(coordinates: Sequence[Sequence[float]], source_crs: str) -> Polygon:
    """Projette les bornes (CRS source) en polygone WGS84 (lon/lat). Lève si non transformable."""
    wgs84 = transform_coordinates_to_wgs84(coordinates, source_crs)
    return Polygon([(lon, lat) for lon, lat in wgs84])


def _invalid(message: str) -> TerritoryCheckResult:
    return TerritoryCheckResult(status="invalid_geometry", risk_level="high", message=message)


def validate_benin_territory(coordinates: Sequence[Sequence[float]], source_crs: str) -> TerritoryCheckResult:
    """Contrôle territorial : la parcelle géoréférencée tombe-t-elle dans le Bénin ?"""
    crs = str(source_crs).strip()
    # CRS non géoréférencé : on ne transforme JAMAIS un LOCAL_ONLY comme de l'UTM.
    if not is_transformable_crs(crs):
        return TerritoryCheckResult(
            status="not_applicable_local_crs",
            risk_level="not_applicable",
            is_inside_benin=None,
            message=_NOT_APPLICABLE_MESSAGE,
        )

    if coordinates is None or len(coordinates) < 3:
        return _invalid("Géométrie invalide : au moins 3 bornes sont requises pour le contrôle territorial.")

    try:
        wgs84_points = transform_coordinates_to_wgs84(coordinates, crs)
        parcel: BaseGeometry = Polygon([(lon, lat) for lon, lat in wgs84_points])
    except (NonTransformableCRSError, ValueError, TypeError):
        return _invalid("Géométrie invalide : transformation ou construction du polygone impossible.")

    if not parcel.is_valid:
        parcel = parcel.buffer(0)  # répare une auto-intersection (polygone en « nœud papillon »)
    if parcel.is_empty or parcel.area <= 0:
        return _invalid("Géométrie invalide : polygone dégénéré (aire nulle).")

    benin = load_benin_boundary()
    centroid = parcel.centroid
    # covers (et non contains) : accepte les points EXACTEMENT sur la frontière.
    centroid_inside = bool(benin.covers(centroid))
    points_outside = sum(1 for lon, lat in wgs84_points if not benin.covers(Point(lon, lat)))
    intersection_ratio = float(parcel.intersection(benin).area / parcel.area)

    common = {
        "centroid_lon": float(centroid.x),
        "centroid_lat": float(centroid.y),
        "intersection_ratio": round(intersection_ratio, 6),
        "points_outside_count": points_outside,
    }

    if intersection_ratio >= _INSIDE_RATIO_THRESHOLD and centroid_inside:
        return TerritoryCheckResult(
            status="inside_benin",
            risk_level="low",
            is_inside_benin=True,
            message="Le tracé géoréférencé est dans le territoire béninois.",
            **common,
        )
    if intersection_ratio > 0:
        return TerritoryCheckResult(
            status="near_border_partial",
            risk_level="high",
            is_inside_benin=False,
            message=(
                "Le tracé géoréférencé chevauche la frontière béninoise (partiellement hors Bénin). "
                "Vérifiez le CRS, les coordonnées X/Y et la projection."
            ),
            **common,
        )
    return TerritoryCheckResult(
        status="outside_benin",
        risk_level="critical",
        is_inside_benin=False,
        message=_OUTSIDE_MESSAGE,
        **common,
    )
