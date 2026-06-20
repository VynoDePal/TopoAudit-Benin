export const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
export const crsOptions = ["EPSG:32631", "EPSG:4326"] as const;

export type SupportedCrs = (typeof crsOptions)[number];

export type CoordinatePoint = {
  label: string;
  x: string;
  y: string;
  confidence: number;
};

export type GeometryIssue = { code: string; message: string };

export type GeometryResult = {
  valid: boolean;
  orientation: "xy" | "yx" | "unknown";
  self_intersecting: boolean;
  area_m2: number | null;
  issues: GeometryIssue[];
  coordinates: number[][] | null;
};

export type SurfaceRiskResult = {
  risk_level: "low" | "moderate" | "high";
  surface_deviation_m2: number;
  surface_deviation_percent: number;
};

export const initialPoints: CoordinatePoint[] = [
  { label: "B1", x: "403825.84", y: "707630.38", confidence: 0.94 },
  { label: "B2", x: "403836.57", y: "707626.36", confidence: 0.92 },
  { label: "B3", x: "403830.47", y: "707610.52", confidence: 0.89 },
  { label: "B4", x: "403827.18", y: "707601.32", confidence: 0.87 },
  { label: "B5", x: "403799.28", y: "707612.51", confidence: 0.9 }
];

export const FORM_DIRTY_MESSAGE = "Modification détectée : confirmez à nouveau avant le calcul géométrique.";

export const confidenceTone = (confidence: number) => {
  if (confidence >= 0.9) return "good";
  if (confidence >= 0.8) return "warning";
  return "danger";
};

export const toNumber = (value: string) => Number(value.replace(",", "."));

export const buildParcelFeature = (coordinates: number[][]): GeoJSON.FeatureCollection<GeoJSON.Polygon> => ({
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Parcelle validée", risk: "Faible" },
      geometry: { type: "Polygon", coordinates: [coordinates] }
    }
  ]
});

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}
