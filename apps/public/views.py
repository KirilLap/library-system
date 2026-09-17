from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from django.contrib.auth.decorators import login_required

from apps.catalog.models import Book, Genre, Language


def book_list(request):
    from django.db.models import OuterRef, Subquery
    from apps.deliveries.models import DeliveryItem
    from apps.locations.models import Location

    current_item = DeliveryItem.objects.filter(
        book=OuterRef('pk'), is_returned=False
    ).order_by('-added_at')

    books = Book.objects.exclude(status='LOST').annotate(
        current_location_id=Subquery(current_item.values('batch__location_id')[:1]),
        current_location_name=Subquery(current_item.values('batch__location__name')[:1]),
        current_location_type=Subquery(current_item.values('batch__location__type')[:1]),
    )

    q = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')
    language = request.GET.get('lang', '')
    status_filter = request.GET.get('status', '')
    location_filter = request.GET.get('location', '')
    sort = request.GET.get('sort', '')

    if q:
        from django.db.models import Q
        books = books.filter(Q(title__icontains=q) | Q(author__icontains=q))
    if genre:
        books = books.filter(genre=genre)
    if language:
        books = books.filter(language=language)
    if status_filter:
        books = books.filter(status=status_filter)
    if location_filter:
        books = books.filter(current_location_id=location_filter)

    if sort == 'location':
        books = books.order_by('current_location_name', 'title')
    else:
        books = books.order_by('title')

    return render(request, 'catalog/public_book_list.html', {
        'books': books,
        'q': q,
        'genre_filter': genre,
        'lang_filter': language,
        'status_filter': status_filter,
        'location_filter': location_filter,
        'sort': sort,
        'genre_choices': Genre.objects.all(),
        'language_choices': Language.objects.all(),
        'status_choices': [('IN_LIBRARY', 'В библиотеке'), ('IN_DELIVERY', 'На точке')],
        'location_choices': Location.objects.filter(is_active=True),
    })


def book_detail(request, pk):
    book = get_object_or_404(Book.objects.exclude(status='LOST'), pk=pk)

    reader = None
    existing_request = None
    if request.user.is_authenticated:
        try:
            reader = request.user.reader_profile
            from apps.readers.models import BookRequest
            existing_request = BookRequest.objects.filter(
                reader=reader, book=book, status__in=['PENDING', 'APPROVED']
            ).first()
        except Exception:
            pass

    from apps.readers.forms import BookRequestForm
    form = BookRequestForm()

    return render(request, 'catalog/public_book_detail.html', {
        'book': book,
        'location': book.current_location,
        'reader': reader,
        'existing_request': existing_request,
        'form': form,
    })


@require_POST
def book_request(request, pk):
    book = get_object_or_404(Book.objects.exclude(status='LOST'), pk=pk)

    if not request.user.is_authenticated:
        return redirect(f'/login/?next=/catalog/{pk}/')

    try:
        reader = request.user.reader_profile
    except Exception:
        messages.error(request, 'Профиль читателя не найден.')
        return redirect('catalog:detail', pk=pk)

    if reader.is_blocked:
        messages.error(request, 'Ваш аккаунт заблокирован. Обратитесь в библиотеку.')
        return redirect('catalog:detail', pk=pk)

    if not reader.phone:
        messages.warning(request, 'Укажите номер телефона перед тем, как подавать заявки.')
        return redirect('main:edit_profile')

    from apps.readers.models import BookRequest
    from apps.readers.forms import BookRequestForm

    # Prevent duplicate active requests
    if BookRequest.objects.filter(reader=reader, book=book, status__in=['PENDING', 'APPROVED']).exists():
        messages.warning(request, 'У вас уже есть активная заявка на эту книгу.')
        return redirect('catalog:detail', pk=pk)

    form = BookRequestForm(request.POST)
    if form.is_valid():
        req = form.save(commit=False)
        req.reader = reader
        req.book = book
        req.save()
        messages.success(request, f'Заявка на «{book.title}» отправлена! Мы свяжемся с вами.')
    return redirect('catalog:detail', pk=pk)


@login_required(login_url='/login/')
def free_book_request(request):
    """Заявка на книгу, которой нет в каталоге."""
    try:
        reader = request.user.reader_profile
    except Exception:
        messages.error(request, 'Профиль читателя не найден.')
        return redirect('catalog:index')

    if reader.is_blocked:
        messages.error(request, 'Ваш аккаунт заблокирован. Обратитесь в библиотеку.')
        return redirect('catalog:index')

    if not reader.phone:
        messages.warning(request, 'Укажите номер телефона перед тем, как подавать заявки.')
        return redirect('main:edit_profile')

    from apps.readers.forms import FreeBookRequestForm
    from apps.readers.models import BookRequest

    if request.method == 'POST':
        form = FreeBookRequestForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.reader = reader
            req.save()
            messages.success(request, f'Заявка на книгу «{req.requested_title}» отправлена! Библиотекарь рассмотрит её.')
            return redirect('main:my')
    else:
        form = FreeBookRequestForm()

    return render(request, 'catalog/free_book_request.html', {'form': form})
