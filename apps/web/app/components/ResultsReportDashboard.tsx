"use client";

import { useEffect, useMemo, useState } from "react";
import ParcelMap from "./ParcelMap";
import { apiBaseUrl, postJson } from "./ocrValidationShared";

type RiskLevel = "low" | "moderate" | "high";

type AuditResult = {
  project_id: string;
  state: string;
  audit_id: string;
  extraction_score: number;
  technical_score: number;
  risk_level: RiskLevel | string;
  warnings: string[];
};

const demoAudit: AuditResult = {
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

const dashboardParcels: GeoJSON.FeatureCollection<GeoJSON.Polygon> = {
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

const riskLabels: Record<string, string> = {
  low: "Faible",
  moderate: "Modéré",
  high: "Élevé"
};

function scoreTone(score: number) {
  if (score >= 85) return "good";
  if (score >= 65) return "warning";
  return "danger";
}

function riskTone(riskLevel: string) {
  if (riskLevel === "low") return "good";
  if (riskLevel === "moderate") return "warning";
  return "danger";
}

function ScoreCard({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <div className="dashboard-score-card">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

export default function ResultsReportDashboard() {
  const [projectId, setProjectId] = useState(demoAudit.project_id);
  const [audit, setAudit] = useState<AuditResult>(demoAudit);
  const [reportUrl, setReportUrl] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState("Aperçu chargé avec des données de démonstration réutilisables.");
  const [isRunningAudit, setIsRunningAudit] = useState(false);
  const [isPreparingReport, setIsPreparingReport] = useState(false);

  useEffect(() => {
    return () => {
      if (reportUrl) {
        URL.revokeObjectURL(reportUrl);
      }
    };
  }, [reportUrl]);

  const normalizedRisk = audit.risk_level.toLowerCase();
  const riskLabel = riskLabels[normalizedRisk] ?? audit.risk_level;
  const projectIdReady = projectId.trim().length > 0;

  const reportFilename = useMemo(() => `topoaudit-${audit.project_id}-report.pdf`, [audit.project_id]);

  const runAudit = async () => {
    if (!projectIdReady) {
      setStatusMessage("Indiquez un identifiant de projet validé avant de lancer l’audit.");
      return;
    }

    setIsRunningAudit(true);
    setStatusMessage("Calcul des scores d’audit en cours…");
    setReportUrl(null);

    try {
      const result = await postJson<AuditResult>(`/projects/${encodeURIComponent(projectId.trim())}/audit`, {});
      setAudit(result);
      setStatusMessage("Scores de risque mis à jour depuis l’API d’audit.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Impossible de lancer l’audit du projet.");
    } finally {
      setIsRunningAudit(false);
    }
  };

  const prepareReport = async () => {
    if (!projectIdReady) {
      setStatusMessage("Indiquez un identifiant de projet avant de préparer le PDF.");
      return;
    }

    setIsPreparingReport(true);
    setStatusMessage("Préparation du rapport PDF…");

    try {
      const response = await fetch(`${apiBaseUrl}/projects/${encodeURIComponent(projectId.trim())}/audit/report.pdf`, {
        method: "POST"
      });

      if (!response.ok) {
        const detail = await response.text();
        throw new Error(detail || `Request failed with ${response.status}`);
      }

      if (reportUrl) {
        URL.revokeObjectURL(reportUrl);
      }
      const blobUrl = URL.createObjectURL(await response.blob());
      setReportUrl(blobUrl);
      setStatusMessage("Rapport PDF prêt : utilisez le lien de téléchargement ci-dessous.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Impossible de préparer le rapport PDF.");
    } finally {
      setIsPreparingReport(false);
    }
  };

  return (
    <section className="dashboard-panel" aria-labelledby="results-dashboard-title">
      <div className="validation-header">
        <div>
          <p className="eyebrow">Résultats & rapport</p>
          <h2 id="results-dashboard-title">Dashboard des risques et rapport PDF</h2>
          <p>
            Consultez les scores issus de l’audit, visualisez la parcelle sur la carte MapLibre existante,
            puis préparez le rapport PDF généré par le backend.
          </p>
        </div>
        <div className={`status-pill ${riskTone(normalizedRisk)}`}>Risque {riskLabel}</div>
      </div>

      <div className="dashboard-toolbar">
        <label>
          Projet audité
          <input value={projectId} onChange={(event) => setProjectId(event.target.value)} placeholder="project-id" />
        </label>
        <button type="button" onClick={runAudit} disabled={!projectIdReady || isRunningAudit}>
          {isRunningAudit ? "Audit…" : "Mettre à jour les scores"}
        </button>
        <button type="button" className="ghost-button" onClick={prepareReport} disabled={!projectIdReady || isPreparingReport}>
          {isPreparingReport ? "PDF…" : "Préparer le PDF"}
        </button>
      </div>

      <div className="dashboard-score-grid" aria-label="Scores de risque">
        <ScoreCard label="Score OCR" value={`${audit.extraction_score}/100`} tone={scoreTone(audit.extraction_score)} />
        <ScoreCard label="Score technique" value={`${audit.technical_score}/100`} tone={scoreTone(audit.technical_score)} />
        <ScoreCard label="Niveau de risque" value={riskLabel} tone={riskTone(normalizedRisk)} />
        <ScoreCard label="Workflow" value={audit.state} tone={audit.state === "AUDITED" ? "good" : "warning"} />
      </div>

      <div className="dashboard-details">
        <div>
          <span>Identifiant audit</span>
          <strong>{audit.audit_id}</strong>
        </div>
        <div>
          <span>Projet</span>
          <strong>{audit.project_id}</strong>
        </div>
      </div>

      <div className="warning-list" aria-label="Alertes d’audit">
        {audit.warnings.map((warning) => <p key={warning}>{warning}</p>)}
      </div>

      <p className="status-message" role="status">{statusMessage}</p>

      {reportUrl && (
        <a className="download-link" href={reportUrl} download={reportFilename}>
          Télécharger le rapport PDF
        </a>
      )}

      <ParcelMap
        parcels={dashboardParcels}
        title="Carte de synthèse de la parcelle auditée"
        description="Le dashboard réutilise le composant MapLibre existant pour afficher la géométrie GeoJSON normalisée en EPSG:4326."
      />
    </section>
  );
}
