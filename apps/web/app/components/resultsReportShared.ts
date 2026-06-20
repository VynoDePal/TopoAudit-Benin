import type { FeatureCollection, Polygon } from "geojson";

export type RiskLevel = "low" | "moderate" | "high";

export type AuditResult = {
  project_id: string;
  state: string;
  audit_id: string;
  extraction_score: number;
  technical_score: number;
  risk_level: RiskLevel | string;
  warnings: string[];
};

export const demoAudit: AuditResult = {
  project_id: "demo-cotonou-001",
  state: "AUDITED",
  audit_id: "aperçu-local",
  extraction_score: 87,
  technical_score: 74,
  risk_level: "moderate",
  warnings: [
    "Aucune comparaison cadastrale officielle effectuée.",
    "Écart modéré entre surface déclarée et surface calculée."
  ]
};

export const dashboardParcels: FeatureCollection<Polygon> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Parcelle auditée", risk: "Modéré" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [2.62058, 6.38404],
            [2.62174, 6.38408],
            [2.6217, 6.38506],
            [2.62054, 6.38501],
            [2.62058, 6.38404]
          ]
        ]
      }
    }
  ]
};

export const riskLabels: Record<string, string> = {
  low: "Faible",
  moderate: "Modéré",
  high: "Élevé"
};

export function scoreTone(score: number) {
  if (score >= 85) return "good";
  if (score >= 65) return "warning";
  return "danger";
}

export function riskTone(riskLevel: string) {
  if (riskLevel === "low") return "good";
  if (riskLevel === "moderate") return "warning";
  return "danger";
}

export const reportFilename = (projectId: string) => `topoaudit-${projectId}-report.pdf`;
