"""Выгрузка статистики по книгам в Excel."""
from io import BytesIO

from django.utils import timezone
from django.utils.translation import gettext as _t
from openpyxl import Workbook
from openpyxl.styles import Font

from apps.readers.stats_export import TITLE_FONT, _put, _sheet_title, _table


def build_books_workbook(data, period_text):
    """data — результат collect_stats(...) с большими лимитами; period_text — подпись периода."""
    wb = Workbook()
    ps, cur = data['period_stats'], data['current']

    # ── Сводка ──
    ws = wb.active
    ws.title = _sheet_title(_t('Сводка'))
    _put(ws, 1, 1, _t('Статистика по книгам')).font = TITLE_FONT
    rows = [
        (_t('Дата выгрузки'), timezone.localtime().strftime('%d.%m.%Y %H:%M')),
        (_t('Период'), period_text),
        ('', ''),
        (_t('Выдано книг'), ps['loans_issued']),
        (_t('Возвращено книг'), ps['loans_returned']),
        (_t('Утеряно книг за период'), ps['loans_lost']),
        (_t('Новых заявок'), ps['requests_created']),
        (_t('Заявок выполнено'), ps['requests_fulfilled']),
        ('', ''),
        (_t('Всего книг'), cur['books_total']),
        (_t('В библиотеке'), cur['books_in_library']),
        (_t('В библиопунктах'), cur['books_in_points']),
        (_t('Потеряно'), cur['books_lost']),
        (_t('На руках сейчас'), cur['on_hands']),
        (_t('Из них просрочено'), cur['overdue']),
    ]
    for r, (label, value) in enumerate(rows, start=3):
        _put(ws, r, 1, label)
        _put(ws, r, 2, value)
    ws.column_dimensions['A'].width = 34
    ws.column_dimensions['B'].width = 24

    # ── По неделям ──
    ws = wb.create_sheet(_sheet_title(_t('Выдачи по неделям')))
    _table(ws, 1, [_t('Неделя с'), _t('по'), _t('Выдано книг')],
           [[w['start'], w['end'], w['count']] for w in reversed(data['week_rows'])],
           widths={1: 14, 2: 14, 3: 16})

    # ── Жанры ──
    ws = wb.create_sheet(_sheet_title(_t('Жанры')))
    total = sum(g['count'] for g in data['all_genres']) or 1
    _table(ws, 1, [_t('Жанр'), _t('Выдано книг'), '%'],
           [[g['name'], g['count'], round(g['count'] * 100 / total, 1)] for g in data['all_genres']])

    # ── Популярные книги ──
    ws = wb.create_sheet(_sheet_title(_t('Популярные книги')))
    _table(ws, 1, [_t('Название'), _t('Автор'), _t('Выдано раз')],
           [[b['book__book_title__title'], b['book__book_title__author'], b['n']] for b in data['top_books']])

    # ── Библиопункты ──
    ws = wb.create_sheet(_sheet_title(_t('Библиопункты')))
    issued = {l['location__name']: l['n'] for l in data['top_locations']}
    names = sorted(set(issued) | set(data['books_in_points_by_location']), key=lambda n: (-issued.get(n, 0), n or ''))
    _table(ws, 1, [_t('Библиопункт'), _t('Выдано за период'), _t('Книг сейчас в пункте')],
           [[n, issued.get(n, 0), data['books_in_points_by_location'].get(n, 0)] for n in names])

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def build_points_workbook(data, period_text):
    """Выгрузка статистики по библиопунктам: сводка и таблица по каждому пункту."""
    wb = Workbook()
    totals = data['totals']

    ws = wb.active
    ws.title = _sheet_title(_t('Сводка'))
    _put(ws, 1, 1, _t('Статистика по библиопунктам')).font = TITLE_FONT
    rows = [
        (_t('Дата выгрузки'), timezone.localtime().strftime('%d.%m.%Y %H:%M')),
        (_t('Период'), period_text),
        ('', ''),
        (_t('Библиопунктов в таблице'), len(data['rows'])),
        (_t('Партий за период'), totals['batches_period']),
        (_t('Партий за всё время'), totals['batches_all']),
        (_t('Книг завезено за период'), totals['books_period']),
        (_t('Книг завезено за всё время'), totals['books_all']),
        (_t('Книг сейчас в пунктах'), totals['in_point']),
        (_t('Выдач за период'), totals['loans']),
        (_t('Читателей брали книги за период'), totals['readers']),
        (_t('Не возвращено сейчас'), totals['open']),
        (_t('Из них просрочено'), totals['overdue']),
    ]
    for r, (label, value) in enumerate(rows, start=3):
        _put(ws, r, 1, label)
        _put(ws, r, 2, value)
    ws.column_dimensions['A'].width = 38
    ws.column_dimensions['B'].width = 24

    ws = wb.create_sheet(_sheet_title(_t('По библиопунктам')))
    headers = [_t('Библиопункт'), _t('Тип'), _t('Партий за период'), _t('Партий всего'),
               _t('Книг завезено за период'), _t('Книг завезено всего'), _t('Книг сейчас в пункте'),
               _t('Выдач за период'), _t('Читателей брали книги'), _t('Не возвращено сейчас'),
               _t('Просрочено'), _t('Выбрали пункт ближайшим')]
    body = [[r['location'].name, r['type'], r['batches_period'], r['batches_all'], r['books_period'],
             r['books_all'], r['in_point'], r['loans'], r['readers'], r['open'], r['overdue'], r['nearest']]
            for r in data['rows']]
    body.append([_t('Итого'), '', totals['batches_period'], totals['batches_all'], totals['books_period'],
                 totals['books_all'], totals['in_point'], totals['loans'], totals['readers'],
                 totals['open'], totals['overdue'], totals['nearest']])
    _table(ws, 1, headers, body, widths={1: 34, 2: 16})
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)

    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
