from django.contrib import messages
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import ReaderRegistrationForm, StyledAuthForm, BookRequestForm, RequestStatusForm
from .models import Reader, BookRequest

LIBRARIAN_LOGIN_URL = '/django-admin/login/'


def librarian_required(func):
    from django.contrib.auth.decorators import login_required as _lr
    return _lr(func, login_url=LIBRARIAN_LOGIN_URL)


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
            next_url = request.GET.get('next') or 'main:my'
            return redirect(next_url)
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
    return render(request, 'readers/my_cabinet.html', {
        'reader': reader,
        'requests': requests_qs,
    })


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
