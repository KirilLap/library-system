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

    from apps.readers.stats import open_loans
    overdue_qs = open_loans(only_overdue=True)
    from apps.readers.passwords import pending_count
    reset_pending = pending_count() if request.user.staff_profile.role == 'ADMIN' else 0

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
        'loans_overdue': overdue_qs.count(),
    }

    overdue_loans = overdue_qs[:10]

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
        'reset_pending': reset_pending,
    })


def _books_period(request):
    from apps.readers.stats import parse_period, period_query
    period, date_from, date_to = parse_period(request.GET)
    return period, date_from, date_to, period_query(period, date_from, date_to)


@librarian_required
def stats_view(request):
    from .stats_books import collect_stats
    period, date_from, date_to, period_qs = _books_period(request)
    ctx = collect_stats(date_from, date_to)
    ctx.update({
        'tab': 'books',
        'period': period,
        'period_qs': period_qs,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'period_choices': [('7', 7), ('30', 30), ('90', 90), ('365', 365)],
    })
    return render(request, 'staff/stats.html', ctx)


@librarian_required
def stats_export(request):
    """Скачать статистику по книгам в Excel (в файле нет данных о конкретных читателях)."""
    from django.http import HttpResponse
    from django.utils import timezone
    from django.utils.translation import gettext
    from .stats_books import collect_stats
    from .stats_export import build_books_workbook
    period, date_from, date_to, _qs = _books_period(request)
    data = collect_stats(date_from, date_to, genre_limit=1000, book_limit=100, location_limit=1000)
    if period == 'all':
        period_text = gettext('Всё время')
    else:
        fmt = lambda d: d.strftime('%d.%m.%Y') if d else '…'
        period_text = f'{fmt(date_from)} – {fmt(date_to)}'
    response = HttpResponse(
        build_books_workbook(data, period_text),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="books-stats-{timezone.localdate().isoformat()}.xlsx"'
    return response


@librarian_required
def stats_points(request):
    """Статистика по библиопунктам: партии, завезённые книги, выдачи, читатели."""
    from .stats_points import collect_points_stats
    period, date_from, date_to, period_qs = _books_period(request)
    data = collect_points_stats(date_from, date_to)
    data.update({
        'tab': 'points',
        'period': period,
        'period_qs': period_qs,
        'date_from': date_from.isoformat() if date_from else '',
        'date_to': date_to.isoformat() if date_to else '',
        'period_choices': [('7', 7), ('30', 30), ('90', 90), ('365', 365)],
    })
    return render(request, 'staff/stats_points.html', data)


@librarian_required
def stats_points_export(request):
    """Скачать статистику по библиопунктам в Excel (данных о конкретных читателях в файле нет)."""
    from django.http import HttpResponse
    from django.utils import timezone
    from django.utils.translation import gettext
    from .stats_export import build_points_workbook
    from .stats_points import collect_points_stats
    period, date_from, date_to, _qs = _books_period(request)
    if period == 'all':
        period_text = gettext('Всё время')
    else:
        fmt = lambda d: d.strftime('%d.%m.%Y') if d else '…'
        period_text = f'{fmt(date_from)} – {fmt(date_to)}'
    response = HttpResponse(
        build_points_workbook(collect_points_stats(date_from, date_to), period_text),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="points-stats-{timezone.localdate().isoformat()}.xlsx"'
    return response


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


@admin_required
@require_POST
def staff_delete(request, pk):
    """Полное удаление учётной записи сотрудника (в отличие от блокировки). Журнал действий остаётся."""
    from django.db import transaction
    from .models import ActionLog
    profile = get_object_or_404(StaffProfile.objects.select_related('user'), pk=pk)
    user = profile.user
    if user == request.user:
        messages.error(request, 'Нельзя удалить самого себя.')
        return redirect('staff:list')
    if any(hasattr(user, attr) for attr in ('reader_profile', 'org_account', 'worker_profile')):
        messages.error(request, 'Эта учётная запись связана ещё и с читателем или организацией, '
                                'удалять её нельзя. Заблокируйте сотрудника.')
        return redirect('staff:list')
    name = profile.full_name
    with transaction.atomic():
        ActionLog.log(request.user, f'Удалил учётную запись сотрудника «{name}» (логин {user.username})')
        user.delete()
    messages.success(request, f'Сотрудник {name} удалён.')
    return redirect('staff:list')
