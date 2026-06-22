from functools import lru_cache
from typing import Literal, Sequence, cast

from pyproj import Transformer

from app.crs_detection import CRSStatus

SUPPORTED_SOURCE_CRS = Literal["EPSG:32631", "EPSG:4326"]
GEOJSON_CRS = "EPSG:4326"
UTM_31N_CRS = "EPSG:32631"


class NonTransformableCRSError(ValueError):
    """Le CRS source n'est pas géoréférencé : transformation vers WGS84 interdite."""


# Statuts CRS interdits à la transformation (coordonnées non géoréférencées).
_FORBIDDEN_STATUS = {
    CRSStatus.LOCAL_ONLY.value: "coordonnées locales uniquement (LOCAL_ONLY)",
    CRSStatus.UNKNOWN_CRS.value: "CRS inconnu (UNKNOWN_CRS)",
    CRSStatus.NEEDS_GEOREFERENCING.value: "géoréférencement requis (NEEDS_GEOREFERENCING)",
}
# Statuts CRS transformables → EPSG correspondant.
_STATUS_TO_EPSG = {
    CRSStatus.EPSG_32631.value: UTM_31N_CRS,
    CRSStatus.EPSG_4326.value: GEOJSON_CRS,
}


def _normalize_source_crs(source_crs: str) -> str:
    """Convertit un statut/EPSG en EPSG transformable, ou lève si non transformable."""
    value = str(source_crs)
    if value in _FORBIDDEN_STATUS:
        raise NonTransformableCRSError(
            f"Transformation vers WGS84 interdite : {_FORBIDDEN_STATUS[value]}"
        )
    return _STATUS_TO_EPSG.get(value, value)


@lru_cache(maxsize=4)
def _transformer(source_crs: str, target_crs: str) -> Transformer:
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def transform_coordinate_to_wgs84(
    x: float,
    y: float,
    source_crs: SUPPORTED_SOURCE_CRS = UTM_31N_CRS,
) -> list[float]:
    """Return a GeoJSON-ready [longitude, latitude] coordinate in EPSG:4326.

    Lève ``NonTransformableCRSError`` si le CRS source n'est pas géoréférencé
    (LOCAL_ONLY, UNKNOWN_CRS, NEEDS_GEOREFERENCING).
    """
    crs = _normalize_source_crs(source_crs)
    if crs == GEOJSON_CRS:
        return [float(x), float(y)]
    if crs != UTM_31N_CRS:
        raise NonTransformableCRSError(f"Unsupported source CRS: {source_crs}")

    longitude, latitude = _transformer(crs, GEOJSON_CRS).transform(float(x), float(y))
    return [longitude, latitude]


def transform_coordinates_to_wgs84(
    coordinates: Sequence[Sequence[float]],
    source_crs: SUPPORTED_SOURCE_CRS = UTM_31N_CRS,
) -> list[list[float]]:
    transformed: list[list[float]] = []
    for coordinate in coordinates:
        if len(coordinate) != 2:
            raise ValueError("Each coordinate must contain exactly x and y")
        x, y = coordinate
        transformed.append(transform_coordinate_to_wgs84(x, y, cast(SUPPORTED_SOURCE_CRS, source_crs)))
    return transformed
