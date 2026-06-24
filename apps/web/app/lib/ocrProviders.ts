// Providers OCR sélectionnables à l'étape Import (Gemma/Gemini, Mistral OCR 4, Mock).
// Le provider choisi est envoyé au backend en query param ?provider= lors de l'appel OCR.

export type OcrProviderId = "gemini" | "mistral" | "mock";

export const OCR_PROVIDERS: { id: OcrProviderId; labelFr: string; labelEn: string }[] = [
  { id: "gemini", labelFr: "Gemma 4 / Gemini", labelEn: "Gemma 4 / Gemini" },
  { id: "mistral", labelFr: "Mistral OCR 4", labelEn: "Mistral OCR 4" },
  { id: "mock", labelFr: "Mock OCR", labelEn: "Mock OCR" },
];

export const DEFAULT_OCR_PROVIDER: OcrProviderId = "gemini";

export function ocrProviderLabel(id: string, lang: "fr" | "en" = "fr"): string {
  const provider = OCR_PROVIDERS.find((p) => p.id === id);
  if (!provider) return id; // provider réel inconnu (ex. azure) → afficher l'id brut
  return lang === "fr" ? provider.labelFr : provider.labelEn;
}

// Chemin OCR avec provider en query param (n'altère pas le workflow par défaut).
export function ocrRequestPath(projectId: string, documentId: string, provider: string): string {
  return `/projects/${projectId}/documents/${documentId}/ocr?provider=${encodeURIComponent(provider)}`;
}
