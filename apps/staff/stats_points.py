"""Статистика по библиопунктам: партии, завезённые книги, выдачи и читатели."""
from django.db.models import Count


def _between(queryset, field, date_from, date_to, is_datetime=False):
    suffix = '__date' if is_datetime else ''
    if date_from:
        queryset = queryset.filter(**{f'{field}{suffix}__gte': date_from})
    if date_to:
        queryset = queryset.filter(**{f'{field}{suffix}__lte': date_to})
    return queryset


def collect_points_stats(date_from, date_to):
    """По каждому библиопункту считает за период (включительно) и за всё время.

    Партии и завезённые книги считаются по дате доставки партии, выдачи по дате выдачи.
    «Сейчас» (в пункте, не возвращено, просрочено) от периода не зависит."""
    from apps.deliveries.models import DeliveryBatch, DeliveryItem
    from apps.locations.models import Location, LocationType
    from apps.readers.models import Loan, Reader
    from apps.readers.stats import open_loans

    def counts(queryset, key):
        return {row[key]: row['n'] for row in queryset.order_by().values(key).annotate(n=Count('id'))}

    batches_all = counts(DeliveryBatch.objects.all(), 'location')
    batches_period = counts(_between(DeliveryBatch.objects.all(), 'delivery_date', date_from, date_to), 'location')
    books_all = counts(DeliveryItem.objects.all(), 'batch__location')
    books_period = counts(
        _between(DeliveryItem.objects.all(), 'batch__delivery_date', date_from, date_to), 'batch__location')
    in_point = counts(DeliveryItem.objects.filter(is_returned=False), 'batch__location')

    period_loans = _between(Loan.objects.all(), 'issued_at', date_from, date_to, is_datetime=True)
    loan_rows = {
        row['location']: row for row in period_loans.order_by().values('location').annotate(
            n=Count('id'), readers=Count('reader', distinct=True))
    }
    open_now = counts(Loan.objects.filter(is_returned=False), 'location')
    overdue_now = counts(open_loans(only_overdue=True), 'location')
    nearest = counts(Reader.objects.exclude(nearest_location=None), 'nearest_location')

    type_names = {t.code: t.localized_name() for t in LocationType.objects.all()}
    rows = []
    for loc in Location.objects.all():
        loans_row = loan_rows.get(loc.pk, {})
        row = {
            'location': loc,
            'type': type_names.get(loc.type, loc.type),
            'batches_period': batches_period.get(loc.pk, 0),
            'batches_all': batches_all.get(loc.pk, 0),
            'books_period': books_period.get(loc.pk, 0),
            'books_all': books_all.get(loc.pk, 0),
            'in_point': in_point.get(loc.pk, 0),
            'loans': loans_row.get('n', 0),
            'readers': loans_row.get('readers', 0),
            'open': open_now.get(loc.pk, 0),
            'overdue': overdue_now.get(loc.pk, 0),
            'nearest': nearest.get(loc.pk, 0),
        }
        numbers = [v for k, v in row.items() if k not in ('location', 'type')]
        if loc.is_active or any(numbers):          # пустые выключенные пункты в таблицу не попадают
            rows.append(row)
    rows.sort(key=lambda r: (-r['loans'], -r['in_point'], r['location'].name))

    keys = ['batches_period', 'batches_all', 'books_period', 'books_all', 'in_point',
            'loans', 'open', 'overdue', 'nearest']
    totals = {k: sum(r[k] for r in rows) for k in keys}
    # читатель мог брать книги в нескольких пунктах, поэтому общее число считаем отдельно
    totals['readers'] = (period_loans.filter(reader__isnull=False).order_by()
                         .values('reader').distinct().count())
    return {'rows': rows, 'totals': totals}
