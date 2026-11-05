from django.contrib import messages
from django.db.models import ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from apps.staff.decorators import admin_required, librarian_required
from .forms import LocationForm, LocationTypeForm, MapSettingsForm
from .models import Location, LocationType, MapSettings, open_type_codes


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
# Admin: location types (только администратор)
# ──────────────────────────────

@admin_required
def location_type_list(request):
    form = LocationTypeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['code']
        if LocationType.objects.filter(code=code).exists():
            messages.error(request, f'Тип с кодом «{code}» уже существует.')
        else:
            lt = form.save()
            messages.success(request, f'Тип «{lt.name}» добавлен.')
            return redirect('locations_admin:type_list')
    types = LocationType.objects.all()
    return render(request, 'locations/type_list.html', {'types': types, 'form': form})


@admin_required
def location_type_update(request, pk):
    lt = get_object_or_404(LocationType, pk=pk)
    if request.method == 'POST':
        form = LocationTypeForm(request.POST, instance=lt)
        if form.is_valid():
            code = form.cleaned_data['code']
            if LocationType.objects.filter(code=code).exclude(pk=lt.pk).exists():
                messages.error(request, f'Тип с кодом «{code}» уже существует.')
            else:
                form.save()
                messages.success(request, f'Тип «{lt.name}» обновлён.')
                return redirect('locations_admin:type_list')
    else:
        form = LocationTypeForm(instance=lt)
    return render(request, 'locations/type_form.html', {'form': form, 'location_type': lt})


@admin_required
def location_type_delete(request, pk):
    lt = get_object_or_404(LocationType, pk=pk)
    if request.method == 'POST':
        if Location.objects.filter(type=lt.code).exists():
            messages.error(request, f'Нельзя удалить: тип «{lt.name}» используется в библиопунктах.')
        else:
            name = lt.name
            lt.delete()
            messages.success(request, f'Тип «{name}» удалён.')
        return redirect('locations_admin:type_list')
    return redirect('locations_admin:type_list')


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
    genre_choices = [(g.code, g.localized_name()) for g in Genre.objects.all()]

    return render(request, 'locations/point_public.html', {
        'location': location,
        'books': books,
        'q': q,
        'genre_filter': genre,
        'genre_choices': genre_choices,
    })


def points_map(request):
    mode = MapSettings.get_solo().closed_points_mode
    open_codes = open_type_codes()
    locations = Location.objects.filter(is_active=True, is_public=True)

    points = []          # маркеры на карте
    closed_list = []     # закрытые, вынесенные в отдельный список (режим SEPARATE)
    total = 0
    for loc in locations:
        closed = loc.type not in open_codes
        if closed and mode == MapSettings.MODE_HIDE:
            continue
        total += 1
        entry = {
            'name': loc.name,
            'address': loc.address,
            'slug': loc.slug,
            'books': loc.books_count,
            'type': loc.get_type_display(),
            'closed': closed,
        }
        if closed and mode == MapSettings.MODE_SEPARATE:
            closed_list.append(entry)
            total -= 1
            continue
        if loc.latitude and loc.longitude:
            entry['lat'] = loc.latitude
            entry['lng'] = loc.longitude
            points.append(entry)
    return render(request, 'locations/map.html', {
        'points': points,
        'closed_points': closed_list,
        'mode': mode,
        'has_closed': any(p['closed'] for p in points),
        'total': total,
        'mapped': len(points),
    })


@admin_required
def map_settings(request):
    settings_obj = MapSettings.get_solo()
    form = MapSettingsForm(request.POST or None, instance=settings_obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Настройки карты сохранены.')
        return redirect('locations_admin:map_settings')
    return render(request, 'locations/map_settings.html', {'form': form})
