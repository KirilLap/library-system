from django.contrib import messages
from django.contrib.auth import login, logout
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
    }

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
            login(request, form.get_user())
            return redirect(request.GET.get('next') or '/admin-panel/')
    else:
        form = StaffLoginForm()
    return render(request, 'staff/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('/admin-panel/login/')


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
