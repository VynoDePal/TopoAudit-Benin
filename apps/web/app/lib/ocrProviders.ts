// Providers OCR sélectionnables à l'étape Import (Gemma/Gemini, Mistral OCR 4, Mock).
// Le provider choisi est envoyé au backend en query param ?provider= lors de l'appel OCR.

export type OcrProviderId = "gemini" | "mistral" | "mock";

export const OCR_PROVIDERS: { id: OcrProviderId; labelFr: string; labelEn: string }[] = [
  { id: "gemini", labelFr: "Gemma 4 / Gemini", labelEn: "Gemma 4 / Gemini" },
  { id: "mistral", labelFr: "Mistral OCR 4", labelEn: "Mistral OCR 4" },
  { id: "mock", labelFr: "Mock OCR", labelEn: "Mock OCR" },
];

// Défaut = Gemma 4 / Gemini, recommandé pour plans topographiques scannés (prompt
// spécialisé, plus fiable sur les coordonnées visibles). Surchargeable dans le select.
export const DEFAULT_OCR_PROVIDER: OcrProviderId = "gemini";

export function ocrProviderLabel(id: string, lang: "fr" | "en" = "fr"): string {
  const provider = OCR_PROVIDERS.find((p) => p.id === id);
  if (!provider) return id; // provider réel inconnu (ex. azure) → afficher l'id brut
  return lang === "fr" ? provider.labelFr : provider.labelEn;
}

// État d'un provider renvoyé par GET /api/ocr/providers (jamais de clé).
export type OcrProviderInfo = {
  id: string;
  label: string;
  configured: boolean;
  supports_word_confidence: boolean;
  // selectable = utilisable (configuré OU fallback mock autorisé en local). En
  // staging/production un provider non configuré n'est PAS selectable.
  selectable?: boolean;
};

// Défaut dynamique : premier provider CONFIGURÉ dans l'ordre gemini > mistral > mock
// (Gemma recommandé d'abord ; mock toujours configuré → il y a toujours un défaut).
export function pickDefaultProvider(providers: OcrProviderInfo[]): OcrProviderId {
  for (const id of ["gemini", "mistral", "mock"] as OcrProviderId[]) {
    const p = providers.find((x) => x.id === id);
    if (p && p.configured) return id;
  }
  return "mock";
}

// Nature / recommandation du provider (descriptif, indépendant de la config).
export function ocrProviderNature(id: string, lang: "fr" | "en" = "fr"): string {
  if (id === "gemini") return lang === "fr" ? "recommandé" : "recommended";
  if (id === "mistral") return lang === "fr" ? "rapide / expérimental" : "fast / experimental";
  if (id === "mock") return lang === "fr" ? "démo locale" : "local demo";
  return "";
}

// Libellé d'option : « Gemma 4 / Gemini — recommandé », « Mistral OCR 4 — rapide /
// expérimental », « Mock OCR — démo locale » (+ « · clé absente » si non configuré).
export function ocrProviderStatusLabel(p: OcrProviderInfo, lang: "fr" | "en" = "fr"): string {
  const nature = ocrProviderNature(p.id, lang);
  const head = nature ? `${ocrProviderLabel(p.id, lang)} — ${nature}` : ocrProviderLabel(p.id, lang);
  if (p.id === "mock" || p.configured) return head;
  if (p.selectable) return `${head} · ${lang === "fr" ? "clé absente (fallback mock)" : "key missing (mock fallback)"}`;
  return `${head} · ${lang === "fr" ? "clé absente" : "key missing"}`;
}

// Chemin OCR avec provider en query param (n'altère pas le workflow par défaut).
export function ocrRequestPath(projectId: string, documentId: string, provider: string): string {
  return `/projects/${projectId}/documents/${documentId}/ocr?provider=${encodeURIComponent(provider)}`;
}

// Après un OCR RÉEL : si aucune borne exploitable, on vide l'écran (jamais de données de
// démo après un upload). Sinon on affiche les parcelles extraites.
export function parcelsAfterOcr<T>(mapped: T[]): { parcels: T[]; activeIdx: number; emptyExtraction: boolean } {
  if (mapped.length === 0) return { parcels: [], activeIdx: 0, emptyExtraction: true };
  return { parcels: mapped, activeIdx: 0, emptyExtraction: false };
}
