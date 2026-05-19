from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required
from .forms import OrgLoginForm, OrgAccountCreateForm
from .models import OrgAccount

ORG_LOGIN_URL = '/org/login/'


def org_required(func):
    """Requires the user to have an OrgAccount."""
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

    from apps.catalog.models import Book
    genre_choices = Book.GENRE_CHOICES

    return render(request, 'organizations/dashboard.html', {
        'location': location,
        'books': books,
        'history': history,
        'q': q,
        'genre_filter': genre,
        'genre_choices': genre_choices,
    })


# ──────────────────────────────
# Admin: manage org accounts
# ──────────────────────────────

@librarian_required
def org_account_create(request, location_pk):
    from apps.locations.models import Location
    location = get_object_or_404(Location, pk=location_pk)

    # Check if account already exists
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
        org.user.delete()  # cascade deletes OrgAccount too
        messages.success(request, f'Аккаунт «{username}» удалён.')
    except OrgAccount.DoesNotExist:
        messages.warning(request, 'Аккаунт не найден.')
    return redirect('locations_admin:detail', pk=location_pk)
