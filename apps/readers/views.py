from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from apps.staff.decorators import admin_required, librarian_required
from .forms import AgeGroupForm, ReaderRegistrationForm, StyledAuthForm, BookRequestForm, RequestStatusForm, ReaderProfileForm, FreeBookRequestForm, ReaderCreateForm
from .models import AgeGroupSettings, Reader, BookRequest, Loan


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


# ──────────────────────────────
# Public auth
# ──────────────────────────────

def register(request):
    if request.user.is_authenticated:
        return redirect('main:my')
    if request.method == 'POST':
        form = ReaderRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, 'Регистрация прошла успешно! Добро пожаловать.')
            return redirect('main:my')
    else:
        form = ReaderRegistrationForm()
    return render(request, 'readers/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('main:my')
    if request.method == 'POST':
        form = StyledAuthForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            next_url = request.GET.get('next')
            if _must_change_password(user):
                response = redirect('main:change_password')
            elif next_url:
                response = redirect(next_url)
            # Redirect workers to their cabinet
            elif hasattr(user, 'worker_profile') and user.worker_profile.is_active:
                response = redirect('organizations:worker_cabinet')
            else:
                response = redirect('main:my')
            # Язык — на аккаунте читателя, а не куки браузера: если он уже
            # выбирал язык раньше, вход должен открываться на нём даже с
            # другого устройства или после очистки куки.
            try:
                lang = user.reader_profile.language
            except Exception:
                lang = ''
            if lang:
                _set_language_cookie(response, lang)
            return response
    else:
        form = StyledAuthForm(request)
    return render(request, 'readers/login.html', {'form': form})


def _must_change_password(user):
    try:
        return user.reader_profile.must_change_password
    except Exception:
        return False


@login_required(login_url='/login/')
def change_password(request):
    """Первая смена пароля у читателя, которого зарегистрировал сотрудник."""
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        return redirect('main:home')

    if request.method == 'POST':
        form = SetPasswordForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            reader.must_change_password = False
            reader.save(update_fields=['must_change_password'])
            messages.success(request, 'Пароль изменён. Добро пожаловать!')
            return redirect('main:my')
    else:
        form = SetPasswordForm(request.user)
    for field in form.fields.values():
        field.widget.attrs['class'] = 'form-control'
    return render(request, 'readers/change_password.html', {
        'form': form, 'forced': reader.must_change_password,
    })


@require_POST
def logout_view(request):
    logout(request)
    return redirect('main:home')


@require_POST
def set_language(request):
    """Переключение языка для читателя/работника библиопункта — как встроенный
    django set_language, но дополнительно запоминает выбор в профиле читателя
    (если он вошёл в систему), чтобы язык не зависел от куки браузера."""
    lang_code = request.POST.get('language')
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or '/'
    valid = bool(lang_code) and lang_code in dict(settings.LANGUAGES)

    if valid and request.user.is_authenticated:
        try:
            profile = request.user.reader_profile
            profile.language = lang_code
            profile.save(update_fields=['language'])
        except Exception:
            pass

    response = HttpResponseRedirect(next_url)
    if valid:
        _set_language_cookie(response, lang_code)
    return response


# ──────────────────────────────
# Helpers
# ──────────────────────────────


# ──────────────────────────────
# Reader cabinet
# ──────────────────────────────

@login_required(login_url='/login/')
def my_cabinet(request):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        messages.error(request, 'Профиль читателя не найден.')
        return redirect('main:home')

    requests_qs = reader.requests.select_related('book', 'preferred_location').order_by('-created_at')
    active_loans = reader.active_loans
    overdue_loans = [loan for loan in active_loans if loan.is_overdue]
    queue_entries = reader.queue_entries.select_related('book').order_by('created_at')
    loan_history = (
        reader.loans
        .filter(is_returned=True)
        .select_related('book', 'location')
        .order_by('-issued_at')
    )

    # Открытые библиопункты (тип с is_open=True) с книгами и координатами — для поиска ближайшего.
    from apps.locations.models import Location, LocationType
    open_type_codes = LocationType.objects.filter(is_open=True).values_list('code', flat=True)
    open_points = [
        {'name': loc.name, 'slug': loc.slug, 'address': loc.address, 'lat': loc.latitude, 'lng': loc.longitude, 'books': loc.books_count}
        for loc in Location.objects.filter(
            is_active=True, is_public=True, type__in=open_type_codes,
            latitude__isnull=False, longitude__isnull=False,
        )
    ]
    open_points = [p for p in open_points if p['books']]

    return render(request, 'readers/my_cabinet.html', {
        'reader': reader,
        'requests': requests_qs,
        'active_loans': active_loans,
        'overdue_loans': overdue_loans,
        'queue_entries': queue_entries,
        'loan_history': loan_history,
        'has_worker_profile': hasattr(request.user, 'worker_profile'),
        'open_points': open_points,
    })


@login_required(login_url='/login/')
def edit_profile(request):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        return redirect('main:home')

    if request.method == 'POST':
        form = ReaderProfileForm(request.POST, instance=reader, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль обновлён.')
            return redirect('main:my')
    else:
        form = ReaderProfileForm(instance=reader, user=request.user)

    return render(request, 'readers/edit_profile.html', {'form': form})


@login_required(login_url='/login/')
def take_book(request):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        messages.error(request, 'Профиль читателя не найден.')
        return redirect('main:home')

    if reader.is_blocked:
        messages.error(request, 'Ваш аккаунт заблокирован.')
        return redirect('main:my')

    error = None
    book = None

    if request.method == 'POST':
        inv = request.POST.get('inventory_number', '').strip()
        from apps.catalog.models import Book
        try:
            book = Book.objects.get(inventory_number=inv)
            location = book.current_location
            if book.status == 'LOST':
                error = 'Эта книга числится утерянной.'
                book = None
            elif location is None:
                error = 'Эта книга сейчас в библиотеке, а не в библиопункте.'
                book = None
            elif Loan.objects.filter(book=book, is_returned=False).exists():
                error = 'Эта книга уже числится у другого читателя.'
                book = None
            else:
                Loan.objects.create(book=book, location=location, reader=reader)
                messages.success(request, f'Книга «{book.title}» отмечена как взятая. Приятного чтения!')
                return redirect('main:my')
        except Book.DoesNotExist:
            error = f'Книга с инвентарным номером «{inv}» не найдена. Проверьте номер на этикетке книги.'

    return render(request, 'readers/take_book.html', {
        'reader': reader,
        'error': error,
    })


@login_required(login_url='/login/')
@require_POST
def return_loan(request, pk):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        raise Http404
    loan = get_object_or_404(Loan, pk=pk, reader=reader, is_returned=False)
    loan.is_returned = True
    loan.returned_at = timezone.now()
    loan.save()
    messages.success(request, f'Книга «{loan.book.title}» отмечена как возвращённая. Спасибо!')
    return redirect('main:my')


@login_required(login_url='/login/')
@require_POST
def my_request_cancel(request, pk):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        raise Http404
    req = get_object_or_404(BookRequest, pk=pk, reader=reader)
    if req.status in ('PENDING', 'APPROVED'):
        req.status = 'CANCELLED'
        req.save()
        messages.success(request, 'Заявка отменена.')
    else:
        messages.warning(request, 'Эту заявку уже нельзя отменить.')
    return redirect('main:my')


# ──────────────────────────────
# Admin: readers
# ──────────────────────────────

@librarian_required
def reader_list(request):
    readers = Reader.objects.select_related('user')
    q = request.GET.get('q', '').strip()
    if q:
        readers = readers.filter(user__first_name__icontains=q) | \
                  readers.filter(user__last_name__icontains=q) | \
                  readers.filter(user__username__icontains=q) | \
                  readers.filter(card_id__icontains=q)
    return render(request, 'readers/reader_list.html', {'readers': readers, 'q': q})


@librarian_required
def reader_create(request):
    """Сотрудник вносит читателя вручную (для тех, кто не может зарегистрироваться сам)."""
    if request.method == 'POST':
        form = ReaderCreateForm(request.POST)
        if form.is_valid():
            user = form.save()
            from apps.staff.models import ActionLog
            ActionLog.log(request.user, f'Зарегистрировал читателя «{user.get_full_name()}» (ID {user.reader_profile.card_id})')
            messages.success(
                request,
                f'Читатель «{user.get_full_name()}» добавлен. '
                f'ID, он же логин и временный пароль: {user.reader_profile.card_id}. '
                'Передайте ему этот номер, при первом входе он задаст свой пароль.'
            )
            return redirect('readers_admin:detail', pk=user.reader_profile.pk)
    else:
        form = ReaderCreateForm()
    return render(request, 'readers/reader_form.html', {'form': form})


def _stats_context(request):
    """Общие данные для страниц статистики: период, границы возрастных групп, счётчики."""
    from django.conf import settings
    from .stats import current_boundaries, open_loans, parse_period, period_query
    boundaries = current_boundaries()
    period, date_from, date_to = parse_period(request.GET)
    return {
        'boundaries': boundaries,
        'period': period,
        'date_from': date_from,
        'date_to': date_to,
        'period_qs': period_query(period, date_from, date_to),
        'unreturned_count': open_loans().count(),
        'overdue_count': open_loans(only_overdue=True).count(),
        'loan_period_days': settings.LOAN_PERIOD_DAYS,
        'is_admin': request.user.staff_profile.role == 'ADMIN',
    }


@librarian_required
def reader_stats(request):
    """Статистика читателей по полу и возрастным группам, книги за период."""
    from .stats import loan_statistics, period_loans, reader_statistics
    ctx = _stats_context(request)
    boundaries = ctx['boundaries']
    ctx.update({
        'stats': reader_statistics(Reader.objects.all(), boundaries),
        'loan_stats': loan_statistics(period_loans(ctx['date_from'], ctx['date_to']), boundaries, top=10),
        'date_from': ctx['date_from'].isoformat() if ctx['date_from'] else '',
        'date_to': ctx['date_to'].isoformat() if ctx['date_to'] else '',
        'period_choices': [('7', 7), ('30', 30), ('90', 90), ('365', 365)],
        'form': AgeGroupForm(initial={'boundaries': ', '.join(str(b) for b in boundaries)}),
    })
    return render(request, 'readers/reader_stats.html', ctx)


@librarian_required
def reader_stats_readers(request):
    """Полный список читателей и взятых ими книг за период (с поиском и страницами)."""
    from django.core.paginator import Paginator
    from .stats import period_loans, reader_loan_rows
    ctx = _stats_context(request)
    rows = reader_loan_rows(period_loans(ctx['date_from'], ctx['date_to']))
    q = request.GET.get('q', '').strip()
    if q:
        needle = q.lower()
        rows = [r for r in rows if needle in r['reader'].full_name.lower()
                or needle in (r['reader'].card_id or '') or needle in r['reader'].user.username.lower()]
    paginator = Paginator(rows, 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    ctx.update({
        'rows': page_obj, 'page_obj': page_obj, 'q': q,
        'total_readers': paginator.count,
        'page_range': paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1),
        'querystring': params.urlencode(),
        'date_from': ctx['date_from'].isoformat() if ctx['date_from'] else '',
        'date_to': ctx['date_to'].isoformat() if ctx['date_to'] else '',
    })
    return render(request, 'readers/reader_stats_readers.html', ctx)


@librarian_required
def reader_stats_unreturned(request):
    """Не возвращённые книги; ?only=overdue оставляет только просроченные."""
    from django.core.paginator import Paginator
    from .stats import open_loans
    ctx = _stats_context(request)
    only_overdue = request.GET.get('only') == 'overdue'
    paginator = Paginator(open_loans(only_overdue=only_overdue), 50)
    page_obj = paginator.get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    ctx.update({
        'loans': page_obj, 'page_obj': page_obj, 'only_overdue': only_overdue,
        'page_range': paginator.get_elided_page_range(page_obj.number, on_each_side=2, on_ends=1),
        'querystring': params.urlencode(),
    })
    return render(request, 'readers/reader_stats_unreturned.html', ctx)


@librarian_required
def reader_stats_export(request):
    """Скачать статистику в Excel. Списки с именами читателей попадают в файл только у администратора."""
    from django.http import HttpResponse
    from .stats import loan_statistics, open_loans, period_loans, reader_loan_rows, reader_statistics
    from .stats_export import build_stats_workbook
    ctx = _stats_context(request)
    boundaries = ctx['boundaries']
    loans = period_loans(ctx['date_from'], ctx['date_to'])
    loan_stats = loan_statistics(loans, boundaries, top=10)
    if ctx['period'] == 'all':
        period_text = gettext('Всё время')
    else:
        fmt = lambda d: d.strftime('%d.%m.%Y') if d else '…'
        period_text = f"{fmt(ctx['date_from'])} – {fmt(ctx['date_to'])}"
    is_admin = ctx['is_admin']
    unreturned_qs = open_loans()
    content = build_stats_workbook(
        stats=reader_statistics(Reader.objects.all(), boundaries),
        loan_stats=loan_stats,
        period_text=period_text,
        include_readers=is_admin,
        reader_rows=reader_loan_rows(loans) if is_admin else [],
        unreturned={'count': ctx['unreturned_count'], 'overdue': ctx['overdue_count'],
                    'loans': list(unreturned_qs) if is_admin else []},
        loan_period_days=ctx['loan_period_days'],
    )
    response = HttpResponse(
        content, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="readers-stats-{timezone.localdate().isoformat()}.xlsx"'
    return response


@admin_required
@require_POST
def reader_stats_settings(request):
    """Администратор меняет границы возрастных групп."""
    form = AgeGroupForm(request.POST)
    if form.is_valid():
        settings_obj = AgeGroupSettings.get_solo()
        settings_obj.boundaries = form.cleaned_data['boundaries']
        settings_obj.save()
        messages.success(request, 'Возрастные группы сохранены.')
    else:
        for error in form.errors.get('boundaries', []):
            messages.error(request, error)
    return redirect('readers_admin:stats')


def _staff_next(request):
    """Куда вернуть сотрудника после действия: только внутри панели, иначе — список не возвращённых."""
    from django.utils.http import url_has_allowed_host_and_scheme
    target = request.POST.get('next', '')
    if target.startswith('/admin-panel/') and url_has_allowed_host_and_scheme(target, allowed_hosts=None):
        return target
    return reverse('readers_admin:stats_unreturned')


@librarian_required
@require_POST
def loan_return_staff(request, pk):
    """Сотрудник принимает возврат книги за читателя (например, просроченной)."""
    from apps.staff.models import ActionLog
    loan = get_object_or_404(Loan.objects.select_related('book__book_title', 'reader__user'),
                             pk=pk, is_returned=False)
    loan.is_returned = True
    loan.returned_at = timezone.now()
    loan.save()
    who = loan.reader.full_name if loan.reader else 'читателя без аккаунта'
    ActionLog.log(request.user, f'Принял возврат книги «{loan.book.title}» ({loan.book.inventory_number}) от {who}')
    messages.success(request, f'Книга «{loan.book.title}» принята назад.')
    return redirect(_staff_next(request))


@librarian_required
@require_POST
def loan_lost_staff(request, pk):
    """Книгу не вернули, она утеряна: остаётся в базе, но скрывается из каталога и не ставится в пункты."""
    from django.db import transaction
    from apps.catalog.models import Book
    from apps.deliveries.models import DeliveryItem
    from apps.staff.models import ActionLog
    with transaction.atomic():
        loan = get_object_or_404(Loan.objects.select_related('book__book_title', 'reader__user'),
                                 pk=pk, is_returned=False)
        now = timezone.now()
        loan.is_returned = True
        loan.is_lost = True
        loan.returned_at = now
        loan.save()
        # Книга больше не числится в библиопункте; статус «Утеряна» (mark_returned его бы сбросил, поэтому закрываем вручную)
        DeliveryItem.objects.filter(book=loan.book, is_returned=False).update(is_returned=True, returned_at=now)
        Book.objects.filter(pk=loan.book_id).update(status='LOST')
    who = loan.reader.full_name if loan.reader else 'читателя без аккаунта'
    ActionLog.log(request.user, f'Отметил книгу «{loan.book.title}» ({loan.book.inventory_number}) '
                                f'как утерянную (была у {who})')
    messages.warning(request, f'Книга «{loan.book.title}» отмечена как утерянная: из каталога она скрыта.')
    return redirect(_staff_next(request))


@librarian_required
def reader_detail(request, pk):
    reader = get_object_or_404(Reader.objects.select_related('user'), pk=pk)
    reader_requests = reader.requests.select_related('book').order_by('-created_at')
    active_loans = reader.loans.filter(is_returned=False).select_related('book', 'location')
    loan_history = reader.loans.filter(is_returned=True).select_related('book', 'location').order_by('-issued_at')
    return render(request, 'readers/reader_detail.html', {
        'reader': reader,
        'reader_requests': reader_requests,
        'active_loans': active_loans,
        'loan_history': loan_history,
    })


@librarian_required
@require_POST
def reader_toggle_block(request, pk):
    reader = get_object_or_404(Reader, pk=pk)
    reader.is_blocked = not reader.is_blocked
    reader.save()
    action = 'заблокирован' if reader.is_blocked else 'разблокирован'
    messages.success(request, f'Читатель {reader.full_name} {action}.')

    from apps.staff.models import ActionLog
    ActionLog.log(request.user, f'{action.capitalize()} читатель «{reader.full_name}»')

    return redirect('readers_admin:detail', pk=pk)


@librarian_required
def reader_delete(request, pk):
    reader = get_object_or_404(Reader.objects.select_related('user'), pk=pk)
    has_loans = reader.loans.exists()

    if request.method == 'POST':
        if has_loans:
            messages.error(
                request,
                f'Нельзя удалить читателя {reader.full_name}: есть история выдач книг. '
                f'Используйте блокировку вместо удаления.'
            )
            return redirect('readers_admin:detail', pk=pk)

        name = reader.full_name
        reader.user.delete()  # каскадно удалит и профиль читателя, и его заявки
        messages.success(request, f'Читатель {name} удалён.')

        from apps.staff.models import ActionLog
        ActionLog.log(request.user, f'Удалил читателя «{name}»')

        return redirect('readers_admin:index')

    return render(request, 'readers/reader_confirm_delete.html', {
        'reader': reader,
        'has_loans': has_loans,
    })


# ──────────────────────────────
# Admin: requests
# ──────────────────────────────

def _change_request_status(request, pk, new_status, success_msg):
    """Общий хелпер смены статуса с проверкой допустимости перехода."""
    req = get_object_or_404(BookRequest, pk=pk)
    if req.is_final:
        messages.error(request, 'Эта заявка завершена и не может быть изменена.')
    elif new_status not in req.allowed_next_statuses:
        messages.error(request, f'Переход из «{req.get_status_display()}» в этот статус недопустим.')
    else:
        old_status_display = req.get_status_display()
        req.status = new_status
        note = request.POST.get('librarian_note', '').strip()
        if note:
            req.librarian_note = note
        req.save()
        messages.success(request, success_msg)

        from apps.staff.models import ActionLog
        ActionLog.log(
            request.user,
            f'Заявка #{req.pk} ({req.reader.full_name}): «{old_status_display}» → «{req.get_status_display()}»',
        )
    next_url = request.POST.get('next') or 'readers_admin_extra:requests'
    # Если next_url — имя URL-паттерна, делаем redirect по имени
    if next_url.startswith('/'):
        from django.shortcuts import redirect as _redirect
        return _redirect(next_url)
    from django.urls import reverse
    return redirect(reverse(next_url))


@librarian_required
@require_POST
def request_approve(request, pk):
    return _change_request_status(request, pk, 'APPROVED', f'Заявка #{pk} одобрена.')


@librarian_required
@require_POST
def request_reject(request, pk):
    return _change_request_status(request, pk, 'REJECTED', f'Заявка #{pk} отклонена.')


@librarian_required
@require_POST
def request_purchasing(request, pk):
    return _change_request_status(request, pk, 'PURCHASING', f'Заявка #{pk} переведена в статус «Закупается».')


@librarian_required
@require_POST
def request_fulfill(request, pk):
    return _change_request_status(request, pk, 'FULFILLED', f'Заявка #{pk} выполнена.')


@librarian_required
def request_fulfill_with_book(request, pk):
    """
    Страница выполнения заявки — привязка книги из каталога или создание новой.
    Используется для заявок со статусом PURCHASING или APPROVED (если книги не было).
    """
    req = get_object_or_404(
        BookRequest.objects.select_related('reader__user', 'preferred_location'),
        pk=pk
    )

    if req.is_final:
        messages.error(request, 'Эта заявка уже завершена.')
        return redirect('readers_admin_extra:request_detail', pk=pk)

    if 'FULFILLED' not in req.allowed_next_statuses:
        messages.error(request, 'Нельзя выполнить заявку с текущим статусом.')
        return redirect('readers_admin_extra:request_detail', pk=pk)

    from apps.catalog.models import Book, Genre, Language
    from apps.catalog.forms import NewBookForm
    from django.db.models import Q

    # Поиск существующей книги
    search_q = request.GET.get('search', '').strip()
    found_books = []
    if search_q:
        found_books = Book.objects.filter(
            Q(book_title__title__icontains=search_q) | Q(book_title__author__icontains=search_q)
        ).select_related('book_title').order_by('book_title__title')[:20]

    # Выбор книги из каталога
    form = NewBookForm(initial={
        'title': req.requested_title,
        'author': req.requested_author,
    })

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'select':
            # Выбрана существующая книга
            book_id = request.POST.get('book_id')
            try:
                book = Book.objects.get(pk=book_id)
                req.book = book
                req.status = 'FULFILLED'
                note = request.POST.get('librarian_note', '').strip()
                if note:
                    req.librarian_note = note
                req.save()
                messages.success(
                    request,
                    f'Заявка выполнена! Книга «{book.title}» привязана к заявке.'
                )
                from apps.staff.models import ActionLog
                ActionLog.log(
                    request.user,
                    f'Заявка #{req.pk} ({req.reader.full_name}): выполнена, привязана книга «{book.title}»',
                )
                return redirect('readers_admin_extra:request_detail', pk=pk)
            except Book.DoesNotExist:
                messages.error(request, 'Книга не найдена.')

        elif action == 'create':
            # Создать новую книгу
            form = NewBookForm(request.POST, request.FILES)
            if form.is_valid():
                book = form.save()
                req.book = book
                req.status = 'FULFILLED'
                note = request.POST.get('librarian_note', '').strip()
                if note:
                    req.librarian_note = note
                req.save()
                messages.success(
                    request,
                    f'Книга «{book.title}» добавлена в каталог и привязана к заявке!'
                )
                from apps.staff.models import ActionLog
                ActionLog.log(
                    request.user,
                    f'Заявка #{req.pk} ({req.reader.full_name}): выполнена, добавлена новая книга «{book.title}»',
                )
                return redirect('readers_admin_extra:request_detail', pk=pk)

    return render(request, 'readers/request_fulfill_book.html', {
        'req': req,
        'form': form,
        'search_q': search_q,
        'found_books': found_books,
        'genres': Genre.objects.all(),
        'languages': Language.objects.all(),
    })


@librarian_required
def request_list(request):
    requests_qs = BookRequest.objects.select_related('reader__user', 'book', 'preferred_location')
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    return render(request, 'readers/request_list.html', {
        'requests': requests_qs,
        'status_filter': status_filter,
        'status_choices': BookRequest.STATUS_CHOICES,
        'pending_count': BookRequest.objects.filter(status='PENDING').count(),
    })


@librarian_required
def request_detail(request, pk):
    req = get_object_or_404(
        BookRequest.objects.select_related('reader__user', 'book', 'preferred_location'),
        pk=pk
    )
    # Форма только для ответа библиотекаря (librarian_note)
    from django import forms as django_forms

    class LibrarianNoteForm(django_forms.ModelForm):
        class Meta:
            model = BookRequest
            fields = ['librarian_note']
            widgets = {
                'librarian_note': django_forms.Textarea(attrs={
                    'rows': 3, 'class': 'form-control',
                    'placeholder': 'Сообщение для читателя…'
                }),
            }
            labels = {'librarian_note': 'Ответ читателю'}

    if request.method == 'POST':
        form = LibrarianNoteForm(request.POST, instance=req)
        if form.is_valid():
            form.save()
            messages.success(request, 'Ответ сохранён.')
            return redirect('readers_admin_extra:request_detail', pk=pk)
    else:
        form = LibrarianNoteForm(instance=req)

    return render(request, 'readers/request_detail.html', {'req': req, 'form': form})
