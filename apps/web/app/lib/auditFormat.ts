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
