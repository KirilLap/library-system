"""Статистика по книгам за период (для страницы «Статистика» и выгрузки в Excel)."""
import datetime

from django.db.models import Count
from django.db.models.functions import TruncWeek
from django.utils import timezone

PERIODS = (7, 30, 90, 365)


def clean_days(raw):
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return 30
    return days if days in PERIODS else 30


def collect_stats(days, genre_limit=8, book_limit=10, location_limit=10):
    """Считает выдачи, возвраты, заявки, популярные жанры, книги и библиопункты за последние days дней."""
    from apps.catalog.models import Book, Genre
    from apps.deliveries.models import DeliveryItem
    from apps.readers.models import BookRequest, Loan
    from apps.readers.stats import open_loans

    since = timezone.now() - datetime.timedelta(days=days)
    loans = Loan.objects.filter(issued_at__gte=since)
    requests = BookRequest.objects.filter(created_at__gte=since)

    period_stats = {
        'loans_issued': loans.count(),
        'loans_returned': Loan.objects.filter(is_returned=True, returned_at__gte=since).count(),
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
        'days': days,
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
