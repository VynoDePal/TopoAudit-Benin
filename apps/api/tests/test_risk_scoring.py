import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.risk_scoring import score_surface_deviation


def test_score_surface_deviation_low_when_absolute_delta_is_at_most_two_m2():
    result = score_surface_deviation(549, 551)

    assert result.risk_level == "low"
    assert result.surface_deviation_m2 == 2
    assert result.surface_deviation_percent == pytest.approx(0.3643, rel=1e-3)


def test_score_surface_deviation_moderate_when_delta_is_at_most_five_percent():
    result = score_surface_deviation(1000, 1049)

    assert result.risk_level == "moderate"
    assert result.surface_deviation_m2 == 49
    assert result.surface_deviation_percent == pytest.approx(4.9)


def test_score_surface_deviation_high_when_delta_exceeds_five_percent():
    result = score_surface_deviation(1000, 1051)

    assert result.risk_level == "high"
    assert result.surface_deviation_m2 == 51
    assert result.surface_deviation_percent == pytest.approx(5.1)


def test_score_surface_deviation_rejects_invalid_declared_surface():
    with pytest.raises(ValueError, match="Declared surface"):
        score_surface_deviation(0, 10)


def test_score_surface_endpoint_returns_risk_score():
    client = TestClient(app)

    response = client.post(
        "/api/risk/score-surface",
        json={"declared_surface_m2": 1000, "calculated_surface_m2": 1049},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] == "moderate"
    assert payload["surface_deviation_m2"] == 49
    assert payload["surface_deviation_percent"] == pytest.approx(4.9)
