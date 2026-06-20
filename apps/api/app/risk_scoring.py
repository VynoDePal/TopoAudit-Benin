from typing import Literal

from pydantic import BaseModel

RiskLevel = Literal["low", "moderate", "high"]


class SurfaceRiskScore(BaseModel):
    risk_level: RiskLevel
    declared_surface_m2: float
    calculated_surface_m2: float
    surface_deviation_m2: float
    surface_deviation_percent: float


def score_surface_deviation(declared_surface_m2: float, calculated_surface_m2: float) -> SurfaceRiskScore:
    """Score risk from absolute and relative surface deviation."""
    if declared_surface_m2 <= 0:
        raise ValueError("Declared surface must be greater than zero")
    if calculated_surface_m2 < 0:
        raise ValueError("Calculated surface must be greater than or equal to zero")

    deviation_m2 = abs(calculated_surface_m2 - declared_surface_m2)
    deviation_percent = deviation_m2 / declared_surface_m2 * 100

    # Spec : faible si écart ≤ 1 % OU ≤ 2 m² (le « OU ≤ 1 % » manquait → une GRANDE
    # parcelle avec un écart absolu > 2 m² mais négligeable en % était classée modérée).
    if deviation_m2 <= 2 or deviation_percent <= 1:
        risk_level: RiskLevel = "low"
    elif deviation_percent <= 5:
        risk_level = "moderate"
    else:
        risk_level = "high"

    return SurfaceRiskScore(
        risk_level=risk_level,
        declared_surface_m2=float(declared_surface_m2),
        calculated_surface_m2=float(calculated_surface_m2),
        surface_deviation_m2=deviation_m2,
        surface_deviation_percent=deviation_percent,
    )
