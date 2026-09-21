"""PDF act generation for delivery batches using ReportLab.

ReportLab is pure Python and the DejaVu Sans font is bundled in ``fonts/``,
so PDFs are generated on any OS (Windows, Linux, macOS) with no extra installs.
"""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .act_data import build_act

_FONTS_DIR = Path(__file__).resolve().parent / 'fonts'
_FONT_REGULAR = 'ActSans'
_FONT_BOLD = 'ActSans-Bold'
_FONTS_READY = False


def _ensure_fonts():
    global _FONTS_READY
    if _FONTS_READY:
        return
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, str(_FONTS_DIR / 'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, str(_FONTS_DIR / 'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily(
        _FONT_REGULAR, normal=_FONT_REGULAR, bold=_FONT_BOLD, italic=_FONT_REGULAR, boldItalic=_FONT_BOLD,
    )
    _FONTS_READY = True


def generate_batch_pdf(batch):
    """Return PDF bytes for a DeliveryBatch."""
    _ensure_fonts()
    act = build_act(batch)

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=act.title,
    )

    title_style = ParagraphStyle('Title', fontName=_FONT_BOLD, fontSize=15, leading=20, spaceAfter=6)
    meta_style = ParagraphStyle('Meta', fontName=_FONT_REGULAR, fontSize=9.5, leading=15, textColor=colors.HexColor('#333333'))
    footer_style = ParagraphStyle('Footer', fontName=_FONT_REGULAR, fontSize=10, spaceBefore=12)
    cell_style = ParagraphStyle('Cell', fontName=_FONT_REGULAR, fontSize=8.5, leading=11.5)
    header_style = ParagraphStyle('Head', fontName=_FONT_BOLD, fontSize=8.5, leading=11.5, textColor=colors.white)

    elements = [Paragraph(escape(act.title), title_style)]
    meta_html = '<br/>'.join(f'<b>{escape(label)}:</b> {escape(value)}' for label, value in act.meta)
    elements.append(Paragraph(meta_html, meta_style))
    elements.append(Spacer(1, 12))

    data = [[Paragraph(escape(h), header_style) for h in act.headers]]
    for row in act.rows:
        data.append([Paragraph(escape(str(c)), cell_style) for c in row])

    col_widths = [1.0 * cm, 2.2 * cm, 5.8 * cm, 4.0 * cm, 1.3 * cm, 2.7 * cm]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1F4E79')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fafafa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Paragraph(f'{escape(act.total_label)}: <b>{act.total}</b>', footer_style))
    elements.append(Spacer(1, 32))

    sign_table = Table([['', '', ''], [act.sign_left, '', act.sign_right]], colWidths=[6.5 * cm, 1.5 * cm, 6.5 * cm])
    sign_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 1), (0, 1), 0.75, colors.black),
        ('LINEABOVE', (2, 1), (2, 1), 0.75, colors.black),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, 1), _FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, 1), 8.5),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#555555')),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    return buf.getvalue()
