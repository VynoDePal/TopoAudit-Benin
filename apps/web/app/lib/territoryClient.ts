// Contrôle territorial Bénin (frontend) : appel API + rendu du badge.
// NON juridique : « hors Bénin » = probablement mal géoréférencé/projeté, jamais « fraude ».

export type TerritoryStatus =
  | "inside_benin"
  | "outside_benin"
  | "near_border_partial"
  | "not_applicable_local_crs"
  | "invalid_geometry"
  | "unknown";

export type TerritoryResult = {
  status: TerritoryStatus | string;
  risk_level: string;
  is_inside_benin: boolean | null;
  centroid_lon: number | null;
  centroid_lat: number | null;
  intersection_ratio: number | null;
  points_outside_count: number | null;
  message: string;
};

export type TerritoryTone = "ok" | "critical" | "warn" | "neutral";

// Badge à afficher (libellé + tonalité de couleur) selon le statut.
export function territoryBadge(status: string, lang: "fr" | "en" = "fr"): { label: string; tone: TerritoryTone } {
  switch (status) {
    case "inside_benin":
      return { label: lang === "fr" ? "OK — dans le territoire béninois" : "OK — inside Benin", tone: "ok" };
    case "outside_benin":
      return { label: lang === "fr" ? "Hors Bénin — risque critique" : "Outside Benin — critical risk", tone: "critical" };
    case "near_border_partial":
      return {
        label: lang === "fr" ? "Chevauche la frontière — à vérifier" : "Crosses the border — verify",
        tone: "warn",
      };
    case "not_applicable_local_crs":
      return {
        label: lang === "fr" ? "Contrôle territorial impossible sans géoréférencement" : "Territory check impossible without georeferencing",
        tone: "neutral",
      };
    case "invalid_geometry":
      return { label: lang === "fr" ? "Géométrie invalide" : "Invalid geometry", tone: "warn" };
    default:
      return { label: "—", tone: "neutral" };
  }
}

// L'audit doit être fortement averti / bloqué quand le tracé tombe hors Bénin.
export function blocksAudit(status: string): boolean {
  return status === "outside_benin";
}

// Corps de la requête POST /api/territory/benin/check (coordonnées SOURCE + CRS).
export function territoryCheckBody(
  points: { x: string; y: string }[],
  sourceCrs: string,
): { source_crs: string; coordinates: number[][] } {
  const num = (v: string) => Number(String(v).trim().replace(",", "."));
  const coordinates = points
    .filter((p) => p.x.trim() !== "" && p.y.trim() !== "" && Number.isFinite(num(p.x)) && Number.isFinite(num(p.y)))
    .map((p) => [num(p.x), num(p.y)]);
  return { source_crs: sourceCrs, coordinates };
}
