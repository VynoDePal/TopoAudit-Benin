from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_returns_status_ok():
    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_is_exposed_under_api_prefix():
    client = TestClient(app)

    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "TopoAudit Benin"
