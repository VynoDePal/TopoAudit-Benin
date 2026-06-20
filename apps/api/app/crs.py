from functools import lru_cache
from typing import Literal, Sequence, cast

from pyproj import Transformer

SUPPORTED_SOURCE_CRS = Literal["EPSG:32631", "EPSG:4326"]
GEOJSON_CRS = "EPSG:4326"
UTM_31N_CRS = "EPSG:32631"


@lru_cache(maxsize=4)
def _transformer(source_crs: str, target_crs: str) -> Transformer:
    return Transformer.from_crs(source_crs, target_crs, always_xy=True)


def transform_coordinate_to_wgs84(
    x: float,
    y: float,
    source_crs: SUPPORTED_SOURCE_CRS = UTM_31N_CRS,
) -> list[float]:
    """Return a GeoJSON-ready [longitude, latitude] coordinate in EPSG:4326."""
    if source_crs == GEOJSON_CRS:
        return [float(x), float(y)]
    if source_crs != UTM_31N_CRS:
        raise ValueError(f"Unsupported source CRS: {source_crs}")

    longitude, latitude = _transformer(source_crs, GEOJSON_CRS).transform(float(x), float(y))
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
