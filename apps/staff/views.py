from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .decorators import admin_required, librarian_required
from .forms import StaffCreateForm, StaffEditForm, StaffInitForm, StaffLoginForm
from .models import StaffProfile


@librarian_required
def dashboard(request):
    from apps.catalog.models import Book
    from apps.deliveries.models import DeliveryBatch
    from apps.locations.models import Location
    from apps.readers.models import Reader, BookRequest, Loan

    from django.conf import settings
    from django.utils import timezone
    import datetime
    overdue_since = timezone.now() - datetime.timedelta(days=settings.LOAN_PERIOD_DAYS)

    stats = {
        'books_total': Book.objects.count(),
        'books_in_library': Book.objects.filter(status='IN_LIBRARY').count(),
        'books_in_delivery': Book.objects.filter(status='IN_DELIVERY').count(),
        'books_lost': Book.objects.filter(status='LOST').count(),
        'locations_total': Location.objects.filter(is_active=True).count(),
        'batches_active': DeliveryBatch.objects.filter(is_returned=False).count(),
        'readers_total': Reader.objects.count(),
        'requests_pending': BookRequest.objects.filter(status='PENDING').count(),
        'loans_active': Loan.objects.filter(is_returned=False).count(),
        'loans_overdue': Loan.objects.filter(is_returned=False, issued_at__lt=overdue_since).count(),
    }

    overdue_loans = (
        Loan.objects
        .filter(is_returned=False, issued_at__lt=overdue_since)
        .select_related('book', 'reader__user', 'location')
        .order_by('issued_at')[:10]
    )

    active_batches = (
        DeliveryBatch.objects
        .filter(is_returned=False)
        .select_related('location')
        .prefetch_related('items')
        .order_by('-delivery_date')[:10]
    )

    pending_requests = (
        BookRequest.objects
        .filter(status='PENDING')
        .select_related('reader__user', 'book')
        .order_by('created_at')[:10]
    )

    recent_loans = (
        Loan.objects
        .filter(is_returned=False)
        .select_related('book', 'reader__user', 'location')
        .order_by('-issued_at')[:10]
    )

    return render(request, 'staff/dashboard.html', {
        'stats': stats,
        'active_batches': active_batches,
        'pending_requests': pending_requests,
        'recent_loans': recent_loans,
        'overdue_loans': overdue_loans,
    })


@librarian_required
def stats_view(request):
    from django.db.models import Count
    from django.db.models.functions import TruncWeek
    from django.utils import timezone
    import datetime

    from apps.readers.models import Loan, BookRequest

    try:
        days = int(request.GET.get('days', 30))
    except ValueError:
        days = 30
    days = days if days in (7, 30, 90, 365) else 30
    since = timezone.now() - datetime.timedelta(days=days)

    loans_in_period = Loan.objects.filter(issued_at__gte=since)
    returns_in_period = Loan.objects.filter(is_returned=True, returned_at__gte=since)
    requests_in_period = BookRequest.objects.filter(created_at__gte=since)

    period_stats = {
        'loans_issued': loans_in_period.count(),
        'loans_returned': returns_in_period.count(),
        'requests_created': requests_in_period.count(),
        'requests_fulfilled': requests_in_period.filter(status='FULFILLED').count(),
    }

    top_genres = (
        loans_in_period
        .values('book__book_title__genre')
        .annotate(n=Count('id'))
        .order_by('-n')[:8]
    )
    from apps.catalog.models import Genre
    genre_names = dict(Genre.objects.values_list('code', 'name'))
    top_genres = [
        {'name': genre_names.get(g['book__book_title__genre'], g['book__book_title__genre'] or '—'), 'count': g['n']}
        for g in top_genres
    ]

    top_books = (
        loans_in_period
        .values('book__book_title__id', 'book__book_title__title', 'book__book_title__author')
        .annotate(n=Count('id'))
        .order_by('-n')[:10]
    )

    top_locations = (
        loans_in_period
        .values('location__id', 'location__name')
        .annotate(n=Count('id'))
        .order_by('-n')[:10]
    )

    weekly = (
        loans_in_period
        .annotate(week=TruncWeek('issued_at'))
        .values('week')
        .annotate(n=Count('id'))
        .order_by('week')
    )
    weekly_labels = [w['week'].strftime('%d.%m') for w in weekly]
    weekly_counts = [w['n'] for w in weekly]

    return render(request, 'staff/stats.html', {
        'days': days,
        'period_stats': period_stats,
        'top_genres': top_genres,
        'top_books': top_books,
        'top_locations': top_locations,
        'weekly_labels': weekly_labels,
        'weekly_counts': weekly_counts,
    })


def init_view(request):
    if StaffProfile.objects.filter(role=StaffProfile.ROLE_ADMIN).exists():
        return redirect('/admin-panel/login/')
    if request.method == 'POST':
        form = StaffInitForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Администратор создан. Добро пожаловать!')
            return redirect('/admin-panel/')
    else:
        form = StaffInitForm()
    return render(request, 'staff/init.html', {'form': form})


def _set_language_cookie(response, lang_code):
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME, lang_code,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )


def login_view(request):
    if request.user.is_authenticated:
        try:
            if request.user.staff_profile.is_active:
                return redirect('/admin-panel/')
        except Exception:
            pass
    if request.method == 'POST':
        form = StaffLoginForm(request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            response = redirect(request.GET.get('next') or '/admin-panel/')
            try:
                lang = user.staff_profile.language
            except Exception:
                lang = ''
            # Язык — на аккаунте сотрудника, а не куки браузера: если он уже
            # выбирал язык раньше, каждый вход должен открываться на нём,
            # даже с другого компьютера или после очистки куки.
            if lang:
                _set_language_cookie(response, lang)
            return response
    else:
        form = StaffLoginForm()
    return render(request, 'staff/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('/admin-panel/login/')


@require_POST
def set_language(request):
    """Переключение языка панели сотрудника — как встроенный django set_language,
    но дополнительно запоминает выбор в профиле сотрудника (если он вошёл в систему),
    чтобы язык не зависел от куки конкретного браузера."""
    lang_code = request.POST.get('language')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/admin-panel/'
    valid = bool(lang_code) and lang_code in dict(settings.LANGUAGES)

    if valid and request.user.is_authenticated:
        try:
            profile = request.user.staff_profile
            profile.language = lang_code
            profile.save(update_fields=['language'])
        except Exception:
            pass

    response = HttpResponseRedirect(next_url)
    if valid:
        _set_language_cookie(response, lang_code)
    return response


@admin_required
def action_log_view(request):
    from django.core.paginator import Paginator
    from .models import ActionLog

    logs = ActionLog.objects.select_related('actor')
    paginator = Paginator(logs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'staff/action_log.html', {'page_obj': page_obj})


@admin_required
def staff_list(request):
    staff = StaffProfile.objects.select_related('user').order_by('role', 'user__last_name')
    return render(request, 'staff/staff_list.html', {'staff': staff})


@admin_required
def staff_create(request):
    if request.method == 'POST':
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Сотрудник {user.get_full_name() or user.username} создан.')
            return redirect('staff:list')
    else:
        form = StaffCreateForm()
    return render(request, 'staff/staff_form.html', {'form': form, 'title': 'Новый сотрудник'})


@admin_required
def staff_edit(request, pk):
    profile = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
    if request.method == 'POST':
        form = StaffEditForm(request.POST, profile=profile)
        if form.is_valid():
            form.save(profile)
            messages.success(request, 'Данные сотрудника обновлены.')
            return redirect('staff:list')
    else:
        form = StaffEditForm(profile=profile)
    return render(request, 'staff/staff_form.html', {
        'form': form,
        'title': 'Редактировать сотрудника',
        'profile': profile,
    })


@admin_required
@require_POST
def staff_toggle_active(request, pk):
    profile = get_object_or_404(StaffProfile, pk=pk)
    if profile.user == request.user:
        messages.error(request, 'Нельзя заблокировать самого себя.')
        return redirect('staff:list')
    profile.is_active = not profile.is_active
    profile.save()
    action = 'активирован' if profile.is_active else 'заблокирован'
    messages.success(request, f'Сотрудник {profile.full_name} {action}.')
    return redirect('staff:list')
