"""Статистика по книгам за период (для страницы «Статистика» и выгрузки в Excel)."""
from django.db.models import Count
from django.db.models.functions import TruncWeek
from django.utils import timezone



def collect_stats(date_from, date_to, genre_limit=8, book_limit=10, location_limit=10):
    """Считает выдачи, возвраты, заявки, популярные жанры, книги и библиопункты за период
    (включительно; None вместо даты — без ограничения с этой стороны)."""
    from apps.catalog.models import Book, Genre
    from apps.deliveries.models import DeliveryItem
    from apps.readers.models import BookRequest, Loan
    from apps.readers.stats import open_loans

    def between(queryset, field):
        if date_from:
            queryset = queryset.filter(**{f'{field}__date__gte': date_from})
        if date_to:
            queryset = queryset.filter(**{f'{field}__date__lte': date_to})
        return queryset

    loans = between(Loan.objects.all(), 'issued_at')
    returns = between(Loan.objects.filter(is_returned=True, is_lost=False), 'returned_at')
    lost = between(Loan.objects.filter(is_lost=True), 'returned_at')
    requests = between(BookRequest.objects.all(), 'created_at')

    period_stats = {
        'loans_issued': loans.count(),
        'loans_returned': returns.count(),
        'loans_lost': lost.count(),
        'requests_created': requests.count(),
        'requests_fulfilled': requests.filter(status='FULFILLED').count(),
    }

    genre_names = {g.code: g.localized_name() for g in Genre.objects.all()}
    genre_rows = loans.values('book__book_title__genre').annotate(n=Count('id')).order_by('-n')
    top_genres = [
        {'name': genre_names.get(g['book__book_title__genre'], g['book__book_title__genre'] or '—'), 'count': g['n']}
        for g in genre_rows[:genre_limit]
    ]

    top_books = (
        loans.values('book__book_title__id', 'book__book_title__title', 'book__book_title__author')
        .annotate(n=Count('id')).order_by('-n', 'book__book_title__title')[:book_limit]
    )
    top_locations = (
        loans.values('location__id', 'location__name').annotate(n=Count('id')).order_by('-n')[:location_limit]
    )

    weekly = (
        loans.annotate(week=TruncWeek('issued_at')).values('week').annotate(n=Count('id')).order_by('week')
    )
    weeks = [(w['week'], w['n']) for w in weekly]

    in_points = dict(
        DeliveryItem.objects.filter(is_returned=False)
        .values_list('batch__location__name').annotate(n=Count('id'))
    )
    current = {
        'books_total': Book.objects.count(),
        'books_in_library': Book.objects.filter(status='IN_LIBRARY').count(),
        'books_in_points': Book.objects.filter(status='IN_DELIVERY').count(),
        'books_lost': Book.objects.filter(status='LOST').count(),
        'on_hands': open_loans().count(),
        'overdue': open_loans(only_overdue=True).count(),
    }

    return {
        'period_stats': period_stats,
        'top_genres': top_genres,
        'top_books': top_books,
        'top_locations': top_locations,
        'weekly_labels': [w.strftime('%d.%m') for w, _n in weeks],
        'weekly_counts': [n for _w, n in weeks],
        'weeks': weeks,
        'current': current,
        'books_in_points_by_location': in_points,
        'all_genres': [
            {'name': genre_names.get(g['book__book_title__genre'], g['book__book_title__genre'] or '—'), 'count': g['n']}
            for g in genre_rows
        ],
    }
