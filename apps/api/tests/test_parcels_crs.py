"""PUT /parcels : la persistance des corrections humaines respecte le CRS (P0.2).

Un CRS local/inconnu ne doit PAS être transformé vers WGS84 (geom NULL) ; seuls les
CRS géoréférencés produisent une géométrie WGS84.
"""

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app


class FakeResult:
    def __init__(self, row=None, rows=None):
        self.row = row
        self.rows = rows or []

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self.rows


class FakeParcelSession:
    def __init__(self):
        self.survey: list[tuple[str, dict]] = []
        self.parcels: list[dict] = []

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "FROM projects" in sql:
            return FakeResult({"id": params.get("project_id"), "owner_id": None, "status": "OCR_EXTRACTED"})
        if "INSERT INTO survey_points" in sql:
            self.survey.append((sql, params))
            return FakeResult(None)
        if "INSERT INTO parcels" in sql:
            self.parcels.append(params)
            return FakeResult(None)
        if "FROM parcels p" in sql:
            return FakeResult(rows=[])
        return FakeResult(None)

    def commit(self):
        pass


def _client(session):
    def _override():
        yield session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_put_parcels_local_only_keeps_geom_null_no_transform():
    session = FakeParcelSession()
    client = _client(session)
    resp = client.put(
        "/api/projects/p1/parcels",
        json={
            "parcels": [
                {
                    "label": "A",
                    "declared_surface_m2": 230,
                    "detected_crs": "LOCAL_ONLY",
                    "points": [{"label": "B1", "x": 900, "y": 2000, "confidence": 0}],
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert len(session.survey) == 1
    sql, params = session.survey[0]
    # Pas de transformation : geom NULL, aucune coordonnée WGS84 fabriquée.
    assert "NULL" in sql and "ST_MakePoint" not in sql
    assert "lon" not in params and "lat" not in params


def test_put_parcels_epsg32631_transforms_to_wgs84():
    session = FakeParcelSession()
    client = _client(session)
    resp = client.put(
        "/api/projects/p1/parcels",
        json={
            "parcels": [
                {
                    "label": "A",
                    "declared_surface_m2": 549,
                    "detected_crs": "EPSG:32631",
                    "points": [{"label": "B1", "x": 403825.84, "y": 707630.38, "confidence": 0.9}],
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert len(session.survey) == 1
    sql, params = session.survey[0]
    assert "ST_MakePoint" in sql
    assert 0.5 < params["lon"] < 4.5
    assert 6.0 < params["lat"] < 13.5
