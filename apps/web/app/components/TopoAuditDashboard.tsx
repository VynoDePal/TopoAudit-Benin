"use client";

// Dashboard TopoAudit Bénin — port fidèle de design/TopoAudit Bénin.dc.html
// (top bar + sidebar workflow + 4 étapes intake→validate→audit→report, 3 thèmes, FR/EN).
import { CSSProperties, useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection, Polygon } from "geojson";

import ParcelMap from "./ParcelMap";
import { authHeaders, loadToken, saveToken, withAuth } from "../lib/authClient";
import { extractionScoreText, isExtractionScoreNull } from "../lib/auditFormat";
import { isTransformableCrs, toWgs84 } from "../lib/crsClient";
import {
  confTone,
  DEFAULT_PARCELS,
  deltaInfo,
  fmt,
  geom,
  hexA,
  num,
  type LangKey,
  type Parcel,
  type Theme,
  type ThemeKey,
  STR,
  THEMES,
} from "../lib/topoDesign";

const MONO = "'IBM Plex Mono', monospace";
type S = Record<string, string>;

// Réponse d'audit du backend (source de vérité, identique au PDF). extraction_score peut
// être null (validation humaine requise) → ne JAMAIS le convertir implicitement en 0.
type AuditApiResponse = {
  extraction_score: number | null;
  extraction_score_status?: string;
  technical_score: number;
  risk_level: string;
  warnings: string[];
  parcels: { label: string; declared_surface_m2: number | null; calculated_surface_m2: number | null; technical_score: number; risk_level: string; warnings: string[] }[];
};

// ---- carte SVG (porté de buildMap) ----
function buildMap(t: Theme, parcels: Parcel[], sat: boolean) {
  const all: [number, number, string][] = [];
  const pcData = parcels.map((p) => {
    const g = geom(p.points);
    const npts = p.points
      .map((pt) => [num(pt.x), num(pt.y), pt.label] as [number, number, string])
      .filter((a) => Number.isFinite(a[0]) && Number.isFinite(a[1]));
    npts.forEach((a) => all.push(a));
    return { p, g, npts };
  });
  const W = 520;
  const H = 420;
  const pad = 54;
  if (all.length < 3) {
    return { bg: t.mapBg, gridColor: t.grid, ink: t.mapInk, labelBg: t.mapBg, sat, satA: t.satA, satB: t.satB, grid: [] as any[], parcels: [] as any[], scaleLen: 80, scaleHalf: 40, scaleLabel: "—" };
  }
  const xs = all.map((a) => a[0]);
  const ys = all.map((a) => a[1]);
  const minx = Math.min(...xs);
  const maxx = Math.max(...xs);
  const miny = Math.min(...ys);
  const maxy = Math.max(...ys);
  const dx = Math.max(maxx - minx, 1);
  const dy = Math.max(maxy - miny, 1);
  const scale = Math.min((W - 2 * pad) / dx, (H - 2 * pad) / dy);
  const ox = (W - dx * scale) / 2;
  const oy = (H - dy * scale) / 2;
  const sx = (x: number) => ox + (x - minx) * scale;
  const sy = (y: number) => H - oy - (y - miny) * scale;
  const grid: { x1: number; y1: number; x2: number; y2: number }[] = [];
  for (let i = 0; i <= 6; i++) {
    const gx = pad + (i * (W - 2 * pad)) / 6;
    grid.push({ x1: gx, y1: 0, x2: gx, y2: H });
  }
  for (let j = 0; j <= 5; j++) {
    const gy = pad + (j * (H - 2 * pad)) / 5;
    grid.push({ x1: 0, y1: gy, x2: W, y2: gy });
  }
  const colors = [t.accent, t.mod];
  const mapParcels = pcData
    .filter((d) => d.npts.length >= 3)
    .map((d, idx) => {
      const stroke = colors[idx % colors.length];
      const screen = d.npts.map((a) => [sx(a[0]), sy(a[1]), a[2]] as [number, number, string]);
      const poly = screen.map((a) => `${a[0].toFixed(1)},${a[1].toFixed(1)}`).join(" ");
      const bornes = screen.map((a) => ({ rx: (a[0] - 3.5).toFixed(1), ry: (a[1] - 3.5).toFixed(1), lx: (a[0] + 6).toFixed(1), ly: (a[1] - 6).toFixed(1), label: a[2] }));
      const segs = screen.map((a, i) => {
        const b = screen[(i + 1) % screen.length];
        const mx = (a[0] + b[0]) / 2;
        const my = (a[1] + b[1]) / 2;
        const len = Math.hypot(d.npts[(i + 1) % d.npts.length][0] - d.npts[i][0], d.npts[(i + 1) % d.npts.length][1] - d.npts[i][1]);
        const label = `${len.toFixed(1)}m`;
        const rw = label.length * 5.6 + 6;
        return { x: mx.toFixed(1), y: (my + 3).toFixed(1), rx: (mx - rw / 2).toFixed(1), ry: (my - 8).toFixed(1), rw: rw.toFixed(1), label };
      });
      const cx = screen.reduce((sm, a) => sm + a[0], 0) / screen.length;
      const cy = screen.reduce((sm, a) => sm + a[1], 0) / screen.length;
      return { poly, stroke, fill: hexA(stroke, sat ? 0.32 : 0.16), bornes, segs, cx: cx.toFixed(1), cy: (cy + 4).toFixed(1), name: d.p.name };
    });
  const target = 90 / scale;
  const pow = Math.pow(10, Math.floor(Math.log10(target)));
  let nice = pow;
  [1, 2, 5, 10].forEach((m) => {
    if (pow * m <= target) nice = pow * m;
  });
  const len = nice * scale;
  return { bg: t.mapBg, gridColor: t.grid, ink: t.mapInk, labelBg: hexA(t.mapBg, 0.85), sat, satA: t.satA, satB: t.satB, grid, parcels: mapParcels, scaleLen: len.toFixed(1), scaleHalf: (len / 2).toFixed(1), scaleLabel: `${nice} m` };
}

type Stage = "intake" | "validate" | "audit" | "report";

export default function TopoAuditDashboard() {
  const [stage, setStage] = useState<Stage>("intake");
  const [themeKey, setThemeKey] = useState<ThemeKey>("cadastre");
  const [lang, setLang] = useState<LangKey>("fr");
  const [activeIdx, setActiveIdx] = useState(0);
  const [mapSat, setMapSat] = useState(false);
  // Auth (P0) : token JWT pour le mode non DEMO_LOCAL ; en mémoire + localStorage.
  const [token, setToken] = useState<string | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [authEmail, setAuthEmail] = useState("");
  const [authPwd, setAuthPwd] = useState("");
  useEffect(() => { setToken(loadToken()); }, []);
  const [projectName, setProjectName] = useState("Vérification Abomey-Calavi");
  const [commune, setCommune] = useState("Abomey-Calavi");
  const [notes, setNotes] = useState("Avant achat");
  const [parcels, setParcels] = useState<Parcel[]>(DEFAULT_PARCELS);

  // Câblage backend : projet réel + fichier uploadé + états async.
  const [projectId, setProjectId] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<null | "ocr" | "audit" | "export">(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<AuditApiResponse | null>(null);
  // Métadonnées OCR (P0.3) : provider réel vs mock + CRS détecté, pour affichage explicite.
  const [ocrInfo, setOcrInfo] = useState<{ isMock: boolean; provider: string; crs: string; scoreStatus: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const t = THEMES[themeKey];
  const s: S = STR[lang];

  // Aperçu de l'image uploadée (visualiseur de scan) ; révoqué au changement/démontage.
  const filePreview = useMemo(() => (file && file.type.startsWith("image/") ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (filePreview) URL.revokeObjectURL(filePreview); }, [filePreview]);
  // Toute (re)définition des parcelles (upload, édition) invalide l'audit affiché.
  useEffect(() => { setAuditResult(null); }, [parcels]);
  // Géoréférencé = OCR transformable (s'il y a un OCR) ET toutes les parcelles affichées
  // ont un CRS transformable. Une seule parcelle non transformable (LOCAL_ONLY/UNKNOWN/
  // NEEDS_GEOREFERENCING) → pas de fond satellite, vue locale, warning.
  const ocrTransformable = !ocrInfo || isTransformableCrs(ocrInfo.crs);
  const parcelsTransformable = parcels.length === 0 || parcels.every((p) => isTransformableCrs(p.crs));
  const isGeoreferenced = ocrTransformable && parcelsTransformable;
  useEffect(() => { if (!isGeoreferenced && mapSat) setMapSat(false); }, [isGeoreferenced, mapSat]);
  // GeoJSON EPSG:4326 des parcelles pour MapLibre (carte géoréférencée réelle), construit
  // par transformation des coordonnées source — UNIQUEMENT les parcelles transformables.
  const geoParcels = useMemo<FeatureCollection<Polygon>>(() => {
    const confirmed = parcels.filter((p) => p.confirmed);
    const src = confirmed.length ? confirmed : parcels;
    return {
      type: "FeatureCollection",
      features: src
        .filter((p) => p.points.length >= 3 && isTransformableCrs(p.crs))
        .map((p) => {
          const ring = p.points.map((pt) => toWgs84(num(pt.x), num(pt.y), p.crs));
          if (ring.length > 0) ring.push(ring[0]);
          return {
            type: "Feature" as const,
            properties: { name: p.name, risk: "Modéré" },
            geometry: { type: "Polygon" as const, coordinates: [ring] },
          };
        }),
    };
  }, [parcels]);
  // CRS réellement affiché (data-driven, jamais EPSG:32631 codé en dur) : le CRS commun
  // des parcelles si uniforme, sinon null → « CRS à confirmer ».
  const displayedCrs =
    parcels.length > 0 && parcels.every((p) => p.crs === parcels[0].crs) ? parcels[0].crs : null;

  // ---- couche API (backend FastAPI réel) ----
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";
  const apiJson = async (method: string, path: string, body?: unknown) => {
    const base: Record<string, string> = body !== undefined ? { "Content-Type": "application/json" } : {};
    const res = await fetch(`${apiBaseUrl}${path}`, {
      method,
      headers: withAuth(token, base),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error((await res.text().catch(() => "")) || `${method} ${path} → ${res.status}`);
    return res.json();
  };
  const mapFromApi = (apiParcels: any[]): Parcel[] =>
    apiParcels.map((p, i) => ({
      id: p.id ?? `p${i + 1}`,
      name: p.label ?? `Parcelle ${i + 1}`,
      declaredRaw: "",
      declaredM2: p.declared_surface_m2 != null ? String(p.declared_surface_m2) : "",
      crs: p.detected_crs ?? "UNKNOWN_CRS",
      confirmed: false,
      points: (p.points ?? []).map((pt: any) => ({ label: pt.label, x: String(pt.x), y: String(pt.y), confidence: pt.confidence ?? 0 })),
    }));
  const mapToApi = (list: Parcel[]) =>
    list.map((p) => ({
      label: p.name,
      declared_surface_m2: Number.isFinite(num(p.declaredM2)) ? num(p.declaredM2) : null,
      detected_crs: p.crs,
      points: p.points.map((pt) => ({ label: pt.label, x: num(pt.x), y: num(pt.y), confidence: pt.confidence })),
    }));

  // Statut CRS (EPSG_32631…) → libellé EPSG transformable, ou statut tel quel (LOCAL_ONLY…).
  const crsStatusToDisplay = (status?: string): string => {
    if (status === "EPSG_32631") return "EPSG:32631";
    if (status === "EPSG_4326") return "EPSG:4326";
    return status ?? "UNKNOWN_CRS";
  };

  // Auth : connexion/inscription → token JWT (stocké). En mode démo local, on peut
  // travailler sans token (le backend l'autorise) ; en non-démo, le token est requis.
  const doAuth = async (mode: "login" | "register") => {
    setErrorMsg(null);
    try {
      const res = await fetch(`${apiBaseUrl}/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: authEmail.trim(), password: authPwd }),
      });
      if (!res.ok) throw new Error((await res.text().catch(() => "")) || `${mode} → ${res.status}`);
      const data = await res.json();
      setToken(data.token);
      saveToken(data.token);
      setAuthOpen(false);
      setAuthPwd("");
    } catch (e) {
      setErrorMsg((lang === "fr" ? "Échec authentification : " : "Auth failed: ") + (e instanceof Error ? e.message : String(e)).slice(0, 160));
    }
  };
  const doLogout = () => { setToken(null); saveToken(null); };

  // Intake → OCR réel : crée le projet, uploade le plan, lance l'OCR, récupère les bornes.
  const runOcr = async () => {
    setErrorMsg(null);
    if (!file) { setStage("validate"); return; } // mode démo (sans fichier)
    setBusy("ocr");
    try {
      const proj = await apiJson("POST", "/projects", { name: projectName || "Audit" });
      setProjectId(proj.id);
      const form = new FormData();
      form.append("file", file);
      const up = await fetch(`${apiBaseUrl}/projects/${proj.id}/documents`, { method: "POST", body: form, headers: authHeaders(token) });
      if (!up.ok) throw new Error((await up.text().catch(() => "")) || `Upload → ${up.status}`);
      const upDoc = await up.json();
      // P0.3 : l'OCR est une étape EXPLICITE (l'upload ne fait que stocker le fichier).
      const ocr = await apiJson("POST", `/projects/${proj.id}/documents/${upDoc.id}/ocr`);
      setOcrInfo({ isMock: !!ocr.is_mock_result, provider: ocr.actual_provider ?? "?", crs: ocr.detected_crs ?? "UNKNOWN_CRS", scoreStatus: ocr.extraction_score_status ?? "needs_human_validation" });
      const crsForParcels = crsStatusToDisplay(ocr.detected_crs);
      const mapped = mapFromApi((ocr.parsed_parcels ?? []).map((p: any) => ({ ...p, detected_crs: crsForParcels })));
      if (mapped.length) {
        setParcels(mapped);
        setActiveIdx(0);
      } else {
        setErrorMsg(lang === "fr" ? "OCR : aucune borne extraite — corrigez/ajoutez manuellement." : "OCR: no corner extracted — correct/add manually.");
      }
      setStage("validate");
    } catch (e) {
      setErrorMsg((lang === "fr" ? "Échec OCR : " : "OCR failed: ") + (e instanceof Error ? e.message : String(e)).slice(0, 160));
    } finally {
      setBusy(null);
    }
  };

  // Validate → Audit réel : sauvegarde les corrections, transite, lance l'audit backend.
  const runAudit = async (allConfirmed: boolean) => {
    if (!allConfirmed) return;
    setErrorMsg(null);
    if (!projectId) { setStage("audit"); return; } // mode démo
    setBusy("audit");
    try {
      await apiJson("PUT", `/projects/${projectId}/parcels`, { parcels: mapToApi(parcels) });
      await apiJson("POST", `/projects/${projectId}/validate`, {});
      const audit = (await apiJson("POST", `/projects/${projectId}/audit`, {})) as AuditApiResponse;
      setAuditResult(audit); // affichage = résultat backend (cohérent avec le PDF)
      setStage("audit");
    } catch (e) {
      setErrorMsg((lang === "fr" ? "Échec audit : " : "Audit failed: ") + (e instanceof Error ? e.message : String(e)).slice(0, 160));
    } finally {
      setBusy(null);
    }
  };

  // Report → PDF réel (backend WeasyPrint) ou impression (mode démo).
  const exportReport = async () => {
    setErrorMsg(null);
    if (!projectId) { if (typeof window !== "undefined") window.print(); return; }
    setBusy("export");
    try {
      const res = await fetch(`${apiBaseUrl}/projects/${projectId}/audit/report.pdf`, { method: "POST", headers: authHeaders(token) });
      if (!res.ok) throw new Error((await res.text().catch(() => "")) || `PDF → ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `topoaudit-${projectId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErrorMsg((lang === "fr" ? "Échec export : " : "Export failed: ") + (e instanceof Error ? e.message : String(e)).slice(0, 160));
    } finally {
      setBusy(null);
    }
  };

  // ---- mutators ----
  const updatePoint = (pIdx: number, rIdx: number, field: keyof Parcel["points"][number], val: string) =>
    setParcels((prev) =>
      prev.map((p, i) =>
        i !== pIdx ? p : { ...p, confirmed: false, points: p.points.map((pt, j) => (j === rIdx ? { ...pt, [field]: val } : pt)) },
      ),
    );
  const addPoint = (pIdx: number) =>
    setParcels((prev) =>
      prev.map((p, i) => {
        if (i !== pIdx) return p;
        const n = p.points.length + 1;
        const pre = p.points[0] ? p.points[0].label.replace(/[0-9]/g, "") : "B";
        return { ...p, confirmed: false, points: [...p.points, { label: pre + n, x: "", y: "", confidence: 0 }] };
      }),
    );
  const removePoint = (pIdx: number, rIdx: number) =>
    setParcels((prev) =>
      prev.map((p, i) => (i !== pIdx ? p : p.points.length <= 3 ? p : { ...p, confirmed: false, points: p.points.filter((_, j) => j !== rIdx) })),
    );
  const updateField = (pIdx: number, field: "declaredRaw" | "declaredM2" | "crs", val: string) =>
    setParcels((prev) => prev.map((p, i) => (i === pIdx ? { ...p, [field]: val, confirmed: false } : p)));
  const confirmParcel = (pIdx: number) =>
    setParcels((prev) => prev.map((p, i) => (i === pIdx ? { ...p, confirmed: !p.confirmed } : p)));

  // ---- derived (équivalent renderVals) ----
  const view = useMemo(() => {
    const order: Record<Stage, number> = { intake: 0, validate: 1, audit: 2, report: 3 };
    const steps = [
      { key: "intake" as Stage, n: "01", label: s.nav_intake, sub: s.nav_intake_sub },
      { key: "validate" as Stage, n: "02", label: s.nav_validate, sub: s.nav_validate_sub },
      { key: "audit" as Stage, n: "03", label: s.nav_audit, sub: s.nav_audit_sub },
      { key: "report" as Stage, n: "04", label: s.nav_report, sub: s.nav_report_sub },
    ];
    const curOrder = order[stage];
    const stepList = steps.map((st) => {
      const so = order[st.key];
      const active = st.key === stage;
      const done = so < curOrder;
      return { ...st, active, done, numBg: active ? t.accent : t.panel2, numFg: active ? t.accentInk : t.sub, numBorder: active ? t.accent : t.line, bg: active ? t.accentSoft : "transparent", border: active ? t.accent : "transparent" };
    });

    const fmtSize = (b: number) => (b < 1024 * 1024 ? `${Math.round(b / 1024)} Ko` : `${(b / 1024 / 1024).toFixed(1)} Mo`);
    const totalBornes = parcels.reduce((n, p) => n + p.points.length, 0);
    const detection = file
      ? [
          { label: s.d_file, value: file.name, mono: "inherit" },
          { label: s.d_type, value: (file.type || "—").replace(/^(application|image)\//, "").toUpperCase(), mono: MONO },
          { label: s.d_size, value: fmtSize(file.size), mono: MONO },
          ...(projectId
            ? [
                { label: s.d_parcels, value: String(parcels.length), mono: MONO },
                { label: s.d_bornes_total, value: String(totalBornes), mono: MONO },
              ]
            : [{ label: s.d_crs, value: s.d_pending, mono: MONO }]),
        ]
      : [
          { label: s.d_file, value: s.d_nofile, mono: "inherit" },
          { label: s.d_geo, value: "—", mono: "inherit" },
          { label: s.d_crs, value: s.d_pending, mono: MONO },
        ];

    const themeList = (Object.keys(THEMES) as ThemeKey[]).map((k) => {
      const th = THEMES[k];
      const on = k === themeKey;
      return { key: k, name: th.name, swatch: th.accent, bg: on ? t.panel : "transparent", ring: on ? `inset 0 0 0 1.5px ${t.accent}` : "none" };
    });

    const geoms = parcels.map((p) => geom(p.points));
    const parcelTabs = parcels.map((p, i) => {
      const on = i === activeIdx;
      return { name: p.name, idx: i, bg: on ? t.accentSoft : t.panel, border: on ? t.accent : t.line, labelColor: t.ink, badge: p.confirmed ? s.confirmed.split(" ")[0] : "•", badgeBg: p.confirmed ? t.lowSoft : t.panel2, badgeFg: p.confirmed ? t.low : t.faint };
    });

    const ap = parcels[activeIdx];
    const ag = geoms[activeIdx];
    const apDelta = deltaInfo(num(ap.declaredM2), ag.area);
    const deltaColorMap: Record<string, string> = { low: t.low, mod: t.mod, high: t.high, none: t.sub };
    const rows = ap.points.map((pt, j) => {
      const tone = confTone(t, pt.confidence);
      return { idx: j, label: pt.label, x: pt.x, y: pt.y, confPct: `${Math.round(pt.confidence * 100)}%`, confBg: tone.bg, confFg: tone.fg };
    });
    const liveMetrics = [
      { label: s.live_valid, value: ag.valid ? "✓" : "—", color: ag.valid ? t.low : t.faint },
      { label: s.live_area, value: ag.area === null ? "—" : `${fmt(ag.area, 1)} m²`, color: t.ink },
      { label: s.live_per, value: ag.perimeter === null ? "—" : `${fmt(ag.perimeter, 1)} m`, color: t.ink },
      { label: s.live_delta, value: apDelta.pct === null ? "—" : `${apDelta.pct > 0 ? "+" : ""}${fmt(apDelta.pct, 1)}%`, color: deltaColorMap[apDelta.band] },
    ];
    const apWarnings: string[] = [];
    if (ap.crs === "EPSG:4326") apWarnings.push(lang === "fr" ? "Vérifiez l’ordre [longitude, latitude] : risque d’inversion X/Y." : "Check [longitude, latitude] order: possible X/Y swap.");
    if (apDelta.band === "high") apWarnings.push(lang === "fr" ? "Écart surface supérieur à 5 % entre la valeur déclarée et calculée." : "Area deviation above 5% between declared and calculated value.");
    const avgConf = ap.points.reduce((a, b) => a + b.confidence, 0) / ap.points.length;
    if (avgConf < 0.8) apWarnings.push(lang === "fr" ? "Confiance OCR moyenne faible sur cette parcelle — contrôlez chaque borne." : "Low average OCR confidence on this parcel — check each corner.");

    const allConfirmed = parcels.every((p) => p.confirmed);
    let statusMsg = s.st_correct;
    if (allConfirmed) statusMsg = s.st_confirmed;
    else if (ap.confirmed) statusMsg = s.st_need;

    const active = {
      declaredRaw: ap.declaredRaw,
      declaredM2: ap.declaredM2,
      crs: ap.crs,
      rows,
      pointCount: ap.points.length,
      liveMetrics,
      warnings: apWarnings,
      hasWarnings: apWarnings.length > 0,
      confirmLabel: ap.confirmed ? s.confirmed : s.confirm,
      confirmBg: ap.confirmed ? t.lowSoft : t.panel,
      confirmFg: ap.confirmed ? t.low : t.ink,
      confirmBorder: ap.confirmed ? t.low : t.line,
    };

    // audit
    const auditParcels = parcels.map((p, i) => {
      const g = geoms[i];
      const dd = deltaInfo(num(p.declaredM2), g.area);
      const band = dd.band;
      const tagMap: Record<string, string> = { low: s.risk_low, mod: s.risk_mod, high: s.risk_high, none: s.risk_ins };
      const colorMap: Record<string, string> = { low: t.low, mod: t.mod, high: t.high, none: t.faint };
      const softMap: Record<string, string> = { low: t.lowSoft, mod: t.modSoft, high: t.highSoft, none: t.panel2 };
      return {
        name: p.name,
        declared: `${fmt(num(p.declaredM2), 0)} m²`,
        calc: g.area === null ? "—" : `${fmt(g.area, 1)} m²`,
        delta: dd.pct === null ? "—" : `${dd.pct > 0 ? "+" : ""}${fmt(dd.pct, 2)}%`,
        deltaColor: colorMap[band],
        perimeter: g.perimeter === null ? "—" : `${fmt(g.perimeter, 1)} m`,
        points: String(p.points.length),
        tag: tagMap[band],
        tagBg: softMap[band],
        tagFg: colorMap[band],
        band,
      };
    });
    const allConf = parcels.flatMap((p) => p.points.map((pt) => pt.confidence));
    const ocrScore = Math.round(Math.min(1, allConf.reduce((a, b) => a + b, 0) / Math.max(allConf.length, 1) + 0.04) * 100);
    let tech = 100;
    geoms.forEach((g) => {
      if (!g.valid) tech -= 40;
    });
    const maxBand = auditParcels.reduce((m, p) => Math.max(m, p.band === "high" ? 3 : p.band === "mod" ? 2 : 1), 1);
    if (maxBand === 3) tech -= 34;
    else if (maxBand === 2) tech -= 15;
    tech = Math.max(0, Math.min(100, tech));
    const overall = Math.min(ocrScore, tech);
    const riskKey = overall >= 85 ? "low" : overall >= 65 ? "mod" : overall >= 40 ? "high" : "ins";
    const riskMap: Record<string, { l: string; c: string; soft: string; h: string }> = {
      low: { l: s.risk_low, c: t.low, soft: t.lowSoft, h: s.hint_low },
      mod: { l: s.risk_mod, c: t.mod, soft: t.modSoft, h: s.hint_mod },
      high: { l: s.risk_high, c: t.high, soft: t.highSoft, h: s.hint_high },
      ins: { l: s.risk_ins, c: t.faint, soft: t.panel2, h: s.hint_ins },
    };
    const rk = riskMap[riskKey];
    const C = 2 * Math.PI * 32;
    const audit = {
      ocrScore,
      techScore: tech,
      ocrColor: ocrScore >= 85 ? t.low : ocrScore >= 65 ? t.mod : t.high,
      techColor: tech >= 85 ? t.low : tech >= 65 ? t.mod : t.high,
      ocrDash: `${((C * ocrScore) / 100).toFixed(1)} ${C.toFixed(1)}`,
      techDash: `${((C * tech) / 100).toFixed(1)} ${C.toFixed(1)}`,
      riskLabel: rk.l,
      riskColor: rk.c,
      riskSoft: rk.soft,
      riskHint: rk.h,
      parcels: auditParcels,
    };

    const findings: { icon: string; color: string; soft: string; title: string; detail: string }[] = [];
    auditParcels.forEach((p) => {
      if (p.band === "high") findings.push({ icon: "!", color: t.high, soft: t.highSoft, title: (lang === "fr" ? "Écart surface élevé — " : "High area deviation — ") + p.name, detail: lang === "fr" ? `Surface calculée éloignée de la valeur déclarée (${p.delta}). Contrôle terrain recommandé.` : `Calculated area far from declared value (${p.delta}). Field check recommended.` });
      else if (p.band === "mod") findings.push({ icon: "~", color: t.mod, soft: t.modSoft, title: (lang === "fr" ? "Écart surface modéré — " : "Moderate area deviation — ") + p.name, detail: lang === "fr" ? `Écart de ${p.delta} à confirmer avec le géomètre.` : `Deviation of ${p.delta} to confirm with the surveyor.` });
    });
    findings.push({ icon: "i", color: t.sub, soft: t.panel2, title: lang === "fr" ? "Aucune référence cadastrale" : "No cadastral reference", detail: lang === "fr" ? "Le levé n’a pas été comparé à une référence cadastrale officielle (ANDF / Cadastre.bj)." : "The survey was not compared to an official cadastral reference (ANDF / Cadastre.bj)." });
    if (findings.length === 1) findings.unshift({ icon: "✓", color: t.low, soft: t.lowSoft, title: lang === "fr" ? "Géométrie cohérente" : "Consistent geometry", detail: lang === "fr" ? "Toutes les parcelles ferment et leurs surfaces concordent avec les valeurs déclarées." : "All parcels close and their areas match the declared values." });

    const repG = geoms[0];
    const reportSegs = (repG.segs || []).map((sg) => ({ from: sg.from, to: sg.to, len: `${fmt(sg.len, 2)} m` }));

    const confirmedParcels = parcels.filter((p) => p.confirmed);
    const map = buildMap(t, confirmedParcels.length ? confirmedParcels : parcels, mapSat);
    const today = new Date().toLocaleDateString(lang === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "short", year: "numeric" });

    return { stepList, detection, themeList, parcelTabs, active, statusMsg, allConfirmed, audit, findings, reportSegs, map, today };
  }, [stage, themeKey, lang, activeIdx, mapSat, parcels, file, projectId, t, s]);

  // Audit AFFICHÉ : résultat du backend si disponible (= la source du PDF, donc cohérent),
  // sinon le calcul client (mode démo sans projet). Les scores backend remplacent les
  // scores client (le score d'extraction client = moyenne des confidences, nulle sur
  // l'OCR réel → toujours bas). Le détail par parcelle (géométrie) reste cohérent.
  const auditView = useMemo(() => {
    if (!auditResult) return view.audit;
    const ar = auditResult;
    const C = 2 * Math.PI * 32;
    const sc = (n: number) => (n >= 85 ? t.low : n >= 65 ? t.mod : t.high);
    const riskMap: Record<string, { l: string; c: string; soft: string; h: string }> = {
      low: { l: s.risk_low, c: t.low, soft: t.lowSoft, h: s.hint_low },
      moderate: { l: s.risk_mod, c: t.mod, soft: t.modSoft, h: s.hint_mod },
      high: { l: s.risk_high, c: t.high, soft: t.highSoft, h: s.hint_high },
    };
    const rk = riskMap[ar.risk_level] ?? { l: s.risk_ins, c: t.faint, soft: t.panel2, h: s.hint_ins };
    const ocrNull = isExtractionScoreNull(ar.extraction_score);
    return {
      ...view.audit,
      ocrScore: ar.extraction_score,
      ocrScoreNull: ocrNull,
      ocrScoreStatus: ar.extraction_score_status,
      techScore: ar.technical_score,
      ocrColor: ocrNull ? t.faint : sc(ar.extraction_score as number),
      techColor: sc(ar.technical_score),
      // Score null → jauge vide (0 dash) ; on n'affichera PAS de valeur numérique.
      ocrDash: ocrNull ? `0 ${C.toFixed(1)}` : `${((C * (ar.extraction_score as number)) / 100).toFixed(1)} ${C.toFixed(1)}`,
      techDash: `${((C * ar.technical_score) / 100).toFixed(1)} ${C.toFixed(1)}`,
      riskLabel: rk.l,
      riskColor: rk.c,
      riskSoft: rk.soft,
      riskHint: rk.h,
    };
  }, [auditResult, view.audit, t, s]);

  // ---- styles réutilisables ----
  const panelCard: CSSProperties = { background: t.panel, border: `1px solid ${t.line}`, borderRadius: 16, boxShadow: t.shadow };
  const inputStyle: CSSProperties = { border: `1px solid ${t.line}`, background: t.panel2, borderRadius: 9, padding: "9px 11px", fontSize: 13.5, color: t.ink };
  const labelStyle: CSSProperties = { display: "flex", flexDirection: "column", gap: 5, fontSize: 12, color: t.sub, fontWeight: 500 };
  const eyebrow = (txt: string) => (
    <div style={{ fontFamily: MONO, fontSize: 11, letterSpacing: ".14em", textTransform: "uppercase", color: t.accent, marginBottom: 7 }}>{txt}</div>
  );
  const arrow = (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8H13M13 8L8.5 3.5M13 8L8.5 12.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /></svg>
  );

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", fontFamily: "'IBM Plex Sans', system-ui, sans-serif", background: t.bg, color: t.ink, overflow: "hidden", WebkitFontSmoothing: "antialiased" }}>
      {/* TOP BAR */}
      <header style={{ flex: "none", height: 58, display: "flex", alignItems: "center", justifyContent: "space-between", padding: "0 20px", background: t.panel, borderBottom: `1px solid ${t.line}`, zIndex: 5 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
          <svg width="26" height="26" viewBox="0 0 26 26" fill="none">
            <circle cx="13" cy="13" r="11.5" stroke={t.accent} strokeWidth="1.4" />
            <path d="M13 2.5V23.5M2.5 13H23.5" stroke={t.accent} strokeWidth="1.1" opacity="0.55" />
            <circle cx="13" cy="13" r="3.4" fill={t.accent} />
          </svg>
          <div style={{ display: "flex", alignItems: "baseline", gap: 7 }}>
            <span style={{ fontWeight: 700, fontSize: 16, letterSpacing: "-.01em" }}>TopoAudit</span>
            <span style={{ fontFamily: MONO, fontSize: 10, fontWeight: 500, letterSpacing: ".14em", textTransform: "uppercase", color: t.accent, border: `1px solid ${t.accent}`, padding: "2px 6px", borderRadius: 4 }}>Bénin</span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, padding: "5px 11px", background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 8 }}>
            <span style={{ width: 7, height: 7, borderRadius: "50%", background: t.low }} />
            <span style={{ fontSize: 12.5, color: t.sub }}>{s.project_meta}</span>
            <span style={{ fontSize: 12.5, fontWeight: 600 }}>{projectName}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 3, padding: 3, background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 9 }}>
            {view.themeList.map((th) => (
              <button key={th.key} onClick={() => setThemeKey(th.key)} title={th.name} style={{ width: 24, height: 24, border: "none", borderRadius: 6, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", background: th.bg, boxShadow: th.ring }}>
                <span style={{ width: 13, height: 13, borderRadius: 4, background: th.swatch, border: "1px solid rgba(128,128,128,.35)" }} />
              </button>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 9, overflow: "hidden", fontFamily: MONO, fontSize: 11.5, fontWeight: 600 }}>
            <button onClick={() => setLang("fr")} style={{ border: "none", cursor: "pointer", padding: "6px 11px", background: lang === "fr" ? t.accent : "transparent", color: lang === "fr" ? t.accentInk : t.sub }}>FR</button>
            <button onClick={() => setLang("en")} style={{ border: "none", cursor: "pointer", padding: "6px 11px", background: lang === "en" ? t.accent : "transparent", color: lang === "en" ? t.accentInk : t.sub }}>EN</button>
          </div>
          <div style={{ position: "relative" }}>
            {token ? (
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                <span style={{ color: t.low, fontWeight: 600 }}>● {lang === "fr" ? "Connecté" : "Signed in"}</span>
                <button onClick={doLogout} style={{ border: `1px solid ${t.line}`, background: t.panel2, borderRadius: 8, padding: "5px 10px", fontSize: 11.5, cursor: "pointer", color: t.sub }}>{lang === "fr" ? "Déconnexion" : "Sign out"}</button>
              </div>
            ) : (
              <button onClick={() => setAuthOpen((v) => !v)} style={{ border: `1px solid ${t.line}`, background: t.panel2, borderRadius: 8, padding: "6px 12px", fontSize: 12, fontWeight: 600, cursor: "pointer", color: t.ink }}>{lang === "fr" ? "Connexion" : "Sign in"}</button>
            )}
            {authOpen && !token && (
              <div style={{ position: "absolute", right: 0, top: 40, width: 244, background: t.panel, border: `1px solid ${t.line}`, borderRadius: 12, boxShadow: t.shadow, padding: 14, display: "flex", flexDirection: "column", gap: 8, zIndex: 20 }}>
                <div style={{ fontSize: 12, fontWeight: 600 }}>{lang === "fr" ? "Authentification" : "Authentication"}</div>
                <input value={authEmail} onChange={(e) => setAuthEmail(e.target.value)} placeholder="email" style={{ border: `1px solid ${t.line}`, background: t.panel2, borderRadius: 8, padding: "7px 9px", fontSize: 12.5, color: t.ink }} />
                <input value={authPwd} onChange={(e) => setAuthPwd(e.target.value)} type="password" placeholder={lang === "fr" ? "mot de passe (8+)" : "password (8+)"} style={{ border: `1px solid ${t.line}`, background: t.panel2, borderRadius: 8, padding: "7px 9px", fontSize: 12.5, color: t.ink }} />
                <div style={{ display: "flex", gap: 6 }}>
                  <button onClick={() => doAuth("login")} style={{ flex: 1, border: "none", background: t.accent, color: t.accentInk, borderRadius: 8, padding: "7px 0", fontSize: 12, fontWeight: 600, cursor: "pointer" }}>{lang === "fr" ? "Se connecter" : "Log in"}</button>
                  <button onClick={() => doAuth("register")} style={{ flex: 1, border: `1px solid ${t.line}`, background: t.panel2, color: t.ink, borderRadius: 8, padding: "7px 0", fontSize: 12, cursor: "pointer" }}>{lang === "fr" ? "Créer" : "Register"}</button>
                </div>
              </div>
            )}
          </div>
        </div>
      </header>

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        {/* SIDEBAR */}
        <aside style={{ flex: "none", width: 248, background: t.panel, borderRight: `1px solid ${t.line}`, display: "flex", flexDirection: "column", padding: "18px 14px", gap: 6 }}>
          <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".16em", textTransform: "uppercase", color: t.faint, padding: "4px 8px 8px" }}>{s.workflow}</div>
          {view.stepList.map((st) => (
            <button key={st.key} onClick={() => setStage(st.key)} style={{ display: "flex", alignItems: "center", gap: 12, textAlign: "left", border: `1px solid ${st.border}`, background: st.bg, borderRadius: 11, padding: "11px 12px", cursor: "pointer", transition: "background .14s,border-color .14s" }}>
              <span style={{ flex: "none", width: 30, height: 30, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: MONO, fontSize: 12, fontWeight: 600, background: st.numBg, color: st.numFg, border: `1px solid ${st.numBorder}` }}>{st.n}</span>
              <span style={{ display: "flex", flexDirection: "column", gap: 1, minWidth: 0 }}>
                <span style={{ fontSize: 13.5, fontWeight: 600, color: t.ink }}>{st.label}</span>
                <span style={{ fontSize: 11, color: t.sub }}>{st.sub}</span>
              </span>
              {st.done && (
                <svg width="15" height="15" viewBox="0 0 16 16" fill="none" style={{ marginLeft: "auto", flex: "none" }}><path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke={t.accent} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /></svg>
              )}
            </button>
          ))}
          <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 9, padding: 13, background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 12 }}>
            <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: ".14em", textTransform: "uppercase", color: t.faint }}>{s.dossier}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span style={{ color: t.sub }}>{s.f_commune}</span><span style={{ fontWeight: 600 }}>{commune}</span></div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span style={{ color: t.sub }}>{s.d_crs}</span><span style={{ fontFamily: MONO, fontWeight: 600 }}>{displayedCrs ?? (lang === "fr" ? "CRS à confirmer" : "CRS to confirm")}</span></div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12 }}><span style={{ color: t.sub }}>{s.d_parcels}</span><span style={{ fontWeight: 600 }}>{parcels.length}</span></div>
            </div>
          </div>
        </aside>

        {/* MAIN */}
        <main style={{ flex: 1, minWidth: 0, overflow: "auto", padding: "26px 30px 60px" }}>
          <div style={{ maxWidth: 1060, margin: "0 auto" }}>
            {/* STAGE 1 — INTAKE */}
            {stage === "intake" && (
              <div>
                <div style={{ marginBottom: 22 }}>
                  {eyebrow(`${s.step_label} 01 · ${s.nav_intake}`)}
                  <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 700, letterSpacing: "-.015em" }}>{s.intake_title}</h1>
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: t.sub, maxWidth: 620 }}>{s.intake_sub}</p>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, alignItems: "start" }}>
                  <section style={{ ...panelCard, padding: 20 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 15, display: "flex", alignItems: "center", gap: 8 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: t.accent }} />{s.project_ctx}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 13 }}>
                      <label style={labelStyle}>{s.f_project}
                        <input value={projectName} onChange={(e) => setProjectName(e.target.value)} style={{ ...inputStyle, fontWeight: 500 }} />
                      </label>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 90px", gap: 11 }}>
                        <label style={labelStyle}>{s.f_commune}
                          <input value={commune} onChange={(e) => setCommune(e.target.value)} style={inputStyle} />
                        </label>
                        <label style={labelStyle}>{s.f_country}
                          <div style={{ ...inputStyle, fontFamily: MONO, fontWeight: 600 }}>BJ</div>
                        </label>
                      </div>
                      <label style={labelStyle}>{s.f_notes}
                        <input value={notes} onChange={(e) => setNotes(e.target.value)} style={inputStyle} />
                      </label>
                    </div>
                  </section>
                  <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div onClick={() => fileInputRef.current?.click()} role="button" tabIndex={0} style={{ background: t.panel, border: `1.5px dashed ${t.accent}`, borderRadius: 16, padding: 22, textAlign: "center", boxShadow: t.shadow, cursor: "pointer" }}>
                      <input ref={fileInputRef} type="file" accept="image/png,image/jpeg,application/pdf" style={{ display: "none" }} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                      <div style={{ width: 46, height: 46, borderRadius: 12, background: t.accentSoft, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 11px" }}>
                        <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M12 16V4M12 4L7 9M12 4L17 9" stroke={t.accent} strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" /><path d="M4 16V19A1 1 0 0 0 5 20H19A1 1 0 0 0 20 19V16" stroke={t.accent} strokeWidth="1.7" strokeLinecap="round" /></svg>
                      </div>
                      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{s.drop_title}</div>
                      <div style={{ fontSize: 12, color: t.sub }}>{s.drop_hint}</div>
                      <div style={{ marginTop: 13, display: "inline-flex", alignItems: "center", gap: 8, padding: "7px 12px", background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 8, fontSize: 12, fontFamily: MONO }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: file ? t.low : t.accent }} />{file ? file.name : lang === "fr" ? "Cliquez pour choisir un plan" : "Click to choose a plan"}
                      </div>
                    </div>
                    <div style={{ ...panelCard, padding: 18 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 13, display: "flex", alignItems: "center", gap: 8, color: t.sub }}><span style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".1em", color: t.accent }}>OCR</span>{s.detected}</div>
                      <div>
                        {view.detection.map((d, i) => (
                          <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: `1px solid ${t.line2}` }}>
                            <span style={{ fontSize: 12.5, color: t.sub }}>{d.label}</span>
                            <span style={{ fontSize: 12.5, fontWeight: 600, fontFamily: d.mono }}>{d.value}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </section>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 14, marginTop: 20 }}>
                  {errorMsg && <span style={{ fontSize: 12.5, color: t.high }}>{errorMsg}</span>}
                  <button onClick={runOcr} disabled={busy === "ocr"} style={{ display: "inline-flex", alignItems: "center", gap: 9, background: t.accent, color: t.accentInk, border: "none", borderRadius: 11, padding: "12px 20px", fontSize: 14, fontWeight: 600, cursor: busy === "ocr" ? "wait" : "pointer", opacity: busy === "ocr" ? 0.7 : 1, boxShadow: t.shadow }}>{busy === "ocr" ? (lang === "fr" ? "Extraction OCR…" : "Running OCR…") : s.btn_ocr}{busy === "ocr" ? null : arrow}</button>
                </div>
              </div>
            )}

            {/* STAGE 2 — VALIDATE */}
            {stage === "validate" && (
              <div>
                <div style={{ marginBottom: 20 }}>
                  {eyebrow(`${s.step_label} 02 · ${s.nav_validate}`)}
                  <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 700, letterSpacing: "-.015em" }}>{s.val_title}</h1>
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: t.sub, maxWidth: 680 }}>{s.val_sub}</p>
                </div>
                {ocrInfo && (
                  <div style={{ marginBottom: 16 }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                      <span style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "5px 12px", borderRadius: 999, fontSize: 12.5, fontWeight: 700, background: ocrInfo.isMock ? "#fef3c7" : "#dcfce7", color: ocrInfo.isMock ? "#92400e" : "#166534", border: `1px solid ${ocrInfo.isMock ? "#f59e0b" : "#22c55e"}` }}>
                        {ocrInfo.isMock ? (lang === "fr" ? "⚠ Mock OCR (démo)" : "⚠ Mock OCR (demo)") : (lang === "fr" ? "✓ OCR réel" : "✓ Real OCR")}
                        {` · ${ocrInfo.provider}`}
                      </span>
                      <span style={{ fontSize: 12.5, color: t.sub, fontFamily: MONO }}>CRS : {ocrInfo.crs}</span>
                      <span style={{ fontSize: 12.5, color: t.sub, fontFamily: MONO }}>{lang === "fr" ? "Statut extraction" : "Extraction status"} : {ocrInfo.scoreStatus}</span>
                    </div>
                    {ocrInfo.scoreStatus === "needs_human_validation" && (
                      <div style={{ marginTop: 10, padding: "8px 12px", borderRadius: 8, fontSize: 12.5, lineHeight: 1.45, background: "#fef3c7", color: "#92400e", border: "1px solid #f59e0b" }}>
                        {lang === "fr"
                          ? "⚠ Validation humaine requise : aucun score d'extraction fiable. Vérifiez chaque borne et le CRS avant de lancer l'audit."
                          : "⚠ Human validation required: no reliable extraction score. Check every corner and the CRS before running the audit."}
                      </div>
                    )}
                  </div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "380px 1fr", gap: 18, alignItems: "start" }}>
                  <section style={{ ...panelCard, overflow: "hidden", position: "sticky", top: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "11px 14px", borderBottom: `1px solid ${t.line}` }}>
                      <span style={{ fontSize: 12.5, fontWeight: 600 }}>{s.scan}</span>
                      <div style={{ display: "flex", gap: 4, fontFamily: MONO, fontSize: 12 }}>
                        <span style={{ width: 24, height: 24, border: `1px solid ${t.line}`, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", color: t.sub }}>−</span>
                        <span style={{ width: 24, height: 24, border: `1px solid ${t.line}`, borderRadius: 6, display: "flex", alignItems: "center", justifyContent: "center", color: t.sub }}>+</span>
                      </div>
                    </div>
                    <div style={{ position: "relative", aspectRatio: "3/4", background: t.panel2, display: "flex", alignItems: "center", justifyContent: "center" }}>
                      {filePreview ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={filePreview} alt={file?.name ?? "scan"} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", background: t.panel2 }} />
                      ) : (
                        <svg width="100%" height="100%" viewBox="0 0 300 400" preserveAspectRatio="xMidYMid slice" style={{ position: "absolute", inset: 0 }}>
                          <defs><pattern id="scanhatch" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="7" stroke={t.line} strokeWidth="3" /></pattern></defs>
                          <rect width="300" height="400" fill="url(#scanhatch)" opacity="0.5" />
                          <rect x="22" y="22" width="256" height="356" fill="none" stroke={t.sub} strokeWidth="1" opacity="0.4" />
                          <rect x="34" y="40" width="150" height="9" fill={t.sub} opacity="0.3" />
                          <rect x="34" y="56" width="96" height="6" fill={t.sub} opacity="0.2" />
                          <polygon points="95,150 200,135 215,250 120,275 70,205" fill={t.accentSoft} stroke={t.accent} strokeWidth="1.6" />
                          {[[95, 150], [200, 135], [215, 250], [120, 275], [70, 205]].map(([cx, cy], i) => (<circle key={i} cx={cx} cy={cy} r="3" fill={t.accent} />))}
                        </svg>
                      )}
                      <div style={{ position: "absolute", left: 11, bottom: 11, fontFamily: MONO, fontSize: 10, color: t.sub, background: t.panel, padding: "3px 7px", borderRadius: 5, border: `1px solid ${t.line}`, maxWidth: "calc(100% - 22px)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{file ? file.name : s.scan_ph}</div>
                    </div>
                  </section>

                  <section style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div style={{ display: "flex", gap: 6 }}>
                      {view.parcelTabs.map((p) => (
                        <button key={p.idx} onClick={() => setActiveIdx(p.idx)} style={{ display: "flex", alignItems: "center", gap: 9, border: `1px solid ${p.border}`, background: p.bg, borderRadius: 10, padding: "9px 14px", cursor: "pointer" }}>
                          <span style={{ fontSize: 13, fontWeight: 600, color: p.labelColor }}>{p.name}</span>
                          <span style={{ fontSize: 10.5, fontWeight: 600, fontFamily: MONO, padding: "2px 7px", borderRadius: 20, background: p.badgeBg, color: p.badgeFg }}>{p.badge}</span>
                        </button>
                      ))}
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 11 }}>
                      <label style={{ ...labelStyle, fontSize: 11.5 }}>{s.surface_ocr}
                        <input value={view.active.declaredRaw} onChange={(e) => updateField(activeIdx, "declaredRaw", e.target.value)} style={{ ...inputStyle, background: t.panel, fontSize: 13, fontFamily: MONO }} />
                      </label>
                      <label style={{ ...labelStyle, fontSize: 11.5 }}>{s.surface_m2}
                        <input value={view.active.declaredM2} onChange={(e) => updateField(activeIdx, "declaredM2", e.target.value)} inputMode="decimal" style={{ ...inputStyle, background: t.panel, fontSize: 13, fontFamily: MONO }} />
                      </label>
                      <label style={{ ...labelStyle, fontSize: 11.5 }}>{s.crs}
                        <select value={view.active.crs === "local" ? "LOCAL_ONLY" : view.active.crs} onChange={(e) => updateField(activeIdx, "crs", e.target.value)} style={{ ...inputStyle, background: t.panel, fontSize: 13 }}>
                          <option value="EPSG:32631">EPSG:32631 — WGS84 / UTM 31N</option>
                          <option value="EPSG:4326">EPSG:4326 — longitude / latitude</option>
                          <option value="LOCAL_ONLY">LOCAL_ONLY — coordonnées locales, pas de fond satellite</option>
                          <option value="UNKNOWN_CRS">UNKNOWN_CRS — CRS inconnu, à confirmer</option>
                          <option value="NEEDS_GEOREFERENCING">NEEDS_GEOREFERENCING — rattachement requis</option>
                        </select>
                      </label>
                    </div>
                    <div style={{ ...panelCard, borderRadius: 14, overflow: "hidden" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead>
                          <tr style={{ background: t.panel2 }}>
                            {[s.c_borne, s.c_x, s.c_y, s.c_conf, ""].map((h, i) => (
                              <th key={i} style={{ textAlign: i === 3 ? "center" : "left", padding: "10px 14px", fontSize: 10.5, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: t.faint, width: i === 0 ? 74 : i === 3 ? 96 : i === 4 ? 42 : undefined }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {view.active.rows.map((r) => (
                            <tr key={r.idx} style={{ borderTop: `1px solid ${t.line2}` }}>
                              <td style={{ padding: "6px 10px 6px 14px" }}><input className="ta-cell" value={r.label} onChange={(e) => updatePoint(activeIdx, r.idx, "label", e.target.value)} style={{ width: "100%", border: "1px solid transparent", background: "transparent", borderRadius: 6, padding: "6px 7px", fontSize: 13, fontWeight: 600, fontFamily: MONO, color: t.ink }} /></td>
                              <td style={{ padding: "6px 10px" }}><input className="ta-cell" value={r.x} onChange={(e) => updatePoint(activeIdx, r.idx, "x", e.target.value)} inputMode="decimal" style={{ width: "100%", border: "1px solid transparent", background: "transparent", borderRadius: 6, padding: "6px 7px", fontSize: 13, fontFamily: MONO, color: t.ink }} /></td>
                              <td style={{ padding: "6px 10px" }}><input className="ta-cell" value={r.y} onChange={(e) => updatePoint(activeIdx, r.idx, "y", e.target.value)} inputMode="decimal" style={{ width: "100%", border: "1px solid transparent", background: "transparent", borderRadius: 6, padding: "6px 7px", fontSize: 13, fontFamily: MONO, color: t.ink }} /></td>
                              <td style={{ padding: "6px 10px", textAlign: "center" }}><span style={{ display: "inline-block", fontSize: 11, fontWeight: 600, fontFamily: MONO, padding: "3px 8px", borderRadius: 20, background: r.confBg, color: r.confFg }}>{r.confPct}</span></td>
                              <td style={{ padding: "6px 10px", textAlign: "center" }}><button onClick={() => removePoint(activeIdx, r.idx)} title={s.remove} style={{ width: 26, height: 26, border: `1px solid ${t.line}`, background: "transparent", borderRadius: 7, cursor: "pointer", color: t.faint, display: "inline-flex", alignItems: "center", justifyContent: "center" }}><svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg></button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 14px", borderTop: `1px solid ${t.line2}`, background: t.panel2 }}>
                        <button onClick={() => addPoint(activeIdx)} style={{ display: "inline-flex", alignItems: "center", gap: 6, border: `1px solid ${t.line}`, background: t.panel, borderRadius: 8, padding: "7px 12px", fontSize: 12.5, fontWeight: 600, color: t.accent, cursor: "pointer" }}>
                          <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 3V13M3 8H13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>{s.add_borne}
                        </button>
                        <span style={{ fontSize: 11.5, color: t.sub, fontFamily: MONO }}>{view.active.pointCount} {s.bornes}</span>
                      </div>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 11 }}>
                      {view.active.liveMetrics.map((m, i) => (
                        <div key={i} style={{ background: t.panel, border: `1px solid ${t.line}`, borderRadius: 12, padding: "12px 13px" }}>
                          <div style={{ fontSize: 10.5, letterSpacing: ".05em", textTransform: "uppercase", color: t.faint, marginBottom: 6 }}>{m.label}</div>
                          <div style={{ fontSize: 16, fontWeight: 600, fontFamily: MONO, color: m.color }}>{m.value}</div>
                        </div>
                      ))}
                    </div>
                    {view.active.hasWarnings && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        {view.active.warnings.map((w, i) => (
                          <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "11px 13px", background: t.modSoft, border: `1px solid ${t.line}`, borderLeft: `3px solid ${t.mod}`, borderRadius: 10 }}>
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" style={{ flex: "none", marginTop: 1 }}><path d="M8 1.5L15 14H1L8 1.5Z" stroke={t.mod} strokeWidth="1.3" strokeLinejoin="round" /><path d="M8 6V9.5M8 11.5V11.6" stroke={t.mod} strokeWidth="1.4" strokeLinecap="round" /></svg>
                            <span style={{ fontSize: 12.5, lineHeight: 1.5, color: t.ink }}>{w}</span>
                          </div>
                        ))}
                      </div>
                    )}
                    <div style={{ display: "flex", gap: 11, justifyContent: "flex-end", alignItems: "center" }}>
                      <span style={{ fontSize: 12, color: errorMsg ? t.high : t.sub, marginRight: "auto" }}>{errorMsg || view.statusMsg}</span>
                      <button onClick={() => confirmParcel(activeIdx)} style={{ border: `1px solid ${view.active.confirmBorder}`, background: view.active.confirmBg, color: view.active.confirmFg, borderRadius: 10, padding: "11px 18px", fontSize: 13.5, fontWeight: 600, cursor: "pointer" }}>{view.active.confirmLabel}</button>
                      <button onClick={() => runAudit(view.allConfirmed)} disabled={!view.allConfirmed || busy === "audit"} style={{ display: "inline-flex", alignItems: "center", gap: 8, border: "none", background: view.allConfirmed ? t.accent : t.panel2, color: view.allConfirmed ? t.accentInk : t.faint, borderRadius: 10, padding: "11px 18px", fontSize: 13.5, fontWeight: 600, cursor: view.allConfirmed ? (busy === "audit" ? "wait" : "pointer") : "not-allowed", opacity: view.allConfirmed ? (busy === "audit" ? 0.7 : 1) : 0.6 }}>{busy === "audit" ? (lang === "fr" ? "Audit…" : "Auditing…") : s.btn_audit}{busy === "audit" ? null : arrow}</button>
                    </div>
                  </section>
                </div>
              </div>
            )}

            {/* STAGE 3 — AUDIT */}
            {stage === "audit" && (
              <div>
                <div style={{ marginBottom: 20 }}>
                  {eyebrow(`${s.step_label} 03 · ${s.nav_audit}`)}
                  <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 700, letterSpacing: "-.015em" }}>{s.audit_title}</h1>
                  <p style={{ margin: 0, fontSize: 14, lineHeight: 1.55, color: t.sub, maxWidth: 680 }}>{s.audit_sub}</p>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.2fr", gap: 16, marginBottom: 16 }}>
                  {[{ label: s.score_ocr, score: auditView.ocrScore, color: auditView.ocrColor, dash: auditView.ocrDash, nullScore: Boolean((auditView as { ocrScoreNull?: boolean }).ocrScoreNull) }, { label: s.score_tech, score: auditView.techScore, color: auditView.techColor, dash: auditView.techDash, nullScore: false }].map((g, i) => (
                    <div key={i} style={{ ...panelCard, padding: 20, display: "flex", alignItems: "center", gap: 16 }}>
                      <svg width="76" height="76" viewBox="0 0 76 76">
                        <circle cx="38" cy="38" r="32" fill="none" stroke={t.line} strokeWidth="7" />
                        {!g.nullScore && <circle cx="38" cy="38" r="32" fill="none" stroke={g.color} strokeWidth="7" strokeLinecap="round" strokeDasharray={g.dash} transform="rotate(-90 38 38)" />}
                      </svg>
                      <div>
                        <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", color: t.faint, marginBottom: 4 }}>{g.label}</div>
                        {g.nullScore ? (
                          <div style={{ fontSize: 17, fontWeight: 700, color: t.high, lineHeight: 1.1 }}>{extractionScoreText(null, lang)}</div>
                        ) : (
                          <div style={{ fontSize: 30, fontWeight: 700, fontFamily: MONO, lineHeight: 1 }}>{g.score}<span style={{ fontSize: 15, color: t.faint }}>/100</span></div>
                        )}
                      </div>
                    </div>
                  ))}
                  <div style={{ background: auditView.riskSoft, border: `1px solid ${auditView.riskColor}`, borderRadius: 16, padding: 20, boxShadow: t.shadow, display: "flex", flexDirection: "column", justifyContent: "center", gap: 6 }}>
                    <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", color: auditView.riskColor, fontWeight: 600 }}>{s.risk}</div>
                    <div style={{ fontSize: 24, fontWeight: 700, color: auditView.riskColor, letterSpacing: "-.01em" }}>{auditView.riskLabel}</div>
                    <div style={{ fontSize: 12, color: t.ink, opacity: 0.7 }}>{auditView.riskHint}</div>
                  </div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
                  <section style={{ ...panelCard, padding: 18 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>{s.per_parcel}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                      {auditView.parcels.map((p, i) => (
                        <div key={i} style={{ border: `1px solid ${t.line}`, borderRadius: 12, padding: 13, background: t.panel2 }}>
                          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 11 }}>
                            <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                            <span style={{ fontSize: 11, fontWeight: 600, fontFamily: MONO, padding: "3px 9px", borderRadius: 20, background: p.tagBg, color: p.tagFg }}>{p.tag}</span>
                          </div>
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(5,1fr)", gap: 8 }}>
                            {[{ l: s.m_declared, v: p.declared, c: t.ink }, { l: s.m_calc, v: p.calc, c: t.ink }, { l: s.m_delta, v: p.delta, c: p.deltaColor }, { l: s.m_per, v: p.perimeter, c: t.ink }, { l: s.m_pts, v: p.points, c: t.ink }].map((m, j) => (
                              <div key={j}><div style={{ fontSize: 9.5, textTransform: "uppercase", color: t.faint, marginBottom: 3 }}>{m.l}</div><div style={{ fontSize: 12, fontWeight: 600, fontFamily: MONO, color: m.c }}>{m.v}</div></div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                  <section style={{ ...panelCard, padding: 18 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 14 }}>{s.findings}</div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
                      {view.findings.map((f, i) => (
                        <div key={i} style={{ display: "flex", gap: 11, alignItems: "flex-start", padding: "11px 12px", background: f.soft, border: `1px solid ${t.line}`, borderLeft: `3px solid ${f.color}`, borderRadius: 10 }}>
                          <span style={{ flex: "none", width: 18, height: 18, borderRadius: 5, background: f.color, color: t.panel, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 700, marginTop: 1 }}>{f.icon}</span>
                          <div>
                            <div style={{ fontSize: 12.5, fontWeight: 600, marginBottom: 2 }}>{f.title}</div>
                            <div style={{ fontSize: 12, lineHeight: 1.45, color: t.sub }}>{f.detail}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </section>
                </div>
                <div style={{ display: "flex", gap: 12, alignItems: "flex-start", marginTop: 16, padding: "15px 17px", background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 14 }}>
                  <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style={{ flex: "none", marginTop: 1 }}><circle cx="10" cy="10" r="8.5" stroke={t.sub} strokeWidth="1.3" /><path d="M10 6V10.5M10 13.5V13.6" stroke={t.sub} strokeWidth="1.5" strokeLinecap="round" /></svg>
                  <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.55, color: t.sub }}>{s.disclaimer}</p>
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18 }}>
                  <button onClick={() => setStage("report")} style={{ display: "inline-flex", alignItems: "center", gap: 9, background: t.accent, color: t.accentInk, border: "none", borderRadius: 11, padding: "12px 20px", fontSize: 14, fontWeight: 600, cursor: "pointer", boxShadow: t.shadow }}>{s.btn_report}{arrow}</button>
                </div>
              </div>
            )}

            {/* STAGE 4 — REPORT */}
            {stage === "report" && (
              <div>
                <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 20, gap: 20 }}>
                  <div>
                    {eyebrow(`${s.step_label} 04 · ${s.nav_report}`)}
                    <h1 style={{ margin: "0 0 6px", fontSize: 26, fontWeight: 700, letterSpacing: "-.015em" }}>{s.report_title}</h1>
                    <p style={{ margin: 0, fontSize: 13.5, color: t.sub }}>{s.generated} {view.today} · {s.file} {file?.name ?? "—"}</p>
                  </div>
                  <button onClick={exportReport} disabled={busy === "export"} style={{ display: "inline-flex", alignItems: "center", gap: 8, background: t.accent, color: t.accentInk, border: "none", borderRadius: 11, padding: "11px 18px", fontSize: 13.5, fontWeight: 600, cursor: busy === "export" ? "wait" : "pointer", opacity: busy === "export" ? 0.7 : 1, flex: "none", boxShadow: t.shadow }}>
                    <svg width="15" height="15" viewBox="0 0 16 16" fill="none"><path d="M8 2V10M8 10L5 7M8 10L11 7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" /><path d="M3 11V13A1 1 0 0 0 4 14H12A1 1 0 0 0 13 13V11" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>{busy === "export" ? (lang === "fr" ? "Export…" : "Exporting…") : s.export_pdf}
                  </button>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1.15fr 1fr", gap: 18, alignItems: "start" }}>
                  {isGeoreferenced ? (
                  <section style={{ ...panelCard, overflow: "hidden" }}>
                    <ParcelMap parcels={geoParcels} title={s.map_title} description={lang === "fr" ? "Fond satellite Esri World Imagery." : "Esri World Imagery basemap."} />
                    <div style={{ padding: "8px 12px", fontSize: 11.5, lineHeight: 1.45, color: "#92400e", background: "#fef3c7", borderTop: "1px solid #f59e0b" }}>
                      {lang === "fr" ? "Fond satellite indicatif, non référence cadastrale." : "Indicative satellite background, not a cadastral reference."}
                    </div>
                  </section>
                  ) : (
                  <section style={{ ...panelCard, overflow: "hidden" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 15px", borderBottom: `1px solid ${t.line}` }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{s.map_title}</span>
                      <div style={{ display: "flex", background: t.panel2, border: `1px solid ${t.line}`, borderRadius: 8, overflow: "hidden", fontSize: 11.5, fontWeight: 600 }}>
                        <button onClick={() => setMapSat(false)} style={{ border: "none", cursor: "pointer", padding: "6px 13px", background: !mapSat ? t.accent : "transparent", color: !mapSat ? t.accentInk : t.sub }}>{s.map_plan}</button>
                        <button onClick={() => isGeoreferenced && setMapSat(true)} disabled={!isGeoreferenced} title={!isGeoreferenced ? s.map_local : undefined} style={{ border: "none", cursor: isGeoreferenced ? "pointer" : "not-allowed", padding: "6px 13px", background: mapSat ? t.accent : "transparent", color: mapSat ? t.accentInk : t.sub, opacity: isGeoreferenced ? 1 : 0.45 }}>{s.map_sat}</button>
                      </div>
                    </div>
                    <div style={{ position: "relative", background: view.map.bg }}>
                      <svg width="100%" viewBox="0 0 520 420" style={{ display: "block" }}>
                        <defs><pattern id="satstripe" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="9" height="9" fill={view.map.satA} /><line x1="0" y1="0" x2="0" y2="9" stroke={view.map.satB} strokeWidth="4.5" /></pattern></defs>
                        {view.map.sat && <rect x="0" y="0" width="520" height="420" fill="url(#satstripe)" opacity="0.55" />}
                        {view.map.grid.map((g: any, i: number) => (<line key={i} x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2} stroke={view.map.gridColor} strokeWidth="0.7" />))}
                        {view.map.parcels.map((pc: any, i: number) => (
                          <g key={i}>
                            <polygon points={pc.poly} fill={pc.fill} stroke={pc.stroke} strokeWidth="2" strokeLinejoin="round" />
                            {pc.segs.map((sg: any, j: number) => (<g key={j}><rect x={sg.rx} y={sg.ry} width={sg.rw} height="15" rx="3" fill={view.map.labelBg} /><text x={sg.x} y={sg.y} fontFamily={MONO} fontSize="9.5" fill={pc.stroke} textAnchor="middle">{sg.label}</text></g>))}
                            {pc.bornes.map((b: any, j: number) => (<g key={j}><rect x={b.rx} y={b.ry} width="7" height="7" fill={view.map.bg} stroke={pc.stroke} strokeWidth="1.6" /><text x={b.lx} y={b.ly} fontFamily={MONO} fontSize="10" fontWeight="600" fill={view.map.ink}>{b.label}</text></g>))}
                            <text x={pc.cx} y={pc.cy} fontFamily={MONO} fontSize="11" fontWeight="600" fill={pc.stroke} textAnchor="middle">{pc.name}</text>
                          </g>
                        ))}
                        <g transform="translate(486,34)"><circle r="17" fill={view.map.bg} stroke={view.map.gridColor} strokeWidth="1" /><path d="M0 -11L4 4L0 1L-4 4Z" fill={view.map.ink} /><text x="0" y="-18" fontFamily={MONO} fontSize="9" fontWeight="700" fill={view.map.ink} textAnchor="middle">N</text></g>
                        <g transform="translate(20,398)"><rect x="0" y="-5" width={view.map.scaleLen} height="5" fill={view.map.ink} /><rect x="0" y="-5" width={view.map.scaleHalf} height="5" fill={view.map.bg} stroke={view.map.ink} strokeWidth="0.8" /><text x="0" y="-9" fontFamily={MONO} fontSize="9" fill={view.map.ink}>0</text><text x={view.map.scaleLen} y="-9" fontFamily={MONO} fontSize="9" fill={view.map.ink} textAnchor="end">{view.map.scaleLabel}</text></g>
                      </svg>
                      {view.map.sat && <div style={{ position: "absolute", left: 12, top: 12, fontFamily: MONO, fontSize: 10, color: view.map.ink, background: view.map.bg, padding: "5px 9px", borderRadius: 6, border: `1px solid ${view.map.gridColor}`, maxWidth: 280, lineHeight: 1.4 }}>{s.sat_note}</div>}
                      {!isGeoreferenced && <div style={{ position: "absolute", left: 12, top: 12, fontFamily: MONO, fontSize: 10, color: "#92400e", background: "#fef3c7", padding: "5px 9px", borderRadius: 6, border: "1px solid #f59e0b", maxWidth: 300, lineHeight: 1.4 }}>{s.map_local}</div>}
                    </div>
                  </section>
                  )}
                  <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                    <div style={{ ...panelCard, padding: 18 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
                        <div style={{ flex: 1 }}><div style={{ fontSize: 11, textTransform: "uppercase", color: t.faint, letterSpacing: ".05em" }}>{s.score_ocr}</div>
                          {isExtractionScoreNull(auditView.ocrScore) ? (
                            <>
                              <div style={{ fontSize: 16, fontWeight: 700, color: t.high }}>{extractionScoreText(null, lang)}</div>
                              {(auditView as { ocrScoreStatus?: string }).ocrScoreStatus && <div style={{ fontSize: 10, color: t.faint, fontFamily: MONO }}>{(auditView as { ocrScoreStatus?: string }).ocrScoreStatus}</div>}
                            </>
                          ) : (
                            <div style={{ fontSize: 22, fontWeight: 700, fontFamily: MONO }}>{auditView.ocrScore}<span style={{ fontSize: 13, color: t.faint }}>/100</span></div>
                          )}
                        </div>
                        <div style={{ flex: 1 }}><div style={{ fontSize: 11, textTransform: "uppercase", color: t.faint, letterSpacing: ".05em" }}>{s.score_tech}</div><div style={{ fontSize: 22, fontWeight: 700, fontFamily: MONO }}>{auditView.techScore}<span style={{ fontSize: 13, color: t.faint }}>/100</span></div></div>
                        <div style={{ flex: "none", fontSize: 13, fontWeight: 700, padding: "7px 13px", borderRadius: 9, background: auditView.riskSoft, color: auditView.riskColor, border: `1px solid ${auditView.riskColor}` }}>{auditView.riskLabel}</div>
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 600, margin: "6px 0 9px" }}>{s.seg_table}</div>
                      <table style={{ width: "100%", borderCollapse: "collapse" }}>
                        <thead><tr>{[s.seg_from, s.seg_to, s.seg_len].map((h, i) => (<th key={i} style={{ textAlign: i === 2 ? "right" : "left", fontSize: 10, textTransform: "uppercase", color: t.faint, padding: "5px 6px", fontWeight: 600 }}>{h}</th>))}</tr></thead>
                        <tbody>
                          {view.reportSegs.map((sg, i) => (<tr key={i} style={{ borderTop: `1px solid ${t.line2}` }}><td style={{ padding: 6, fontSize: 12, fontFamily: MONO, fontWeight: 600 }}>{sg.from}</td><td style={{ padding: 6, fontSize: 12, fontFamily: MONO, fontWeight: 600 }}>{sg.to}</td><td style={{ padding: 6, fontSize: 12, fontFamily: MONO, textAlign: "right" }}>{sg.len}</td></tr>))}
                        </tbody>
                      </table>
                    </div>
                    <div style={{ background: t.accentSoft, border: `1px solid ${t.line}`, borderRadius: 14, padding: 16 }}>
                      <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 7, color: t.accent, display: "flex", alignItems: "center", gap: 7 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: t.accent }} />{s.recommendations}</div>
                      <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.6, color: t.ink }}>{s.reco_body}</p>
                    </div>
                    <div style={{ ...panelCard, borderRadius: 14, padding: 15 }}>
                      <div style={{ fontFamily: MONO, fontSize: 10, letterSpacing: ".12em", textTransform: "uppercase", color: t.faint, marginBottom: 9 }}>{s.tech_log}</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 5, fontFamily: MONO, fontSize: 11.5, color: t.sub }}>
                        <div>crs_source = {displayedCrs ?? "UNKNOWN_CRS"}</div>
                        <div>crs_geojson = EPSG:4326 · always_xy=true</div>
                        <div>transform = {isGeoreferenced ? "pyproj.Transformer → EPSG:4326" : "disabled"}</div>
                        <div>engine = topoaudit-geometry v0.1.0</div>
                      </div>
                    </div>
                  </section>
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
