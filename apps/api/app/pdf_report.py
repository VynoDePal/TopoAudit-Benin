from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.workflow import AuditResponse

LEGAL_DISCLAIMER = (
    "Ce rapport est généré automatiquement à des fins d'audit technique préliminaire. "
    "Il ne constitue pas un avis juridique, ne remplace pas une vérification cadastrale "
    "officielle et ne confère aucun droit foncier. Toute décision juridique ou transaction "
    "doit être validée par les autorités compétentes et des professionnels habilités."
)


def _risk_label(risk_level: str) -> str:
    labels = {"low": "Faible", "moderate": "Modéré", "high": "Élevé"}
    return labels.get(risk_level, risk_level)


def generate_audit_report_pdf(audit: AuditResponse) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=f"Rapport d'audit {audit.project_id}",
    )
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    body_style = styles["BodyText"]
    disclaimer_style = ParagraphStyle(
        "Disclaimer",
        parent=body_style,
        borderColor=colors.HexColor("#b45309"),
        borderPadding=8,
        backColor=colors.HexColor("#fffbeb"),
        leading=14,
    )

    score_rows = [
        ["Indicateur", "Valeur"],
        ["Projet", audit.project_id],
        ["Audit", audit.audit_id],
        ["État du workflow", audit.state.value],
        ["Score d'extraction", f"{audit.extraction_score}/100"],
        ["Score technique", f"{audit.technical_score}/100"],
        ["Niveau de risque", _risk_label(audit.risk_level)],
    ]
    score_table = Table(score_rows, colWidths=[6 * cm, 8 * cm])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f9fafb")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    warnings = audit.warnings or ["Aucune alerte technique supplémentaire."]
    warning_items = "<br/>".join(f"• {warning}" for warning in warnings)

    story = [
        Paragraph("Rapport d'audit préliminaire TopoAudit Bénin", title_style),
        Spacer(1, 0.5 * cm),
        Paragraph("Scores de risque", heading_style),
        score_table,
        Spacer(1, 0.5 * cm),
        Paragraph("Alertes et limites techniques", heading_style),
        Paragraph(warning_items, body_style),
        Spacer(1, 0.5 * cm),
        Paragraph("Avertissement légal obligatoire", heading_style),
        Paragraph(LEGAL_DISCLAIMER, disclaimer_style),
    ]

    document.build(story)
    return buffer.getvalue()
