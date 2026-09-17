from django.contrib import messages
from django.db.models import ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.staff.decorators import librarian_required
from .forms import LocationForm
from .models import Location


# ──────────────────────────────
# Admin views
# ──────────────────────────────

@librarian_required
def location_list(request):
    locations = Location.objects.all()
    show_inactive = request.GET.get('inactive')
    if not show_inactive:
        locations = locations.filter(is_active=True)
    return render(request, 'locations/location_list.html', {
        'locations': locations,
        'show_inactive': show_inactive,
    })


@librarian_required
def location_create(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            location = form.save()
            messages.success(request, f'Библиопункт «{location.name}» создан. QR-код сгенерирован.')
            return redirect('locations_admin:detail', pk=location.pk)
    else:
        form = LocationForm()
    return render(request, 'locations/location_form.html', {
        'form': form,
        'title': 'Добавить библиопункт',
    })


@librarian_required
def location_update(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, f'Библиопункт «{location.name}» обновлён.')
            return redirect('locations_admin:detail', pk=location.pk)
    else:
        form = LocationForm(instance=location)
    return render(request, 'locations/location_form.html', {
        'form': form,
        'location': location,
        'title': f'Редактировать: {location.name}',
    })


@librarian_required
def location_detail(request, pk):
    location = get_object_or_404(Location, pk=pk)
    books = location.get_current_books()

    q = request.GET.get('q', '').strip()
    if q:
        books = [b for b in books if q.lower() in b.title.lower()]

    history = location.get_delivery_history()

    return render(request, 'locations/location_detail.html', {
        'location': location,
        'books': books,
        'history': history,
        'q': q,
    })


@librarian_required
def location_delete(request, pk):
    location = get_object_or_404(Location, pk=pk)
    has_batches = location.batches.exists()

    if request.method == 'POST':
        if has_batches:
            messages.error(
                request,
                f'Нельзя удалить библиопункт «{location.name}»: есть история партий доставки. '
                f'Деактивируйте библиопункт вместо удаления.'
            )
            return redirect('locations_admin:detail', pk=pk)

        name = location.name
        if hasattr(location, 'org_account'):
            location.org_account.user.delete()
        try:
            location.delete()
        except ProtectedError:
            messages.error(request, f'Нельзя удалить библиопункт «{name}»: есть связанные записи о выдаче книг.')
            return redirect('locations_admin:detail', pk=pk)
        messages.success(request, f'Библиопункт «{name}» удалён.')
        from apps.staff.models import ActionLog
        ActionLog.log(request.user, f'Удалил библиопункт «{name}»')
        return redirect('locations_admin:index')

    return render(request, 'locations/location_confirm_delete.html', {
        'location': location,
        'has_batches': has_batches,
    })


@librarian_required
def location_qr_download(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if not location.qr_code:
        messages.error(request, 'QR-код не найден. Попробуйте сохранить библиопункт заново.')
        return redirect('locations_admin:detail', pk=pk)
    response = HttpResponse(location.qr_code.read(), content_type='image/png')
    response['Content-Disposition'] = f'attachment; filename="qr_{location.slug}.png"'
    return response


# ──────────────────────────────
# Public view
# ──────────────────────────────

def point_public(request, slug):
    location = get_object_or_404(Location, slug=slug, is_active=True)
    books = location.get_current_books()

    q = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')

    if q:
        books = [b for b in books if q.lower() in b.title.lower() or q.lower() in b.author.lower()]
    if genre:
        books = [b for b in books if b.genre == genre]

    from apps.catalog.models import Genre
    genre_choices = Genre.objects.values_list('code', 'name')

    return render(request, 'locations/point_public.html', {
        'location': location,
        'books': books,
        'q': q,
        'genre_filter': genre,
        'genre_choices': genre_choices,
    })


def points_map(request):
    locations = Location.objects.filter(is_active=True)
    points = []
    for loc in locations:
        if loc.latitude and loc.longitude:
            points.append({
                'name': loc.name,
                'address': loc.address,
                'slug': loc.slug,
                'lat': loc.latitude,
                'lng': loc.longitude,
                'books': loc.books_count,
                'type': loc.get_type_display(),
            })
    return render(request, 'locations/map.html', {
        'points': points,
        'total': locations.count(),
        'mapped': len(points),
    })
