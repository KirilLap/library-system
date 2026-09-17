"""PDF act generation for delivery batches using ReportLab.

ReportLab is pure Python — unlike WeasyPrint it needs no native GTK/Pango/Cairo
libraries, so it works out of the box on any Windows office PC without extra
runtime installs.
"""

import os
from io import BytesIO

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

_FONT_REGULAR = 'PDFSans'
_FONT_BOLD = 'PDFSans-Bold'
_FONTS_READY = False


def _ensure_fonts():
    """Register a Cyrillic-capable TTF font. Reuses Windows' bundled Arial."""
    global _FONTS_READY
    if _FONTS_READY:
        return

    candidates = [
        (r'C:\Windows\Fonts\arial.ttf', r'C:\Windows\Fonts\arialbd.ttf'),
    ]
    for regular_path, bold_path in candidates:
        if os.path.exists(regular_path) and os.path.exists(bold_path):
            pdfmetrics.registerFont(TTFont(_FONT_REGULAR, regular_path))
            pdfmetrics.registerFont(TTFont(_FONT_BOLD, bold_path))
            _FONTS_READY = True
            return

    raise RuntimeError(
        'Не найден шрифт с поддержкой кириллицы (Arial в C:\\Windows\\Fonts). '
        'PDF с русским/узбекским текстом сгенерировать нельзя.'
    )


def generate_batch_pdf(batch):
    """Return PDF bytes for a DeliveryBatch."""
    _ensure_fonts()

    items = batch.items.select_related('book').order_by('book__inventory_number')
    library_name = getattr(settings, 'LIBRARY_NAME', '')
    library_phone = getattr(settings, 'LIBRARY_PHONE', '')

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f'Акт доставки №{batch.pk}',
    )

    title_style = ParagraphStyle(
        'Title', fontName=_FONT_BOLD, fontSize=16, leading=20, spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        'Meta', fontName=_FONT_REGULAR, fontSize=10, leading=15, textColor=colors.HexColor('#333333'),
    )
    footer_style = ParagraphStyle(
        'Footer', fontName=_FONT_REGULAR, fontSize=10, spaceBefore=12,
    )
    sign_style = ParagraphStyle(
        'Sign', fontName=_FONT_REGULAR, fontSize=9, textColor=colors.HexColor('#555555'), alignment=1,
    )

    elements = [Paragraph(f'Акт доставки книг №{batch.pk}', title_style)]

    meta_lines = [
        f'<b>Библиотека:</b> {library_name}' + (f' · {library_phone}' if library_phone else ''),
        f'<b>Точка доставки:</b> {batch.location.name} ({batch.location.get_type_display()})',
        f'<b>Адрес:</b> {batch.location.address}',
    ]
    if batch.location.contact_person:
        contact = f'<b>Контактное лицо:</b> {batch.location.contact_person}'
        if batch.location.contact_phone:
            contact += f' · {batch.location.contact_phone}'
        meta_lines.append(contact)
    meta_lines.append(f'<b>Дата доставки:</b> {batch.delivery_date.strftime("%d.%m.%Y")}')
    meta_lines.append(f'<b>Количество книг:</b> {len(items)}')
    if batch.note:
        meta_lines.append(f'<b>Примечание:</b> {batch.note}')

    elements.append(Paragraph('<br/>'.join(meta_lines), meta_style))
    elements.append(Spacer(1, 12))

    table_data = [['№', 'Инв. №', 'Название', 'Автор', 'Год', 'Жанр']]
    for i, item in enumerate(items, start=1):
        table_data.append([
            str(i),
            item.book.inventory_number,
            item.book.title,
            item.book.author,
            str(item.book.year) if item.book.year else '—',
            item.book.get_genre_display(),
        ])

    cell_style = ParagraphStyle('Cell', fontName=_FONT_REGULAR, fontSize=9, leading=12)
    header_style = ParagraphStyle('Head', fontName=_FONT_BOLD, fontSize=9, leading=12, textColor=colors.white)
    wrapped_data = [[Paragraph(str(c), header_style) for c in table_data[0]]]
    for row in table_data[1:]:
        wrapped_data.append([Paragraph(str(c), cell_style) for c in row])

    col_widths = [1.0 * cm, 2.2 * cm, 5.8 * cm, 4.0 * cm, 1.3 * cm, 2.7 * cm]
    table = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
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

    elements.append(Paragraph(f'Итого книг: <b>{len(items)}</b>', footer_style))
    elements.append(Spacer(1, 32))

    sign_table = Table(
        [['', ''], ['Сдал (библиотекарь)', 'Принял (ответственный)']],
        colWidths=[7 * cm, 7 * cm],
    )
    sign_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 1), (0, 1), 0.75, colors.black),
        ('LINEABOVE', (1, 1), (1, 1), 0.75, colors.black),
        ('TOPPADDING', (0, 1), (-1, 1), 4),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 1), (-1, 1), _FONT_REGULAR),
        ('FONTSIZE', (0, 1), (-1, 1), 9),
        ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#555555')),
    ]))
    elements.append(sign_table)

    doc.build(elements)
    return buf.getvalue()
