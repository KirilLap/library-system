from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required
from .forms import OrgLoginForm, OrgAccountCreateForm, LocationWorkerCreateForm
from .models import OrgAccount, LocationWorker

ORG_LOGIN_URL = '/org/login/'
WORKER_LOGIN_URL = '/login/'


def org_required(func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(ORG_LOGIN_URL)
        try:
            _ = request.user.org_account
        except OrgAccount.DoesNotExist:
            messages.error(request, 'У вас нет доступа к кабинету организации.')
            return redirect(ORG_LOGIN_URL)
        return func(request, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def worker_required(func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(f'{WORKER_LOGIN_URL}?next={request.path}')
        try:
            worker = request.user.worker_profile
            if not worker.is_active:
                messages.error(request, 'Ваш аккаунт работника деактивирован.')
                return redirect('main:home')
        except LocationWorker.DoesNotExist:
            messages.error(request, 'У вас нет доступа к кабинету работника.')
            return redirect('main:home')
        return func(request, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# ──────────────────────────────
# Org auth
# ──────────────────────────────

def org_login(request):
    if request.user.is_authenticated:
        try:
            _ = request.user.org_account
            return redirect('organizations:dashboard')
        except OrgAccount.DoesNotExist:
            pass

    if request.method == 'POST':
        form = OrgLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            try:
                _ = user.org_account
            except OrgAccount.DoesNotExist:
                messages.error(request, 'Этот аккаунт не привязан ни к одной организации.')
                return render(request, 'organizations/login.html', {'form': form})
            login(request, user)
            return redirect('organizations:dashboard')
    else:
        form = OrgLoginForm(request)
    return render(request, 'organizations/login.html', {'form': form})


@require_POST
def org_logout(request):
    logout(request)
    return redirect('organizations:login')


# ──────────────────────────────
# Org dashboard
# ──────────────────────────────

@org_required
def org_dashboard(request):
    org = request.user.org_account
    location = org.location
    books = location.get_current_books()

    q = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')

    if q:
        books = [b for b in books if q.lower() in b.title.lower() or q.lower() in b.author.lower()]
    if genre:
        books = [b for b in books if b.genre == genre]

    history = location.get_delivery_history()

    from apps.catalog.models import Genre
    genre_choices = list(Genre.objects.values_list('code', 'name'))

    return render(request, 'organizations/dashboard.html', {
        'location': location,
        'books': books,
        'history': history,
        'q': q,
        'genre_filter': genre,
        'genre_choices': genre_choices,
    })


# ──────────────────────────────
# Worker cabinet
# ──────────────────────────────

@worker_required
def worker_cabinet(request):
    worker = request.user.worker_profile
    location = worker.location
    from apps.readers.models import Loan
    active_loans = Loan.objects.filter(
        location=location, is_returned=False
    ).select_related('book', 'reader__user').order_by('-issued_at')
    return render(request, 'organizations/worker_cabinet.html', {
        'worker': worker,
        'location': location,
        'active_loans': active_loans,
    })


@worker_required
def worker_issue(request):
    worker = request.user.worker_profile
    location = worker.location
    book = None
    reader = None
    error = None

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'lookup_book':
            inv = request.POST.get('inventory_number', '').strip()
            from apps.catalog.models import Book
            try:
                book = Book.objects.get(inventory_number=inv)
                # Verify it's at this location
                if book.current_location != location:
                    error = f'Книга «{book.title}» не находится на вашей точке.'
                    book = None
                else:
                    from apps.readers.models import Loan
                    if Loan.objects.filter(book=book, is_returned=False).exists():
                        error = f'Книга «{book.title}» уже выдана и не возвращена.'
                        book = None
            except Book.DoesNotExist:
                error = f'Книга с инв. номером «{inv}» не найдена.'

        elif action == 'issue':
            inv = request.POST.get('inventory_number', '').strip()
            reader_pk = request.POST.get('reader_pk', '').strip()
            from apps.catalog.models import Book
            from apps.readers.models import Loan, Reader
            try:
                book = Book.objects.get(inventory_number=inv)
                reader = get_object_or_404(Reader, pk=reader_pk)
                if book.current_location != location:
                    error = 'Книга не на вашей точке.'
                elif Loan.objects.filter(book=book, is_returned=False).exists():
                    error = 'Книга уже выдана.'
                else:
                    Loan.objects.create(
                        book=book,
                        location=location,
                        reader=reader,
                        issued_by=worker,
                    )
                    messages.success(
                        request,
                        f'Книга «{book.title}» выдана читателю {reader.full_name}.'
                    )
                    return redirect('organizations:worker_cabinet')
            except Book.DoesNotExist:
                error = 'Книга не найдена.'

    from apps.readers.models import Reader
    readers = Reader.objects.filter(
        affiliated_location=location
    ).select_related('user').order_by('user__last_name')

    return render(request, 'organizations/worker_issue.html', {
        'worker': worker,
        'location': location,
        'book': book,
        'readers': readers,
        'error': error,
        'inv_value': request.POST.get('inventory_number', ''),
    })


@worker_required
def worker_return(request):
    worker = request.user.worker_profile
    location = worker.location
    from apps.readers.models import Loan
    active_loans = Loan.objects.filter(
        location=location, is_returned=False
    ).select_related('book', 'reader__user').order_by('book__title')

    if request.method == 'POST':
        loan_pk = request.POST.get('loan_pk')
        loan = get_object_or_404(Loan, pk=loan_pk, location=location, is_returned=False)
        loan.is_returned = True
        loan.returned_at = timezone.now()
        loan.save()
        messages.success(request, f'Книга «{loan.book.title}» принята назад.')
        return redirect('organizations:worker_return')

    return render(request, 'organizations/worker_return.html', {
        'worker': worker,
        'location': location,
        'active_loans': active_loans,
    })


@worker_required
def worker_readers(request):
    worker = request.user.worker_profile
    location = worker.location
    from apps.readers.models import Reader
    readers = Reader.objects.filter(
        affiliated_location=location
    ).select_related('user').order_by('user__last_name')
    return render(request, 'organizations/worker_readers.html', {
        'worker': worker,
        'location': location,
        'readers': readers,
    })


@worker_required
def worker_register_reader(request):
    worker = request.user.worker_profile
    location = worker.location
    from apps.readers.forms import ReaderRegistrationForm

    if request.method == 'POST':
        form = ReaderRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            from apps.readers.models import Reader
            Reader.objects.filter(user=user).update(affiliated_location=location)
            messages.success(
                request,
                f'Читатель «{user.get_full_name() or user.username}» зарегистрирован и прикреплён к точке «{location.name}».'
            )
            return redirect('organizations:worker_readers')
    else:
        form = ReaderRegistrationForm()

    return render(request, 'organizations/worker_register_reader.html', {
        'worker': worker,
        'location': location,
        'form': form,
    })


# ──────────────────────────────
# Admin: manage org accounts
# ──────────────────────────────

@librarian_required
def org_account_create(request, location_pk):
    from apps.locations.models import Location
    location = get_object_or_404(Location, pk=location_pk)

    if hasattr(location, 'org_account'):
        messages.warning(request, 'У этой точки уже есть аккаунт организации.')
        return redirect('locations_admin:detail', pk=location_pk)

    if request.method == 'POST':
        form = OrgAccountCreateForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            OrgAccount.objects.create(user=user, location=location)
            messages.success(
                request,
                f'Аккаунт «{user.username}» создан и привязан к точке «{location.name}».'
            )
            return redirect('locations_admin:detail', pk=location_pk)
    else:
        form = OrgAccountCreateForm()

    return render(request, 'organizations/org_account_form.html', {
        'form': form,
        'location': location,
    })


@librarian_required
@require_POST
def org_account_delete(request, location_pk):
    from apps.locations.models import Location
    location = get_object_or_404(Location, pk=location_pk)
    try:
        org = location.org_account
        username = org.user.username
        org.user.delete()
        messages.success(request, f'Аккаунт «{username}» удалён.')
    except OrgAccount.DoesNotExist:
        messages.warning(request, 'Аккаунт не найден.')
    return redirect('locations_admin:detail', pk=location_pk)


@librarian_required
def worker_add(request, location_pk):
    from apps.locations.models import Location
    location = get_object_or_404(Location, pk=location_pk)

    if request.method == 'POST':
        form = LocationWorkerCreateForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = User.objects.create_user(
                username=cd['username'],
                password=cd['password'],
                first_name=cd['first_name'],
                last_name=cd['last_name'],
            )
            worker = LocationWorker.objects.create(user=user, location=location)
            # Also create a Reader profile so worker can borrow books personally
            from apps.readers.models import Reader
            Reader.objects.create(user=user, affiliated_location=location)
            messages.success(
                request,
                f'Работник «{worker.full_name}» добавлен к точке «{location.name}».'
            )
            return redirect('locations_admin:detail', pk=location_pk)
    else:
        form = LocationWorkerCreateForm()

    return render(request, 'organizations/add_worker.html', {
        'form': form,
        'location': location,
    })


@librarian_required
@require_POST
def worker_toggle(request, worker_pk):
    worker = get_object_or_404(LocationWorker, pk=worker_pk)
    worker.is_active = not worker.is_active
    worker.save()
    status = 'активирован' if worker.is_active else 'деактивирован'
    messages.success(request, f'Работник {worker.full_name} {status}.')
    return redirect('locations_admin:detail', pk=worker.location_id)
