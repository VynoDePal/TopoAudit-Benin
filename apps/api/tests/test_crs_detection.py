"""Tests du modèle CRS (P0 hardening V2).

Couvre : plan moderne EPSG:32631, plan local ancien, coordonnées inversées X/Y,
CRS absent, et l'interdiction de transformer un CRS non géoréférencé.
"""

import pytest

from app.crs import NonTransformableCRSError, transform_coordinate_to_wgs84
from app.crs_detection import (
    CRSStatus,
    detect_crs,
    detect_crs_from_coordinates,
    detect_crs_from_text,
)

# Coordonnées UTM 31N réelles d'une levée béninoise.
BENIN_UTM = [
    [403825.84, 707630.38],
    [403836.57, 707626.36],
    [403840.12, 707641.10],
    [403829.20, 707645.42],
]


def test_modern_plan_epsg32631_from_text_and_coords():
    result = detect_crs(
        text="Système de projection : UTM zone 31N (WGS84) — EPSG:32631",
        coordinates=BENIN_UTM,
    )
    assert result.status == CRSStatus.EPSG_32631
    assert result.epsg == "EPSG:32631"
    assert result.is_transformable


def test_modern_plan_epsg32631_from_coordinates_only():
    result = detect_crs(coordinates=BENIN_UTM)
    assert result.status == CRSStatus.EPSG_32631
    assert result.is_transformable


def test_utm31_mention_without_epsg_code():
    result = detect_crs_from_text("Projection UTM 31 Nord, datum WGS84")
    assert result.status == CRSStatus.EPSG_32631


def test_old_local_plan_is_local_only():
    local = [[900.0, 2000.0], [9000.0, 1500.0], [8500.0, 9000.0], [1200.0, 8800.0]]
    result = detect_crs(text="Plan ancien, coordonnées relatives, sans projection", coordinates=local)
    assert result.status == CRSStatus.LOCAL_ONLY
    assert result.epsg is None
    assert not result.is_transformable


def test_inverted_xy_flags_needs_georeferencing():
    inverted = [[y, x] for x, y in BENIN_UTM]  # easting / northing intervertis
    result = detect_crs(coordinates=inverted)
    assert result.status == CRSStatus.NEEDS_GEOREFERENCING
    assert not result.is_transformable


def test_absent_crs_is_unknown():
    result = detect_crs(text="", coordinates=None)
    assert result.status == CRSStatus.UNKNOWN_CRS
    assert not result.is_transformable


def test_wgs84_geographic_coordinates():
    geo = [[2.35, 9.31], [2.36, 9.31], [2.36, 9.32], [2.35, 9.32]]
    result = detect_crs(text="Coordonnées géographiques WGS84", coordinates=geo)
    assert result.status == CRSStatus.EPSG_4326
    assert result.is_transformable


def test_coordinates_only_unknown_when_out_of_range():
    weird = [[5_000_000.0, 9_000_000.0], [5_100_000.0, 9_100_000.0]]
    result = detect_crs_from_coordinates(weird)
    assert result.status == CRSStatus.UNKNOWN_CRS


# --- P0 : « WGS84 » seul ne doit JAMAIS donner EPSG_4326 automatiquement ---
def test_wgs84_text_with_utm_coords_is_epsg32631_not_4326():
    result = detect_crs(text="Datum WGS84", coordinates=BENIN_UTM)
    assert result.status == CRSStatus.EPSG_32631


def test_itrf_text_with_utm_coords_is_never_4326():
    result = detect_crs(text="ITRF 2005", coordinates=BENIN_UTM)
    assert result.status == CRSStatus.EPSG_32631
    assert result.status != CRSStatus.EPSG_4326


def test_explicit_geographic_text_with_lonlat_is_epsg4326():
    geo = [[2.35, 9.31], [2.36, 9.31], [2.36, 9.32], [2.35, 9.32]]
    result = detect_crs(text="Coordonnées géographiques WGS84", coordinates=geo)
    assert result.status == CRSStatus.EPSG_4326


def test_wgs84_text_without_coords_is_not_epsg4326():
    result = detect_crs(text="WGS84", coordinates=None)
    assert result.status in (CRSStatus.UNKNOWN_CRS, CRSStatus.NEEDS_GEOREFERENCING)
    assert result.status != CRSStatus.EPSG_4326


def test_bare_wgs84_text_alone_returns_none():
    assert detect_crs_from_text("WGS84") is None
    assert detect_crs_from_text("ITRF 2005") is None


@pytest.mark.parametrize(
    "forbidden",
    [
        CRSStatus.LOCAL_ONLY.value,
        CRSStatus.UNKNOWN_CRS.value,
        CRSStatus.NEEDS_GEOREFERENCING.value,
    ],
)
def test_transform_forbidden_for_non_georeferenced_crs(forbidden):
    with pytest.raises(NonTransformableCRSError):
        transform_coordinate_to_wgs84(403825.84, 707630.38, forbidden)


def test_transform_allowed_for_epsg32631_gives_benin_lonlat():
    lon, lat = transform_coordinate_to_wgs84(403825.84, 707630.38, "EPSG:32631")
    assert 0.5 < lon < 4.5
    assert 6.0 < lat < 13.5


def test_transform_accepts_crs_status_value_for_transformable():
    lon, lat = transform_coordinate_to_wgs84(403825.84, 707630.38, CRSStatus.EPSG_32631.value)
    assert 0.5 < lon < 4.5
    assert 6.0 < lat < 13.5
