// Logique des bornes (P0) : affichage de la confiance OCR + validation humaine.
// confidence = qualité OCR machine (null si non fournie — JAMAIS 0 par défaut) ;
// validated = validation humaine, indicateur SÉPARÉ de la confiance.

export function confidenceLabel(confidence: number | null | undefined, lang: "fr" | "en" = "fr"): string {
  // null/undefined → « À valider » ; un vrai nombre (y compris 0) → « X% ».
  if (typeof confidence !== "number") return lang === "fr" ? "À valider" : "To validate";
  return `${Math.round(confidence * 100)}%`;
}

export type BorneInput = { label: string; x: string | number; y: string | number; validated?: boolean };

function _num(v: string | number): number {
  if (typeof v === "number") return v;
  const s = String(v).trim().replace(",", ".");
  return s === "" ? NaN : Number(s); // Number("") === 0 → on force NaN pour rejeter le vide
}

export function isBorneValid(pt: BorneInput): boolean {
  return pt.label.trim() !== "" && Number.isFinite(_num(pt.x)) && Number.isFinite(_num(pt.y));
}

// Confirmation possible uniquement si : ≥3 bornes, toutes valides (label/x/y), toutes
// validées humainement (validated === true).
export function canConfirmParcel(points: BorneInput[]): boolean {
  return points.length >= 3 && points.every((pt) => isBorneValid(pt) && pt.validated === true);
}

// Édition d'une borne (label/x/y) → invalide la validation humaine de cette borne.
export function editBorne<T extends Record<string, unknown>>(pt: T, field: "label" | "x" | "y", value: string): T {
  return { ...pt, [field]: value, validated: false };
}

// Mapping point → API : ne JAMAIS convertir une confiance absente en 0.
export function borneToApi(pt: { confidence?: number | null; validated?: boolean }): {
  confidence: number | null;
  validated: boolean;
} {
  return { confidence: pt.confidence ?? null, validated: pt.validated ?? false };
}
