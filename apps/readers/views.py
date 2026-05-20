from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required
from .forms import ReaderRegistrationForm, StyledAuthForm, BookRequestForm, RequestStatusForm
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
# Reader cabinet
# ──────────────────────────────

@login_required(login_url='/login/')
def my_cabinet(request):
    try:
        reader = request.user.reader_profile
    except Reader.DoesNotExist:
        messages.error(request, 'Профиль читателя не найден.')
        return redirect('main:home')

    requests_qs = reader.requests.select_related('book').order_by('-created_at')
    active_loans = reader.active_loans
    return render(request, 'readers/my_cabinet.html', {
        'reader': reader,
        'requests': requests_qs,
        'active_loans': active_loans,
        'has_worker_profile': hasattr(request.user, 'worker_profile'),
    })


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
    return render(request, 'readers/reader_detail.html', {
        'reader': reader,
        'reader_requests': reader_requests,
    })


@librarian_required
@require_POST
def reader_toggle_block(request, pk):
    reader = get_object_or_404(Reader, pk=pk)
    reader.is_blocked = not reader.is_blocked
    reader.save()
    action = 'заблокирован' if reader.is_blocked else 'разблокирован'
    messages.success(request, f'Читатель {reader.full_name} {action}.')
    return redirect('readers_admin:detail', pk=pk)


# ──────────────────────────────
# Admin: requests
# ──────────────────────────────

@librarian_required
def request_list(request):
    requests_qs = BookRequest.objects.select_related('reader__user', 'book')
    status_filter = request.GET.get('status', '')
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    return render(request, 'readers/request_list.html', {
        'requests': requests_qs,
        'status_filter': status_filter,
        'status_choices': BookRequest.STATUS_CHOICES,
    })


@librarian_required
def request_detail(request, pk):
    req = get_object_or_404(BookRequest.objects.select_related('reader__user', 'book'), pk=pk)
    if request.method == 'POST':
        form = RequestStatusForm(request.POST, instance=req)
        if form.is_valid():
            form.save()
            messages.success(request, 'Статус заявки обновлён.')
            return redirect('readers_admin_extra:request_detail', pk=pk)
    else:
        form = RequestStatusForm(instance=req)
    return render(request, 'readers/request_detail.html', {'req': req, 'form': form})
