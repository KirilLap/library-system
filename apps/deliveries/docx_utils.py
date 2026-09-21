"""Word (.docx) act generation for delivery batches using python-docx (pure Python)."""

from io import BytesIO

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .act_data import build_act

_FONT = 'Arial'
_HEADER_FILL = '1F4E79'
_COL_WIDTHS_CM = [1.0, 2.2, 5.8, 4.0, 1.3, 2.7]


def _set_font(run, size=None, bold=None, color=None):
    run.font.name = _FONT
    run._element.rPr.rFonts.set(qn('w:eastAsia'), _FONT)
    if size:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)


def _shade(cell, fill):
    tc_pr = cell._element.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), fill)
    tc_pr.append(shd)


def _repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    el = OxmlElement('w:tblHeader')
    el.set(qn('w:val'), 'true')
    tr_pr.append(el)


def _top_border(cell):
    tc_pr = cell._element.get_or_add_tcPr()
    borders = OxmlElement('w:tcBorders')
    top = OxmlElement('w:top')
    top.set(qn('w:val'), 'single')
    top.set(qn('w:sz'), '6')
    top.set(qn('w:color'), '000000')
    borders.append(top)
    tc_pr.append(borders)


def _write(cell, text, size=9, bold=False, color=None, align=None):
    para = cell.paragraphs[0]
    para.paragraph_format.space_after = Pt(0)
    if align is not None:
        para.alignment = align
    _set_font(para.add_run(text), size=size, bold=bold, color=color)


def generate_batch_docx(batch):
    """Return .docx bytes for a DeliveryBatch."""
    act = build_act(batch)

    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.5)
    section.left_margin = section.right_margin = Cm(2)
    doc.core_properties.title = act.title

    normal = doc.styles['Normal']
    normal.font.name = _FONT
    normal.element.rPr.rFonts.set(qn('w:eastAsia'), _FONT)

    title = doc.add_paragraph()
    title.paragraph_format.space_after = Pt(6)
    _set_font(title.add_run(act.title), size=15, bold=True)

    meta = doc.add_paragraph()
    meta.paragraph_format.space_after = Pt(10)
    meta.paragraph_format.line_spacing = 1.3
    for i, (label, value) in enumerate(act.meta):
        if i:
            meta.add_run().add_break()
        _set_font(meta.add_run(f'{label}: '), size=9.5, bold=True, color='333333')
        _set_font(meta.add_run(value), size=9.5, color='333333')

    table = doc.add_table(rows=1, cols=len(act.headers))
    table.style = 'Table Grid'
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for cell, header, width in zip(table.rows[0].cells, act.headers, _COL_WIDTHS_CM):
        cell.width = Cm(width)
        _shade(cell, _HEADER_FILL)
        _write(cell, header, size=8.5, bold=True, color='FFFFFF')
    _repeat_header(table.rows[0])

    for i, row in enumerate(act.rows):
        cells = table.add_row().cells
        for cell, value, width in zip(cells, row, _COL_WIDTHS_CM):
            cell.width = Cm(width)
            if i % 2:
                _shade(cell, 'FAFAFA')
            _write(cell, str(value), size=8.5)

    total = doc.add_paragraph()
    total.paragraph_format.space_before = Pt(10)
    _set_font(total.add_run(f'{act.total_label}: '), size=10)
    _set_font(total.add_run(str(act.total)), size=10, bold=True)

    doc.add_paragraph().paragraph_format.space_after = Pt(18)

    sign = doc.add_table(rows=2, cols=2)
    sign.alignment = WD_TABLE_ALIGNMENT.CENTER
    sign.rows[0].height = Cm(1)
    for cell in sign.rows[0].cells:
        cell.width = Cm(7)
    for cell, label in zip(sign.rows[1].cells, (act.sign_left, act.sign_right)):
        cell.width = Cm(7)
        _top_border(cell)
        _write(cell, label, size=8.5, color='555555', align=WD_ALIGN_PARAGRAPH.CENTER)

    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()
