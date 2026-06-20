import pytest
from fastapi.testclient import TestClient

from app.geometry_engine import validate_polygon
from app.main import app


def test_validate_polygon_accepts_valid_utm_polygon_and_returns_wgs84_coordinates():
    result = validate_polygon(
        [
            [403825.84, 707630.38],
            [403836.57, 707630.38],
            [403836.57, 707626.36],
            [403825.84, 707626.36],
        ],
        "EPSG:32631",
    )

    assert result.valid is True
    assert result.orientation == "xy"
    assert result.self_intersecting is False
    assert result.area_m2 == pytest.approx(43.1346)
    assert result.coordinates is not None
    assert result.coordinates[0] == pytest.approx([2.130353989859776, 6.401151000268496])


def test_validate_polygon_detects_self_intersection():
    result = validate_polygon(
        [
            [2.13, 6.40],
            [2.14, 6.41],
            [2.13, 6.41],
            [2.14, 6.40],
        ],
        "EPSG:4326",
    )

    assert result.valid is False
    assert result.self_intersecting is True
    assert any(issue.code == "self_intersection" for issue in result.issues)


def test_validate_polygon_rejects_degenerate_polygon():
    result = validate_polygon([[2.13, 6.40], [2.13, 6.40], [2.14, 6.40]], "EPSG:4326")

    assert result.valid is False
    assert any(issue.code == "not_enough_points" for issue in result.issues)


def test_validate_polygon_detects_and_normalizes_xy_inversion_for_benin_coordinates():
    result = validate_polygon(
        [
            [6.40, 2.13],
            [6.40, 2.14],
            [6.41, 2.14],
            [6.41, 2.13],
        ],
        "EPSG:4326",
    )

    assert result.valid is True
    assert result.orientation == "yx"
    assert any(issue.code == "xy_inversion_detected" for issue in result.issues)
    assert result.coordinates == [[2.13, 6.4], [2.14, 6.4], [2.14, 6.41], [2.13, 6.41], [2.13, 6.4]]


def test_validate_polygon_endpoint_returns_validation_result():
    client = TestClient(app)

    response = client.post(
        "/api/geometry/validate-polygon",
        json={
            "source_crs": "EPSG:4326",
            "coordinates": [[6.40, 2.13], [6.40, 2.14], [6.41, 2.14], [6.41, 2.13]],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["valid"] is True
    assert payload["orientation"] == "yx"
    assert payload["issues"][0]["code"] == "xy_inversion_detected"
