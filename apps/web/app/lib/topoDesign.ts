// Design system TopoAudit Bénin — porté depuis design/TopoAudit Bénin.dc.html.
// Thèmes (cadastre/instrument/terrain), chaînes FR/EN et helpers géométriques.

export type ThemeKey = "cadastre" | "instrument" | "terrain";
export type LangKey = "fr" | "en";

export type Theme = {
  name: string;
  bg: string;
  panel: string;
  panel2: string;
  ink: string;
  sub: string;
  faint: string;
  line: string;
  line2: string;
  accent: string;
  accentInk: string;
  accentSoft: string;
  grid: string;
  satA: string;
  satB: string;
  mapBg: string;
  mapInk: string;
  low: string;
  lowSoft: string;
  mod: string;
  modSoft: string;
  high: string;
  highSoft: string;
  shadow: string;
};

export const THEMES: Record<ThemeKey, Theme> = {
  cadastre: { name: "Cadastre", bg: "#E9E7DF", panel: "#FBFAF6", panel2: "#F1EFE7", ink: "#1B2620", sub: "#5C6A60", faint: "#909A8E", line: "#DCD9CD", line2: "#E8E5DB", accent: "#0F7B46", accentInk: "#FFFFFF", accentSoft: "#E2EFE7", grid: "#D7D3C5", satA: "#c9c2ae", satB: "#b8b09a", mapBg: "#F4F2EA", mapInk: "#3a463d", low: "#0F7B46", lowSoft: "#DEEFE4", mod: "#A66A0B", modSoft: "#F6ECD6", high: "#B0392C", highSoft: "#F3DDD8", shadow: "0 1px 2px rgba(40,46,38,.05), 0 10px 30px rgba(40,46,38,.05)" },
  instrument: { name: "Instrument", bg: "#0F1316", panel: "#171D21", panel2: "#1E262B", ink: "#E8EDEA", sub: "#94A099", faint: "#5F6A64", line: "#2A343A", line2: "#222B30", accent: "#E0A33E", accentInk: "#1B1305", accentSoft: "#2A2414", grid: "#222C32", satA: "#1c252a", satB: "#283238", mapBg: "#141A1E", mapInk: "#aab4ae", low: "#5FBE8C", lowSoft: "#15271E", mod: "#E0A33E", modSoft: "#2A2414", high: "#E06F5A", highSoft: "#2C1A15", shadow: "0 1px 2px rgba(0,0,0,.4), 0 14px 36px rgba(0,0,0,.4)" },
  terrain: { name: "Terrain", bg: "#E8ECEF", panel: "#FFFFFF", panel2: "#F3F6F8", ink: "#14202A", sub: "#566570", faint: "#8A98A2", line: "#DBE2E7", line2: "#E9EEF1", accent: "#1F6FEB", accentInk: "#FFFFFF", accentSoft: "#E3EDFC", grid: "#D7E0E6", satA: "#bcc8cf", satB: "#a9b6bd", mapBg: "#EEF2F5", mapInk: "#2f3e49", low: "#137A52", lowSoft: "#DBEFE7", mod: "#9A6A06", modSoft: "#F5EBD3", high: "#B23A2E", highSoft: "#F4DDD9", shadow: "0 1px 2px rgba(20,32,42,.05), 0 10px 30px rgba(20,32,42,.07)" },
};

export type Strings = Record<string, string>;

export const STR: Record<LangKey, Strings> = {
  fr: {
    project_meta: "Projet", workflow: "Flux de travail", dossier: "Dossier", step_label: "Étape", pages: "pages", bornes: "bornes",
    nav_intake: "Import", nav_intake_sub: "Plan & projet", nav_validate: "Validation", nav_validate_sub: "Coordonnées OCR", nav_audit: "Audit", nav_audit_sub: "Scores de risque", nav_report: "Rapport", nav_report_sub: "PDF & carte",
    intake_title: "Nouveau dossier d’audit", intake_sub: "Importez un plan topographique scanné et renseignez le contexte du projet. L’extraction OCR sera ensuite validée manuellement.",
    project_ctx: "Contexte du projet", f_project: "Nom du projet", f_commune: "Commune", f_country: "Pays", f_notes: "Notes",
    drop_title: "Déposez le plan scanné", drop_hint: "JPG, PNG ou PDF — un ou plusieurs feuillets", detected: "Détection préliminaire",
    d_title: "Titre du document", d_surface: "Surface déclarée", d_scale: "Échelle", d_geo: "Système géodésique", d_crs: "CRS détecté", d_parcels: "Parcelles",
    d_file: "Fichier", d_type: "Type", d_size: "Taille", d_nofile: "aucun fichier sélectionné", d_pending: "après extraction OCR", d_bornes_total: "Bornes détectées",
    btn_ocr: "Lancer l’extraction OCR",
    val_title: "Validation humaine des coordonnées", val_sub: "Corrigez les bornes extraites avant tout calcul. Aucun audit n’est lancé sans votre confirmation explicite.",
    scan: "Plan source", scan_ph: "aperçu du scan",
    surface_ocr: "Surface OCR brute", surface_m2: "Surface déclarée (m²)", crs: "Système de coordonnées", crs_local: "Coordonnées locales",
    c_borne: "Borne", c_x: "X (Est)", c_y: "Y (Nord)", c_conf: "Confiance", remove: "Retirer", add_borne: "Ajouter une borne",
    live_area: "Surface calc.", live_per: "Périmètre", live_delta: "Écart surface", live_valid: "Validité",
    confirm: "Confirmer la parcelle", confirmed: "Parcelle confirmée", to_confirm: "À confirmer",
    btn_audit: "Lancer l’audit",
    audit_title: "Audit préliminaire de risque", audit_sub: "Synthèse de cohérence technique du levé. Cet audit ne certifie pas la conformité juridique de la parcelle.",
    score_ocr: "Score d’extraction", score_tech: "Score technique", risk: "Niveau de risque",
    risk_low: "Risque faible", risk_mod: "Risque modéré", risk_high: "Risque élevé", risk_ins: "Données insuffisantes",
    hint_low: "Levé géométriquement cohérent.", hint_mod: "Écarts à vérifier avant transaction.", hint_high: "Incohérences techniques notables.", hint_ins: "Complétez les coordonnées.",
    per_parcel: "Détail par parcelle", findings: "Anomalies détectées",
    m_declared: "Décl.", m_calc: "Calc.", m_delta: "Écart", m_per: "Périm.", m_pts: "Bornes",
    disclaimer: "Audit préliminaire — ne remplace pas un géomètre-expert ni une certification juridique. Aucune comparaison cadastrale officielle n’a été effectuée.",
    btn_report: "Générer le rapport",
    report_title: "Rapport d’audit préliminaire", generated: "Généré le", file: "Fichier :",
    map_title: "Tracé de la parcelle", map_plan: "Plan", map_sat: "Satellite", sat_note: "Fond satellite indicatif — visualisation uniquement, non référence cadastrale.", map_local: "Vue locale — coordonnées non géoréférencées (pas de fond satellite).",
    seg_table: "Distances entre bornes", seg_from: "De", seg_to: "À", seg_len: "Longueur", recommendations: "Recommandations", tech_log: "Journal technique", export_pdf: "Exporter le PDF",
    reco_body: "Le document semble géométriquement cohérent. L’audit ne compare pas encore le levé à une référence cadastrale officielle. Vérifiez le TF/QIP ou demandez un extrait cadastral avant toute transaction.",
    st_correct: "Corrigez les bornes puis confirmez chaque parcelle.", st_confirmed: "Parcelle confirmée — vous pouvez lancer l’audit.", st_need: "Confirmez les deux parcelles pour activer l’audit.",
  },
  en: {
    project_meta: "Project", workflow: "Workflow", dossier: "Dossier", step_label: "Step", pages: "pages", bornes: "corners",
    nav_intake: "Import", nav_intake_sub: "Plan & project", nav_validate: "Validation", nav_validate_sub: "OCR coordinates", nav_audit: "Audit", nav_audit_sub: "Risk scores", nav_report: "Report", nav_report_sub: "PDF & map",
    intake_title: "New audit dossier", intake_sub: "Import a scanned survey plan and fill in the project context. OCR extraction is validated manually afterwards.",
    project_ctx: "Project context", f_project: "Project name", f_commune: "Commune", f_country: "Country", f_notes: "Notes",
    drop_title: "Drop the scanned plan", drop_hint: "JPG, PNG or PDF — one or several sheets", detected: "Preliminary detection",
    d_title: "Document title", d_surface: "Declared area", d_scale: "Scale", d_geo: "Geodetic system", d_crs: "Detected CRS", d_parcels: "Parcels",
    d_file: "File", d_type: "Type", d_size: "Size", d_nofile: "no file selected", d_pending: "after OCR extraction", d_bornes_total: "Detected corners",
    btn_ocr: "Run OCR extraction",
    val_title: "Human coordinate validation", val_sub: "Correct the extracted corners before any computation. No audit runs without your explicit confirmation.",
    scan: "Source plan", scan_ph: "scan preview",
    surface_ocr: "Raw OCR area", surface_m2: "Declared area (m²)", crs: "Coordinate system", crs_local: "Local coordinates",
    c_borne: "Corner", c_x: "X (East)", c_y: "Y (North)", c_conf: "Confidence", remove: "Remove", add_borne: "Add a corner",
    live_area: "Calc. area", live_per: "Perimeter", live_delta: "Area delta", live_valid: "Validity",
    confirm: "Confirm parcel", confirmed: "Parcel confirmed", to_confirm: "To confirm",
    btn_audit: "Run audit",
    audit_title: "Preliminary risk audit", audit_sub: "Technical-consistency summary of the survey. This audit does not certify legal compliance of the parcel.",
    score_ocr: "Extraction score", score_tech: "Technical score", risk: "Risk level",
    risk_low: "Low risk", risk_mod: "Moderate risk", risk_high: "High risk", risk_ins: "Insufficient data",
    hint_low: "Geometrically consistent survey.", hint_mod: "Deviations to check before transaction.", hint_high: "Notable technical inconsistencies.", hint_ins: "Complete the coordinates.",
    per_parcel: "Per-parcel detail", findings: "Detected anomalies",
    m_declared: "Decl.", m_calc: "Calc.", m_delta: "Delta", m_per: "Perim.", m_pts: "Corners",
    disclaimer: "Preliminary audit — does not replace a licensed surveyor nor a legal certification. No official cadastral comparison has been performed.",
    btn_report: "Generate report",
    report_title: "Preliminary audit report", generated: "Generated", file: "File:",
    map_title: "Parcel outline", map_plan: "Plan", map_sat: "Satellite", sat_note: "Indicative satellite background — visualization only, not a cadastral reference.", map_local: "Local view — non-georeferenced coordinates (no satellite background).",
    seg_table: "Distances between corners", seg_from: "From", seg_to: "To", seg_len: "Length", recommendations: "Recommendations", tech_log: "Technical log", export_pdf: "Export PDF",
    reco_body: "The document appears geometrically consistent. The audit does not yet compare the survey to an official cadastral reference. Verify the TF/QIP or request a cadastral extract before any transaction.",
    st_correct: "Correct the corners then confirm each parcel.", st_confirmed: "Parcel confirmed — you can run the audit.", st_need: "Confirm both parcels to enable the audit.",
  },
};

// ---- helpers (portés verbatim) ----
export const num = (v: string | number): number => {
  const n = parseFloat(String(v).replace(",", ".").replace(/\s/g, ""));
  return Number.isFinite(n) ? n : NaN;
};

export const fmt = (n: number | null | undefined, d: number): string => {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return n.toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d });
};

export type Point = { label: string; x: string; y: string; confidence: number };

export type Geom = {
  valid: boolean;
  area: number | null;
  perimeter: number | null;
  segs: { from: string; to: string; len: number }[];
};

export const geom = (points: Point[]): Geom => {
  const pts = points.map((p) => [num(p.x), num(p.y)] as [number, number]);
  const valid = pts.length >= 3 && pts.every(([x, y]) => Number.isFinite(x) && Number.isFinite(y));
  if (!valid) return { valid: false, area: null, perimeter: null, segs: [] };
  let area = 0;
  let per = 0;
  const segs: Geom["segs"] = [];
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    area += a[0] * b[1] - b[0] * a[1];
    const d = Math.hypot(b[0] - a[0], b[1] - a[1]);
    per += d;
    segs.push({ from: points[i].label, to: points[(i + 1) % points.length].label, len: d });
  }
  return { valid: true, area: Math.abs(area) / 2, perimeter: per, segs };
};

export type DeltaBand = "low" | "mod" | "high" | "none";
export const deltaInfo = (declared: number, calc: number | null): { abs: number | null; pct: number | null; band: DeltaBand } => {
  if (calc === null || !Number.isFinite(declared) || declared <= 0) return { abs: null, pct: null, band: "none" };
  const abs = calc - declared;
  const pct = (abs / declared) * 100;
  const ap = Math.abs(pct);
  const band: DeltaBand = ap <= 1 ? "low" : ap <= 5 ? "mod" : "high";
  return { abs, pct, band };
};

export const hexA = (hex: string, a: number): string => {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
};

export const confTone = (t: Theme, c: number): { bg: string; fg: string } => {
  if (c >= 0.9) return { bg: t.lowSoft, fg: t.low };
  if (c >= 0.8) return { bg: t.modSoft, fg: t.mod };
  return { bg: t.highSoft, fg: t.high };
};

export type Parcel = {
  id: string;
  name: string;
  declaredRaw: string;
  declaredM2: string;
  crs: string;
  confirmed: boolean;
  points: Point[];
};

export const DEFAULT_PARCELS: Parcel[] = [
  {
    id: "p1", name: "Parcelle 1", declaredRaw: "05a 49ca", declaredM2: "549", crs: "EPSG:32631", confirmed: false,
    points: [
      { label: "B1", x: "403825.84", y: "707630.38", confidence: 0.94 },
      { label: "B2", x: "403836.57", y: "707626.36", confidence: 0.92 },
      { label: "B3", x: "403830.47", y: "707610.52", confidence: 0.88 },
      { label: "B4", x: "403827.18", y: "707601.32", confidence: 0.95 },
      { label: "B5", x: "403799.28", y: "707612.51", confidence: 0.9 },
    ],
  },
  {
    id: "p2", name: "Parcelle 2", declaredRaw: "02a 08ca", declaredM2: "208", crs: "EPSG:32631", confirmed: false,
    points: [
      { label: "C1", x: "403868.10", y: "707655.40", confidence: 0.81 },
      { label: "C2", x: "403884.40", y: "707650.10", confidence: 0.74 },
      { label: "C3", x: "403879.20", y: "707631.50", confidence: 0.86 },
      { label: "C4", x: "403861.00", y: "707637.20", confidence: 0.79 },
    ],
  },
];
