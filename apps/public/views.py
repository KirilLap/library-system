from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.catalog.models import Book


def book_list(request):
    books = Book.objects.exclude(status='LOST')
    q = request.GET.get('q', '').strip()
    genre = request.GET.get('genre', '')
    language = request.GET.get('lang', '')
    status_filter = request.GET.get('status', '')

    if q:
        books = books.filter(title__icontains=q) | Book.objects.filter(author__icontains=q)
        books = books.exclude(status='LOST')
    if genre:
        books = books.filter(genre=genre)
    if language:
        books = books.filter(language=language)
    if status_filter:
        books = books.filter(status=status_filter)

    books = books.order_by('title')

    return render(request, 'catalog/public_book_list.html', {
        'books': books,
        'q': q,
        'genre_filter': genre,
        'lang_filter': language,
        'status_filter': status_filter,
        'genre_choices': Book.GENRE_CHOICES,
        'language_choices': Book.LANGUAGE_CHOICES,
        'status_choices': [('IN_LIBRARY', 'В библиотеке'), ('IN_DELIVERY', 'На точке')],
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
