from html import escape

from weasyprint import HTML

from app.extraction_score import SCORE_STATUS_NEEDS_HUMAN_VALIDATION
from app.workflow import AuditResponse, ParcelAuditResult

LEGAL_DISCLAIMER = (
    "Ce rapport est généré automatiquement à des fins d'audit technique préliminaire. "
    "Il ne constitue pas un avis juridique, ne remplace pas une vérification cadastrale "
    "officielle et ne confère aucun droit foncier. Toute décision juridique ou transaction "
    "doit être validée par les autorités compétentes et des professionnels habilités."
)


def _risk_label(risk_level: str) -> str:
    labels = {"low": "Faible", "moderate": "Modéré", "high": "Élevé"}
    return labels.get(risk_level, risk_level)


def _format_surface(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f} m²"


def _format_extraction_score(score: int | None, status: str) -> str:
    """Score sur 100, ou mention explicite quand la validation humaine est requise."""
    if score is None or status == SCORE_STATUS_NEEDS_HUMAN_VALIDATION:
        return "Validation humaine requise"
    return f"{score}/100"


_TERRITORY_LABELS = {
    "inside_benin": "OK — dans le territoire béninois",
    "outside_benin": "Hors Bénin — risque critique",
    "near_border_partial": "Chevauche la frontière — à vérifier",
    "not_applicable_local_crs": "Non applicable (CRS local/inconnu)",
    "invalid_geometry": "Géométrie invalide",
    "unknown": "—",
}


def _territory_label(status: str) -> str:
    return _TERRITORY_LABELS.get(status, status or "—")


def _territory_centroid(lon: float | None, lat: float | None) -> str:
    if lon is None or lat is None:
        return "—"
    return f"{lat:.5f}, {lon:.5f} (lat, lon)"


def _warning_list(warnings: list[str]) -> str:
    return "".join(f"<li>{escape(warning)}</li>" for warning in warnings)


def _parcel_card(parcel: ParcelAuditResult, index: int) -> str:
    warnings = parcel.warnings or ["Aucune alerte technique supplémentaire."]
    parcel_id = f"<p class=\"muted\">Identifiant : {escape(parcel.parcel_id)}</p>" if parcel.parcel_id else ""
    geometry_status = "Invalide" if parcel.invalid_geometry else "Validée"
    return f"""
        <section class="parcel-card">
            <h3>Parcelle {index} — {escape(parcel.label)}</h3>
            {parcel_id}
            <table>
                <tbody>
                    <tr><th>Surface déclarée</th><td>{escape(_format_surface(parcel.declared_surface_m2))}</td></tr>
                    <tr><th>Surface calculée</th><td>{escape(_format_surface(parcel.calculated_surface_m2))}</td></tr>
                    <tr><th>Score d'extraction</th><td>{escape(_format_extraction_score(parcel.extraction_score, parcel.extraction_score_status))}</td></tr>
                    <tr><th>Bornes validées humainement</th><td>{"Oui" if parcel.human_validated else "Non"}</td></tr>
                    <tr><th>Score technique</th><td>{parcel.technical_score}/100</td></tr>
                    <tr><th>Niveau de risque</th><td>{escape(_risk_label(parcel.risk_level))}</td></tr>
                    <tr><th>Géométrie</th><td>{geometry_status}</td></tr>
                    <tr><th>Contrôle territorial Bénin</th><td>{escape(_territory_label(parcel.territory_status))}</td></tr>
                    <tr><th>Centroïde (lat, lon)</th><td>{escape(_territory_centroid(parcel.territory_centroid_lon, parcel.territory_centroid_lat))}</td></tr>
                </tbody>
            </table>
            <h4>Alertes de la parcelle</h4>
            <ul>{_warning_list(warnings)}</ul>
        </section>
    """


def generate_audit_report_pdf(audit: AuditResponse) -> bytes:
    warnings = audit.warnings or ["Aucune alerte technique supplémentaire."]
    parcels_html = "".join(_parcel_card(parcel, index) for index, parcel in enumerate(audit.parcels, start=1))
    if not parcels_html:
        parcels_html = "<p>Aucune parcelle détaillée n'est disponible pour cet audit.</p>"

    html = f"""
    <!doctype html>
    <html lang="fr">
    <head>
        <meta charset="utf-8">
        <title>Rapport d'audit {escape(audit.project_id)}</title>
        <style>
            @page {{ size: A4; margin: 1.8cm; }}
            body {{ color: #111827; font-family: DejaVu Sans, sans-serif; font-size: 11px; line-height: 1.45; }}
            h1 {{ color: #111827; font-size: 22px; margin: 0 0 18px; }}
            h2 {{ border-bottom: 2px solid #d1d5db; color: #1f2937; font-size: 16px; margin: 22px 0 10px; padding-bottom: 4px; }}
            h3 {{ color: #1f2937; font-size: 14px; margin: 0 0 8px; }}
            h4 {{ color: #374151; font-size: 12px; margin: 10px 0 4px; }}
            table {{ border-collapse: collapse; margin: 8px 0 10px; width: 100%; }}
            th, td {{ border: 1px solid #d1d5db; padding: 6px 8px; text-align: left; vertical-align: top; }}
            th {{ background: #f3f4f6; font-weight: 700; width: 42%; }}
            ul {{ margin: 4px 0 0 18px; padding: 0; }}
            .summary th {{ background: #1f2937; color: white; width: 45%; }}
            .parcel-card {{ border: 1px solid #d1d5db; border-radius: 6px; margin: 12px 0; padding: 12px; page-break-inside: avoid; }}
            .muted {{ color: #4b5563; margin: -4px 0 8px; }}
            .disclaimer {{ background: #fffbeb; border: 1px solid #b45309; border-radius: 6px; padding: 10px; }}
        </style>
    </head>
    <body>
        <h1>Rapport d'audit préliminaire TopoAudit Bénin</h1>

        <h2>Scores de risque</h2>
        <table class="summary">
            <tbody>
                <tr><th>Projet</th><td>{escape(audit.project_id)}</td></tr>
                <tr><th>Audit</th><td>{escape(audit.audit_id)}</td></tr>
                <tr><th>État du workflow</th><td>{escape(audit.state.value)}</td></tr>
                <tr><th>Score d'extraction</th><td>{escape(_format_extraction_score(audit.extraction_score, audit.extraction_score_status))}</td></tr>
                <tr><th>Bornes validées humainement</th><td>{"Oui" if audit.human_validated else "Non"}</td></tr>
                <tr><th>Score technique</th><td>{audit.technical_score}/100</td></tr>
                <tr><th>Niveau de risque</th><td>{escape(_risk_label(audit.risk_level))}</td></tr>
                <tr><th>Contrôle territorial Bénin</th><td>{escape(_territory_label(audit.territory_status))}{" — Risque critique" if audit.territory_risk_level == "critical" else ""}</td></tr>
                <tr><th>Centroïde (lat, lon)</th><td>{escape(_territory_centroid(audit.territory_centroid_lon, audit.territory_centroid_lat))}</td></tr>
            </tbody>
        </table>

        <h2>Audits par parcelle</h2>
        <p>Les surfaces et alertes ci-dessous sont présentées parcelle par parcelle, sans fusionner les géométries.</p>
        {parcels_html}

        <h2>Alertes et limites techniques</h2>
        <ul>{_warning_list(warnings)}</ul>

        <h2>Avertissement légal obligatoire</h2>
        <p class="disclaimer">{escape(LEGAL_DISCLAIMER)}</p>
    </body>
    </html>
    """
    return HTML(string=html).write_pdf()
