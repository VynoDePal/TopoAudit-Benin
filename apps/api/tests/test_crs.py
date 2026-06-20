import pytest

from fastapi.testclient import TestClient

from app.main import app

from app.crs import transform_coordinate_to_wgs84, transform_coordinates_to_wgs84


def test_epsg_32631_coordinate_transforms_to_epsg_4326_lon_lat():
    coordinate = transform_coordinate_to_wgs84(403825.84, 707630.38, "EPSG:32631")

    assert coordinate == pytest.approx([2.130353989859776, 6.401151000268496])


def test_epsg_32631_coordinates_transform_to_geojson_lon_lat_order():
    coordinates = transform_coordinates_to_wgs84(
        [(403825.84, 707630.38), (403836.57, 707626.36)],
        "EPSG:32631",
    )

    assert coordinates[0] == pytest.approx([2.130353989859776, 6.401151000268496])
    assert coordinates[1][0] == pytest.approx(2.1304506262855257)
    assert coordinates[1][1] == pytest.approx(6.401114950042085)


def test_crs_transform_endpoint_returns_epsg_4326_lon_lat_coordinates():
    client = TestClient(app)

    response = client.post(
        "/api/crs/transform",
        json={"source_crs": "EPSG:32631", "coordinates": [[403825.84, 707630.38]]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_crs"] == "EPSG:32631"
    assert payload["target_crs"] == "EPSG:4326"
    assert payload["coordinates"][0] == pytest.approx([2.130353989859776, 6.401151000268496])


def test_crs_transform_endpoint_rejects_non_xy_coordinates():
    client = TestClient(app)

    response = client.post(
        "/api/crs/transform",
        json={"source_crs": "EPSG:32631", "coordinates": [[403825.84, 707630.38, 1.0]]},
    )

    assert response.status_code == 422



def test_epsg_4326_coordinate_is_already_geojson_lon_lat():
    assert transform_coordinate_to_wgs84(2.13, 6.4, "EPSG:4326") == [2.13, 6.4]


def test_unsupported_source_crs_raises_value_error():
    with pytest.raises(ValueError, match="Unsupported source CRS"):
        transform_coordinate_to_wgs84(1, 2, "local_non_georef")
