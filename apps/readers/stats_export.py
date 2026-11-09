"""Выгрузка статистики читателей в Excel."""
from io import BytesIO

from django.utils import timezone
from django.utils.translation import gettext as _t
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill('solid', fgColor='2E5C9A')
HEADER_FONT = Font(bold=True, color='FFFFFF')
TITLE_FONT = Font(bold=True, size=14)


def _sheet_title(text):
    for ch in '[]:*?/\\':
        text = text.replace(ch, ' ')
    return text[:31]


def _put(ws, row, col, value, number_format=None):
    """Записывает значение; текст, начинающийся с «=», остаётся текстом (защита от формул из чужих данных)."""
    cell = ws.cell(row=row, column=col, value=value)
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        cell.data_type = 's'
    if number_format:
        cell.number_format = number_format
    return cell


def _table(ws, start_row, headers, rows, widths=None):
    for col, header in enumerate(headers, start=1):
        cell = _put(ws, start_row, col, header)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    for r, values in enumerate(rows, start=start_row + 1):
        for col, value in enumerate(values, start=1):
            fmt = None
            if hasattr(value, 'year') and hasattr(value, 'month'):
                fmt = 'DD.MM.YYYY'
            _put(ws, r, col, value, fmt)
    for col in range(1, len(headers) + 1):
        width = (widths or {}).get(col)
        if width is None:
            longest = max([len(str(headers[col - 1]))] + [len(str(v[col - 1])) for v in rows if v[col - 1] is not None] or [8])
            width = min(max(longest + 2, 10), 50)
        ws.column_dimensions[get_column_letter(col)].width = width
    ws.freeze_panes = ws.cell(row=start_row + 1, column=1)


def build_stats_workbook(*, stats, loan_stats, period_text, include_readers,
                         reader_rows, unreturned, loan_period_days):
    """Собирает книгу Excel. Списки с именами читателей (include_readers) — только для администратора."""
    wb = Workbook()

    # ── Сводка ──
    ws = wb.active
    ws.title = _sheet_title(_t('Сводка'))
    _put(ws, 1, 1, _t('Статистика читателей')).font = TITLE_FONT
    now = timezone.localtime()
    summary = [
        (_t('Дата выгрузки'), now.strftime('%d.%m.%Y %H:%M')),
        (_t('Период для книг'), period_text),
        ('', ''),
        (_t('Всего читателей'), stats['total']),
    ]
    for g in stats['gender']:
        summary.append((g['label'], g['count']))
    summary += [
        ('', ''),
        (_t('Взято книг за период'), loan_stats['total']),
        (_t('Читателей брали книги'), loan_stats['readers_total']),
        (_t('В среднем на читателя'), loan_stats['average']),
        (_t('Не возвращено сейчас'), unreturned['count']),
        (_t('Из них просрочено'), unreturned['overdue']),
        (_t('Срок возврата, дней'), loan_period_days if loan_period_days else _t('без ограничения')),
    ]
    if not include_readers:
        summary += [('', ''), (_t('Списки читателей в файл не включены (доступны администратору).'), '')]
    for r, (label, value) in enumerate(summary, start=3):
        _put(ws, r, 1, label).font = Font(bold=bool(label) and value == '')
        _put(ws, r, 2, value)
    ws.column_dimensions['A'].width = 42
    ws.column_dimensions['B'].width = 24

    # ── Читатели по возрасту и полу ──
    ws = wb.create_sheet(_sheet_title(_t('Читатели по возрасту')))
    headers = [_t('Возраст'), _t('Мужской'), _t('Женский'), _t('Не указан'), _t('Всего'), '%']
    rows = [[r['label'], r['male'], r['female'], r['unknown_gender'], r['total'], r['percent']] for r in stats['age_rows']]
    _table(ws, 1, headers, rows)

    # ── Книги по возрасту и полу ──
    ws = wb.create_sheet(_sheet_title(_t('Книги по возрасту')))
    rows = [[r['label'], r['male'], r['female'], r['unknown_gender'], r['total']] for r in loan_stats['age_rows']]
    _table(ws, 1, headers[:5], rows)

    if include_readers:
        # ── Читатели и взятые книги ──
        ws = wb.create_sheet(_sheet_title(_t('Читатели и книги')))
        rows = [[row['reader'].full_name, row['reader'].card_id or '', row['reader'].get_gender_display(),
                 row['reader'].birth_year or '', row['taken'], row['not_returned']] for row in reader_rows]
        _table(ws, 1, [_t('Читатель'), _t('ID читателя'), _t('Пол'), _t('Год рождения'),
                       _t('Взято'), _t('Не возвращено')], rows)

        # ── Не возвращённые книги ──
        ws = wb.create_sheet(_sheet_title(_t('Не возвращены')))
        rows = []
        for loan in unreturned['loans']:
            rows.append([
                loan.reader.full_name if loan.reader else _t('Без читателя'),
                (loan.reader.card_id or '') if loan.reader else '',
                loan.book.title, loan.book.inventory_number, loan.location.name,
                timezone.localtime(loan.issued_at).date(), loan.days_held, loan.overdue_days,
            ])
        _table(ws, 1, [_t('Читатель'), _t('ID читателя'), _t('Книга'), _t('Инв. номер'), _t('Библиопункт'),
                       _t('Дата выдачи'), _t('Дней на руках'), _t('Просрочено дней')], rows)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
