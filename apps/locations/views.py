from django.contrib import messages
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
            messages.success(request, f'Точка «{location.name}» создана. QR-код сгенерирован.')
            return redirect('locations_admin:detail', pk=location.pk)
    else:
        form = LocationForm()
    return render(request, 'locations/location_form.html', {
        'form': form,
        'title': 'Добавить точку доставки',
    })


@librarian_required
def location_update(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            messages.success(request, f'Точка «{location.name}» обновлена.')
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
def location_qr_download(request, pk):
    location = get_object_or_404(Location, pk=pk)
    if not location.qr_code:
        messages.error(request, 'QR-код не найден. Попробуйте сохранить точку заново.')
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

    from apps.catalog.models import Book
    genre_choices = Book.GENRE_CHOICES

    return render(request, 'locations/point_public.html', {
        'location': location,
        'books': books,
        'q': q,
        'genre_filter': genre,
        'genre_choices': genre_choices,
    })
