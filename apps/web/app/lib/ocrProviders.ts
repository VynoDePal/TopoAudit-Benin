// Providers OCR sélectionnables à l'étape Import (Gemma/Gemini, Mistral OCR 4, Mock).
// Le provider choisi est envoyé au backend en query param ?provider= lors de l'appel OCR.

export type OcrProviderId = "gemini" | "mistral" | "mock";

export const OCR_PROVIDERS: { id: OcrProviderId; labelFr: string; labelEn: string }[] = [
  { id: "gemini", labelFr: "Gemma 4 / Gemini", labelEn: "Gemma 4 / Gemini" },
  { id: "mistral", labelFr: "Mistral OCR 4", labelEn: "Mistral OCR 4" },
  { id: "mock", labelFr: "Mock OCR", labelEn: "Mock OCR" },
];

// Défaut = Mistral OCR 4 (meilleure extraction + confiance OCR par borne). Surchargeable
// dans le select « Moteur OCR » à l'import.
export const DEFAULT_OCR_PROVIDER: OcrProviderId = "mistral";

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

// Défaut dynamique : premier provider CONFIGURÉ dans l'ordre mistral > gemini > mock
// (mock toujours configuré → il y a toujours un défaut).
export function pickDefaultProvider(providers: OcrProviderInfo[]): OcrProviderId {
  for (const id of ["mistral", "gemini", "mock"] as OcrProviderId[]) {
    const p = providers.find((x) => x.id === id);
    if (p && p.configured) return id;
  }
  return "mock";
}

// Libellé d'option : « Mistral OCR 4 — configuré / clé absente (fallback mock) / clé absente ».
export function ocrProviderStatusLabel(p: OcrProviderInfo, lang: "fr" | "en" = "fr"): string {
  const base = ocrProviderLabel(p.id, lang);
  if (p.id === "mock") return `${base} — ${lang === "fr" ? "local" : "local"}`;
  if (p.configured) return `${base} — ${lang === "fr" ? "configuré" : "configured"}`;
  if (p.selectable) return `${base} — ${lang === "fr" ? "clé absente (fallback mock)" : "key missing (mock fallback)"}`;
  return `${base} — ${lang === "fr" ? "clé absente" : "key missing"}`;
}

// Chemin OCR avec provider en query param (n'altère pas le workflow par défaut).
export function ocrRequestPath(projectId: string, documentId: string, provider: string): string {
  return `/projects/${projectId}/documents/${documentId}/ocr?provider=${encodeURIComponent(provider)}`;
}
