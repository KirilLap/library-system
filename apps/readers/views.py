from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required
from .forms import ReaderRegistrationForm, StyledAuthForm, BookRequestForm, RequestStatusForm, ReaderProfileForm, FreeBookRequestForm
from .models import Reader, BookRequest, Loan


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
            if next_url:
                return redirect(next_url)
            # Redirect workers to their cabinet
            if hasattr(user, 'worker_profile') and user.worker_profile.is_active:
                return redirect('organizations:worker_cabinet')
            return redirect('main:my')
    else:
        form = StyledAuthForm(request)
    return render(request, 'readers/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('main:home')


# ──────────────────────────────
# Helpers
# ──────────────────────────────

def _require_phone(reader, request):
    """Возвращает redirect если у читателя нет телефона, иначе None."""
    if not reader.phone:
        messages.warning(request, 'Пожалуйста, укажите номер телефона — это необходимо для связи с вами.')
        return redirect('main:edit_profile')
    return None


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
    loan_history = (
        reader.loans
        .filter(is_returned=True)
        .select_related('book', 'location')
        .order_by('-issued_at')
    )

    # Открытые точки (махалля) с книгами и координатами — для поиска ближайшей.
    from apps.locations.models import Location
    open_points = [
        {'name': loc.name, 'slug': loc.slug, 'address': loc.address, 'lat': loc.latitude, 'lng': loc.longitude, 'books': loc.books_count}
        for loc in Location.objects.filter(
            is_active=True, type='MAHALLA', latitude__isnull=False, longitude__isnull=False
        )
    ]
    open_points = [p for p in open_points if p['books']]

    return render(request, 'readers/my_cabinet.html', {
        'reader': reader,
        'requests': requests_qs,
        'active_loans': active_loans,
        'loan_history': loan_history,
        'has_worker_profile': hasattr(request.user, 'worker_profile'),
        'phone_missing': not reader.phone,
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

    phone_redirect = _require_phone(reader, request)
    if phone_redirect:
        return phone_redirect

    error = None
    book = None

    if request.method == 'POST':
        inv = request.POST.get('inventory_number', '').strip()
        from apps.catalog.models import Book
        try:
            book = Book.objects.get(inventory_number=inv)
            location = book.current_location
            if location is None:
                error = 'Эта книга сейчас в библиотеке, а не на точке доставки.'
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
                  readers.filter(phone__icontains=q)
    return render(request, 'readers/reader_list.html', {'readers': readers, 'q': q})


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
    from apps.catalog.forms import BookForm
    from django.db.models import Q

    # Поиск существующей книги
    search_q = request.GET.get('search', '').strip()
    found_books = []
    if search_q:
        found_books = Book.objects.filter(
            Q(title__icontains=search_q) | Q(author__icontains=search_q)
        ).order_by('title')[:20]

    # Выбор книги из каталога
    form = BookForm(initial={
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
            form = BookForm(request.POST, request.FILES)
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
