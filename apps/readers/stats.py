"""Статистика читателей: пол и возрастные группы с настраиваемыми границами."""
from django.utils import timezone
from django.utils.translation import gettext

DEFAULT_BOUNDARIES = '14,18,31,61'
MAX_AGE = 120
MAX_BOUNDARIES = 9


def parse_boundaries(text):
    """'14, 18 31;61' -> [14, 18, 31, 61]. Бросает ValueError с понятным текстом."""
    raw = [part for part in str(text).replace(';', ',').replace(' ', ',').split(',') if part.strip()]
    if not raw:
        raise ValueError('Укажите хотя бы одну границу, например: 14, 18, 31, 61.')
    try:
        values = [int(part) for part in raw]
    except ValueError:
        raise ValueError('Границы должны быть целыми числами через запятую, например: 14, 18, 31, 61.')
    if any(v < 1 or v > MAX_AGE for v in values):
        raise ValueError(f'Каждая граница должна быть от 1 до {MAX_AGE}.')
    if len(set(values)) != len(values):
        raise ValueError('Границы не должны повторяться.')
    if len(values) > MAX_BOUNDARIES:
        raise ValueError(f'Не больше {MAX_BOUNDARIES} границ.')
    return sorted(values)


def build_groups(boundaries):
    """Границы [14, 18, 31, 61] -> группы до 14 / 14–17 / 18–30 / 31–60 / 61+."""
    groups = []
    first = boundaries[0]
    groups.append({'min': 0, 'max': first - 1,
                   'label': gettext('до %(n)s') % {'n': first}})
    for start, nxt in zip(boundaries, boundaries[1:]):
        end = nxt - 1
        label = str(start) if start == end else gettext('%(a)s–%(b)s') % {'a': start, 'b': end}
        groups.append({'min': start, 'max': end, 'label': label})
    last = boundaries[-1]
    groups.append({'min': last, 'max': None, 'label': gettext('%(n)s+') % {'n': last}})
    return groups


def reader_statistics(readers, boundaries):
    """Считает читателей по полу и возрастным группам (возраст = текущий год − год рождения)."""
    from .models import Reader
    groups = build_groups(boundaries)
    year = timezone.now().year
    genders = [Reader.GENDER_MALE, Reader.GENDER_FEMALE, '']

    gender_totals = {g: 0 for g in genders}
    age_unknown = {g: 0 for g in genders}
    matrix = [{g: 0 for g in genders} for _ in groups]

    total = 0
    for gender, birth_year in readers.values_list('gender', 'birth_year'):
        gender = gender if gender in genders else ''
        total += 1
        gender_totals[gender] += 1
        if not birth_year:
            age_unknown[gender] += 1
            continue
        age = max(year - birth_year, 0)
        for index, group in enumerate(groups):
            if age >= group['min'] and (group['max'] is None or age <= group['max']):
                matrix[index][gender] += 1
                break

    def pct(value):
        return round(value * 100 / total, 1) if total else 0

    rows = []
    for group, counts in zip(groups, matrix):
        count = sum(counts.values())
        rows.append({'label': group['label'], 'male': counts['M'], 'female': counts['F'],
                     'unknown_gender': counts[''], 'total': count, 'percent': pct(count)})
    unknown_total = sum(age_unknown.values())
    rows.append({'label': gettext('Возраст не указан'), 'male': age_unknown['M'], 'female': age_unknown['F'],
                 'unknown_gender': age_unknown[''], 'total': unknown_total, 'percent': pct(unknown_total),
                 'muted': True})

    return {
        'total': total,
        'gender': [
            {'label': gettext('Мужской'), 'count': gender_totals['M'], 'percent': pct(gender_totals['M'])},
            {'label': gettext('Женский'), 'count': gender_totals['F'], 'percent': pct(gender_totals['F'])},
            {'label': gettext('Не указан'), 'count': gender_totals[''], 'percent': pct(gender_totals[''])},
        ],
        'age_rows': rows,
    }


def _group_index(groups, age):
    for index, group in enumerate(groups):
        if age >= group['min'] and (group['max'] is None or age <= group['max']):
            return index
    return len(groups) - 1


def loan_statistics(loans, boundaries, top=10):
    """Сколько книг взято за период: всего, по читателям (топ), по возрасту и полу.

    loans — выборка Loan за нужный период. Выдачи без читателя (анонимные) входят
    в общий итог, но не в списки по читателям и возрасту."""
    from django.db.models import Count, Q
    from .models import Reader

    groups = build_groups(boundaries)
    year = timezone.now().year
    genders = [Reader.GENDER_MALE, Reader.GENDER_FEMALE, '']

    with_reader = loans.filter(reader__isnull=False)
    total = loans.count()
    by_readers = with_reader.count()

    rows = [{'label': g['label'], 'male': 0, 'female': 0, 'unknown_gender': 0, 'total': 0} for g in groups]
    rows.append({'label': gettext('Возраст не указан'), 'male': 0, 'female': 0,
                 'unknown_gender': 0, 'total': 0, 'muted': True})
    key = {'M': 'male', 'F': 'female', '': 'unknown_gender'}
    for gender, birth_year in with_reader.values_list('reader__gender', 'reader__birth_year'):
        gender = gender if gender in genders else ''
        if birth_year:
            index = _group_index(groups, max(year - birth_year, 0))
        else:
            index = len(groups)
        rows[index][key[gender]] += 1
        rows[index]['total'] += 1

    counted = list(
        with_reader.values('reader')
        .annotate(taken=Count('id'), not_returned=Count('id', filter=Q(is_returned=False)))
        .order_by('-taken', 'reader')
    )
    readers_total = len(counted)
    readers = Reader.objects.select_related('user').in_bulk([c['reader'] for c in counted[:top]])
    top_readers = []
    for c in counted[:top]:
        reader = readers.get(c['reader'])
        if reader is not None:
            top_readers.append({'reader': reader, 'taken': c['taken'], 'not_returned': c['not_returned']})

    return {
        'total': total,
        'by_readers': by_readers,
        'anonymous': total - by_readers,
        'readers_total': readers_total,
        'average': round(by_readers / readers_total, 1) if readers_total else 0,
        'age_rows': rows,
        'top_readers': top_readers,
        'top_limit': top,
        'hidden_readers': max(readers_total - top, 0),
    }


# ───────────── Период, списки читателей и не возвращённые книги ─────────────

def current_boundaries():
    """Границы возрастных групп из настроек (при порче настроек — значения по умолчанию)."""
    from .models import AgeGroupSettings
    try:
        return parse_boundaries(AgeGroupSettings.get_solo().boundaries)
    except ValueError:
        return parse_boundaries(DEFAULT_BOUNDARIES)


def parse_period(params, today=None):
    """Период из адресной строки: ?days=7|30|90|365|all или ?from=ГГГГ-ММ-ДД&to=ГГГГ-ММ-ДД.

    Возвращает (period, date_from, date_to); period — '7', '30', '90', '365', 'all' или 'custom'."""
    from datetime import date, timedelta
    today = today or timezone.localdate()

    def _date(value):
        try:
            return date.fromisoformat(value)
        except (TypeError, ValueError):
            return None

    date_from, date_to = _date(params.get('from')), _date(params.get('to'))
    days = params.get('days', '')
    if date_from or date_to:
        period = 'custom'
    elif days == 'all':
        period = 'all'
    else:
        period = days if days in ('7', '30', '90', '365') else '30'
        date_from = today - timedelta(days=int(period) - 1)
        date_to = today
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return period, date_from, date_to


def period_query(period, date_from, date_to):
    """Часть адреса, которая сохраняет выбранный период в ссылках."""
    from urllib.parse import urlencode
    if period == 'custom':
        data = {}
        if date_from:
            data['from'] = date_from.isoformat()
        if date_to:
            data['to'] = date_to.isoformat()
        return urlencode(data)
    return urlencode({'days': period})


def period_loans(date_from, date_to):
    from .models import Loan
    loans = Loan.objects.all()
    if date_from:
        loans = loans.filter(issued_at__date__gte=date_from)
    if date_to:
        loans = loans.filter(issued_at__date__lte=date_to)
    return loans


def reader_loan_rows(loans):
    """Все читатели, бравшие книги в выборке: сколько взято и сколько не возвращено (по убыванию)."""
    from django.db.models import Count, Q
    from .models import Reader
    counted = list(
        loans.filter(reader__isnull=False).values('reader')
        .annotate(taken=Count('id'), not_returned=Count('id', filter=Q(is_returned=False)))
        .order_by('-taken', 'reader')
    )
    readers = Reader.objects.select_related('user').in_bulk([c['reader'] for c in counted])
    rows = []
    for c in counted:
        reader = readers.get(c['reader'])
        if reader is not None:
            rows.append({'reader': reader, 'taken': c['taken'], 'not_returned': c['not_returned']})
    return rows


def open_loans(only_overdue=False):
    """Не возвращённые книги (сначала самые давние). Просрочка считается так же, как в кабинете читателя:
    книга на руках дольше LOAN_PERIOD_DAYS дней."""
    from datetime import timedelta
    from django.conf import settings
    from .models import Loan
    loans = Loan.objects.filter(is_returned=False).select_related('book__book_title', 'reader__user', 'location')
    if only_overdue:
        loans = loans.filter(issued_at__lte=timezone.now() - timedelta(days=settings.LOAN_PERIOD_DAYS + 1))
    return loans.order_by('issued_at')
