from typing import Literal, Sequence

from pydantic import BaseModel, Field
from shapely.geometry import Polygon
from shapely.validation import explain_validity

from app.crs import SUPPORTED_SOURCE_CRS, UTM_31N_CRS, transform_coordinates_to_wgs84

CoordinateXY = Sequence[float]


class GeometryValidationIssue(BaseModel):
    code: str
    message: str


class PolygonValidationResult(BaseModel):
    valid: bool
    orientation: Literal["xy", "yx", "unknown"] = "unknown"
    self_intersecting: bool = False
    area_m2: float | None = None
    issues: list[GeometryValidationIssue] = Field(default_factory=list)
    coordinates: list[list[float]] | None = None


def _is_lon_lat(coordinate: CoordinateXY) -> bool:
    if len(coordinate) != 2:
        return False
    longitude, latitude = coordinate
    return -180 <= float(longitude) <= 180 and -90 <= float(latitude) <= 90


def _looks_like_benin_lon_lat(coordinate: CoordinateXY) -> bool:
    if len(coordinate) != 2:
        return False
    longitude, latitude = coordinate
    return 0 <= float(longitude) <= 4 and 5 <= float(latitude) <= 13


def _detect_orientation(coordinates: Sequence[CoordinateXY], source_crs: str) -> Literal["xy", "yx", "unknown"]:
    if source_crs != "EPSG:4326" or not coordinates:
        return "xy"

    xy_benin_count = sum(1 for coordinate in coordinates if _looks_like_benin_lon_lat(coordinate))
    yx_benin_count = sum(1 for x, y in coordinates if _looks_like_benin_lon_lat((y, x)))
    if yx_benin_count > xy_benin_count and yx_benin_count >= max(1, len(coordinates) - 1):
        return "yx"

    xy_valid_count = sum(1 for coordinate in coordinates if _is_lon_lat(coordinate))
    yx_valid_count = sum(1 for x, y in coordinates if _is_lon_lat((y, x)))
    if yx_valid_count > xy_valid_count:
        return "yx"
    if xy_valid_count == len(coordinates):
        return "xy"
    return "unknown"


def _normalized_ring(coordinates: Sequence[CoordinateXY], orientation: Literal["xy", "yx", "unknown"]) -> list[list[float]]:
    ring: list[list[float]] = []
    for coordinate in coordinates:
        if len(coordinate) != 2:
            raise ValueError("Each polygon coordinate must contain exactly x and y")
        x, y = coordinate
        if orientation == "yx":
            ring.append([float(y), float(x)])
        else:
            ring.append([float(x), float(y)])

    if ring and ring[0] != ring[-1]:
        ring.append(ring[0].copy())
    return ring


def validate_polygon(
    coordinates: Sequence[CoordinateXY],
    source_crs: SUPPORTED_SOURCE_CRS = UTM_31N_CRS,
) -> PolygonValidationResult:
    issues: list[GeometryValidationIssue] = []

    try:
        orientation = _detect_orientation(coordinates, source_crs)
        ring = _normalized_ring(coordinates, orientation)
    except ValueError as exc:
        return PolygonValidationResult(
            valid=False,
            issues=[GeometryValidationIssue(code="invalid_coordinate", message=str(exc))],
        )

    unique_points = {tuple(point) for point in ring[:-1]}
    if len(unique_points) < 3:
        return PolygonValidationResult(
            valid=False,
            orientation=orientation,
            issues=[GeometryValidationIssue(code="not_enough_points", message="A polygon requires at least three distinct points")],
            coordinates=ring,
        )

    polygon = Polygon(ring)
    if polygon.is_empty or polygon.area == 0:
        issues.append(GeometryValidationIssue(code="zero_area", message="Polygon area must be greater than zero"))

    validity_reason = explain_validity(polygon)
    self_intersecting = validity_reason.startswith("Self-intersection")
    if not polygon.is_valid:
        code = "self_intersection" if self_intersecting else "invalid_polygon"
        issues.append(GeometryValidationIssue(code=code, message=validity_reason))

    if orientation == "yx":
        issues.append(
            GeometryValidationIssue(
                code="xy_inversion_detected",
                message="Coordinates appear to be latitude/longitude and were normalized to longitude/latitude",
            )
        )
    elif orientation == "unknown":
        issues.append(GeometryValidationIssue(code="unknown_orientation", message="Coordinate orientation could not be determined"))

    output_coordinates = ring
    area_m2: float | None = polygon.area if source_crs == UTM_31N_CRS else None
    if source_crs == UTM_31N_CRS:
        output_coordinates = transform_coordinates_to_wgs84(ring, source_crs)

    return PolygonValidationResult(
        valid=not any(issue.code not in {"xy_inversion_detected"} for issue in issues),
        orientation=orientation,
        self_intersecting=self_intersecting,
        area_m2=area_m2,
        issues=issues,
        coordinates=output_coordinates,
    )
