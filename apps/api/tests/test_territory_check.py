from fastapi.testclient import TestClient
from pyproj import Transformer

from app.main import app
from app.territory_check import is_transformable_crs, load_benin_boundary, validate_benin_territory

# Transforme des lon/lat (WGS84) en UTM 31N pour fabriquer des cas « UTM » contrôlés.
_TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32631", always_xy=True)


def _square_lonlat(lon: float, lat: float, d: float = 0.01) -> list[list[float]]:
    return [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d]]


def _square_utm(lon: float, lat: float, d: float = 0.01) -> list[list[float]]:
    return [list(_TO_UTM.transform(x, y)) for x, y in _square_lonlat(lon, lat, d)]


def test_benin_boundary_loads_valid():
    geom = load_benin_boundary()
    assert geom.is_valid and not geom.is_empty
    # Centroïde du Bénin ~ (2.3°E, 9.6°N).
    assert 1.5 < geom.centroid.x < 3.0 and 8.5 < geom.centroid.y < 10.5


def test_is_transformable_crs():
    assert is_transformable_crs("EPSG:32631") and is_transformable_crs("EPSG_32631")
    assert is_transformable_crs("EPSG:4326") and is_transformable_crs("EPSG_4326")
    assert not is_transformable_crs("LOCAL_ONLY")
    assert not is_transformable_crs("UNKNOWN_CRS")
    assert not is_transformable_crs("NEEDS_GEOREFERENCING")


def test_parcel_utm_benin_plausible_inside():
    # 1. Parcelle UTM 31N au centre du Bénin → inside_benin.
    result = validate_benin_territory(_square_utm(2.35, 9.5), "EPSG:32631")
    assert result.status == "inside_benin"
    assert result.risk_level == "low"
    assert result.is_inside_benin is True
    assert result.intersection_ratio is not None and result.intersection_ratio >= 0.95


def test_parcel_utm_transformed_outside_benin():
    # 2. Parcelle UTM 31N (Paris) → hors Bénin, risque critique.
    result = validate_benin_territory(_square_utm(2.35, 48.85), "EPSG:32631")
    assert result.status == "outside_benin"
    assert result.risk_level == "critical"
    assert result.is_inside_benin is False
    assert result.intersection_ratio == 0.0


def test_parcel_in_ocean_outside_benin():
    # 3. Parcelle dans le golfe de Guinée (lat 4°N) → hors Bénin.
    result = validate_benin_territory(_square_lonlat(2.35, 4.0), "EPSG:4326")
    assert result.status == "outside_benin"
    assert result.risk_level == "critical"


def test_local_only_not_applicable():
    # 4. CRS LOCAL_ONLY → contrôle non applicable (jamais classé faux levé).
    result = validate_benin_territory([[100, 100], [200, 100], [200, 200]], "LOCAL_ONLY")
    assert result.status == "not_applicable_local_crs"
    assert result.risk_level == "not_applicable"
    assert result.is_inside_benin is None
    assert "impossible" in result.message.lower()


def test_unknown_crs_not_applicable():
    # 5. UNKNOWN_CRS → contrôle non applicable.
    result = validate_benin_territory([[100, 100], [200, 100], [200, 200]], "UNKNOWN_CRS")
    assert result.status == "not_applicable_local_crs"
    assert result.risk_level == "not_applicable"


def test_invalid_geometry_too_few_points():
    # 6. Moins de 3 bornes → géométrie invalide.
    result = validate_benin_territory([[2.35, 9.5], [2.36, 9.5]], "EPSG:4326")
    assert result.status == "invalid_geometry"
    assert result.risk_level == "high"


def test_endpoint_territory_check_returns_status():
    # 7. L'endpoint renvoie le bon status.
    client = TestClient(app)
    inside = client.post(
        "/api/territory/benin/check",
        json={"source_crs": "EPSG:32631", "coordinates": _square_utm(2.35, 9.5)},
    )
    assert inside.status_code == 200
    assert inside.json()["status"] == "inside_benin"

    outside = client.post(
        "/api/territory/benin/check",
        json={"source_crs": "EPSG:32631", "coordinates": _square_utm(2.35, 48.85)},
    )
    assert outside.status_code == 200
    assert outside.json()["status"] == "outside_benin"
    assert outside.json()["risk_level"] == "critical"

    local = client.post(
        "/api/territory/benin/check",
        json={"source_crs": "LOCAL_ONLY", "coordinates": [[1, 1], [2, 1], [2, 2]]},
    )
    assert local.json()["status"] == "not_applicable_local_crs"
