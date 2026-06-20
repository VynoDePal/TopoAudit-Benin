"use client";

import { useMemo, useState } from "react";
import ParcelMap from "./ParcelMap";
import {
  FORM_DIRTY_MESSAGE,
  buildParcelFeature,
  confidenceTone,
  crsOptions,
  initialPoints,
  postJson,
  toNumber,
  type CoordinatePoint,
  type GeometryResult,
  type SurfaceRiskResult,
  type SupportedCrs
} from "./ocrValidationShared";

function EditableCell({
  label,
  value,
  onChange,
  inputMode = "text"
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  inputMode?: "text" | "decimal";
}) {
  return (
    <label className="sr-cell-label">
      <span className="sr-only">{label}</span>
      <input value={value} inputMode={inputMode} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="result-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function OcrValidationInterface() {
  const [points, setPoints] = useState(initialPoints);
  const [declaredSurfaceRaw, setDeclaredSurfaceRaw] = useState("05a 49ca");
  const [declaredSurfaceM2, setDeclaredSurfaceM2] = useState("549");
  const [crs, setCrs] = useState<SupportedCrs>("EPSG:32631");
  const [confirmed, setConfirmed] = useState(false);
  const [geometry, setGeometry] = useState<GeometryResult | null>(null);
  const [surfaceRisk, setSurfaceRisk] = useState<SurfaceRiskResult | null>(null);
  const [statusMessage, setStatusMessage] = useState("Corrigez les champs OCR puis confirmez les coordonnées.");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const numericCoordinates = useMemo(() => points.map((point) => [toNumber(point.x), toNumber(point.y)]), [points]);
  const hasInvalidCoordinate = numericCoordinates.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y));
  const declaredSurface = toNumber(declaredSurfaceM2);
  const mapData = geometry?.valid && geometry.coordinates ? buildParcelFeature(geometry.coordinates) : undefined;

  const invalidateConfirmation = (message = FORM_DIRTY_MESSAGE) => {
    setConfirmed(false);
    setGeometry(null);
    setSurfaceRisk(null);
    setStatusMessage(message);
  };

  const updatePoints = (updater: (current: CoordinatePoint[]) => CoordinatePoint[]) => {
    setPoints((current) => updater(current));
    invalidateConfirmation();
  };

  const updatePoint = (index: number, field: keyof Pick<CoordinatePoint, "label" | "x" | "y">, value: string) => {
    updatePoints((current) => current.map((point, currentIndex) => (currentIndex === index ? { ...point, [field]: value } : point)));
  };

  const addPoint = () => {
    updatePoints((current) => [...current, { label: `B${current.length + 1}`, x: "", y: "", confidence: 0 }]);
  };

  const removePoint = (index: number) => {
    updatePoints((current) => current.filter((_, currentIndex) => currentIndex !== index));
  };

  const updateCrs = (value: SupportedCrs) => {
    setCrs(value);
    invalidateConfirmation();
  };

  const confirmCoordinates = () => {
    if (points.length < 3 || hasInvalidCoordinate || !Number.isFinite(declaredSurface) || declaredSurface <= 0) {
      setStatusMessage("Renseignez au moins trois coordonnées valides et une surface déclarée positive.");
      return;
    }

    setConfirmed(true);
    setStatusMessage("Coordonnées confirmées. Le calcul géométrique peut être lancé.");
  };

  const calculateGeometry = async () => {
    if (!confirmed) {
      setStatusMessage("Confirmez les coordonnées corrigées avant de lancer le calcul.");
      return;
    }

    setIsSubmitting(true);
    setStatusMessage("Calcul géométrique en cours…");
    try {
      const geometryResult = await postJson<GeometryResult>("/geometry/validate-polygon", {
        source_crs: crs,
        coordinates: numericCoordinates
      });
      setGeometry(geometryResult);

      if (geometryResult.area_m2 !== null) {
        setSurfaceRisk(
          await postJson<SurfaceRiskResult>("/risk/score-surface", {
            declared_surface_m2: declaredSurface,
            calculated_surface_m2: geometryResult.area_m2
          })
        );
      } else {
        setSurfaceRisk(null);
      }

      setStatusMessage(geometryResult.valid ? "Calcul terminé : géométrie exploitable." : "Calcul terminé avec anomalies à corriger.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Impossible de calculer la géométrie.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <section className="validation-panel" aria-labelledby="ocr-validation-title">
      <div className="validation-header">
        <div>
          <p className="eyebrow">Validation OCR humaine</p>
          <h2 id="ocr-validation-title">Coordonnées et surface modifiables avant calcul</h2>
          <p>
            Les valeurs ci-dessous simulent une extraction OCR : l’utilisateur corrige les bornes, confirme le CRS,
            puis déclenche explicitement le moteur géométrique existant.
          </p>
        </div>
        <div className={`status-pill ${confirmed ? "status-ok" : "status-waiting"}`}>{confirmed ? "Confirmé" : "À valider"}</div>
      </div>

      <div className="form-grid">
        <label>
          Surface OCR brute
          <input value={declaredSurfaceRaw} onChange={(event) => setDeclaredSurfaceRaw(event.target.value)} />
        </label>
        <label>
          Surface déclarée (m²)
          <input value={declaredSurfaceM2} inputMode="decimal" onChange={(event) => setDeclaredSurfaceM2(event.target.value)} />
        </label>
        <label>
          Système de coordonnées
          <select value={crs} onChange={(event) => updateCrs(event.target.value as SupportedCrs)}>
            {crsOptions.map((option) => <option key={option}>{option}</option>)}
          </select>
        </label>
      </div>

      <div className="table-wrap">
        <table className="coordinate-table">
          <thead>
            <tr>
              {["Borne", "X / longitude", "Y / latitude", "Confiance OCR", "Actions"].map((heading) => <th key={heading}>{heading}</th>)}
            </tr>
          </thead>
          <tbody>
            {points.map((point, index) => (
              <tr key={`${point.label}-${index}`}>
                <td><EditableCell label={`Libellé borne ${index + 1}`} value={point.label} onChange={(value) => updatePoint(index, "label", value)} /></td>
                <td><EditableCell label={`Coordonnée X ${point.label}`} value={point.x} inputMode="decimal" onChange={(value) => updatePoint(index, "x", value)} /></td>
                <td><EditableCell label={`Coordonnée Y ${point.label}`} value={point.y} inputMode="decimal" onChange={(value) => updatePoint(index, "y", value)} /></td>
                <td><span className={`confidence ${confidenceTone(point.confidence)}`}>{Math.round(point.confidence * 100)}%</span></td>
                <td><button type="button" className="ghost-button" onClick={() => removePoint(index)} disabled={points.length <= 3}>Retirer</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="actions-row">
        <button type="button" className="ghost-button" onClick={addPoint}>Ajouter une borne</button>
        <button type="button" onClick={confirmCoordinates}>Confirmer les coordonnées</button>
        <button type="button" onClick={calculateGeometry} disabled={!confirmed || isSubmitting}>{isSubmitting ? "Calcul…" : "Calculer la géométrie"}</button>
      </div>

      <p className="status-message" role="status">{statusMessage}</p>

      <div className="warning-list" aria-label="Avertissements OCR">
        {crs === "EPSG:4326" && <p>Vérifiez l’ordre [longitude, latitude] : le moteur signale et normalise les inversions probables.</p>}
        {geometry?.orientation === "unknown" && <p>Orientation incertaine : contrôlez les colonnes X/Y avant audit.</p>}
        {geometry?.issues.map((issue) => <p key={`${issue.code}-${issue.message}`}>{issue.message}</p>)}
      </div>

      {geometry && (
        <div className="result-grid" aria-label="Résultats géométriques">
          <ResultMetric label="Validité" value={geometry.valid ? "Valide" : "À corriger"} />
          <ResultMetric label="Surface calculée" value={geometry.area_m2 === null ? "Non géoréférencée" : `${geometry.area_m2.toFixed(2)} m²`} />
          <ResultMetric label="Écart surface" value={surfaceRisk ? `${surfaceRisk.surface_deviation_m2.toFixed(2)} m² (${surfaceRisk.surface_deviation_percent.toFixed(2)}%)` : "Indisponible"} />
          <ResultMetric label="Risque surface" value={surfaceRisk?.risk_level ?? "Non calculé"} />
        </div>
      )}

      <ParcelMap
        parcels={mapData}
        title="Aperçu de la parcelle validée"
        description="La carte réutilise MapLibre avec les coordonnées normalisées retournées par l’API de validation géométrique."
      />
    </section>
  );
}
