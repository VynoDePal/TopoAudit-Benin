// Affichage du score d'extraction (P0). Un score null = « validation humaine requise » :
// on affiche « à valider », JAMAIS 0/100 et jamais une jauge numérique. Un vrai 0 reste
// « 0/100 » (score réel, pas une valeur manquante convertie).

export function isExtractionScoreNull(score: number | null | undefined): boolean {
  return score === null || score === undefined;
}

export function extractionScoreText(score: number | null | undefined, lang: "fr" | "en" = "fr"): string {
  if (isExtractionScoreNull(score)) return lang === "fr" ? "À valider" : "To validate";
  return `${score}/100`;
}

// Affichage de la carte « Score d'extraction » :
// - score OCR machine présent → « X/100 » ;
// - sinon, si l'utilisateur a coché des bornes → « Validé · X/100 » (score de validation
//   HUMAINE, distinct de la confiance OCR) ;
// - sinon → « À valider ».
export function extractionDisplay(
  extractionScore: number | null | undefined,
  humanValidationScore: number | null | undefined,
  lang: "fr" | "en" = "fr",
): { label: string; validated: boolean; nullScore: boolean; gaugeScore: number | null } {
  if (!isExtractionScoreNull(extractionScore)) {
    return { label: `${extractionScore}/100`, validated: false, nullScore: false, gaugeScore: extractionScore as number };
  }
  if (!isExtractionScoreNull(humanValidationScore)) {
    const validated = lang === "fr" ? "Validé" : "Validated";
    return { label: `${validated} · ${humanValidationScore}/100`, validated: true, nullScore: false, gaugeScore: humanValidationScore as number };
  }
  return { label: lang === "fr" ? "À valider" : "To validate", validated: false, nullScore: true, gaugeScore: null };
}
