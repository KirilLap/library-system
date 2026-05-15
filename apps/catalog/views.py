from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from .forms import BookForm, MARCImportForm
from .marc_utils import parse_marc_file
from .models import Book

LOGIN_URL = '/django-admin/login/'


def librarian_required(func):
    return login_required(func, login_url=LOGIN_URL)


@librarian_required
def book_list(request):
    qs = Book.objects.all()

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(inventory_number__icontains=q) |
            Q(barcode__icontains=q)
        )

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    genre = request.GET.get('genre', '')
    if genre:
        qs = qs.filter(genre=genre)

    language = request.GET.get('language', '')
    if language:
        qs = qs.filter(language=language)

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'catalog/book_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status,
        'genre_filter': genre,
        'language_filter': language,
        'status_choices': Book.STATUS_CHOICES,
        'genre_choices': Book.GENRE_CHOICES,
        'language_choices': Book.LANGUAGE_CHOICES,
        'total': qs.count(),
    })


@librarian_required
def book_create(request):
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            book = form.save()
            messages.success(request, f'Книга «{book.title}» добавлена.')
            return redirect('catalog_admin:index')
    else:
        form = BookForm()
    return render(request, 'catalog/book_form.html', {
        'form': form,
        'title': 'Добавить книгу',
    })


@librarian_required
def book_update(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, f'Книга «{book.title}» обновлена.')
            return redirect('catalog_admin:index')
    else:
        form = BookForm(instance=book)
    return render(request, 'catalog/book_form.html', {
        'form': form,
        'book': book,
        'title': f'Редактировать: {book.title}',
        'current_location': book.current_location,
    })


@librarian_required
def book_delete(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        title = book.title
        book.delete()
        messages.success(request, f'Книга «{title}» удалена.')
        return redirect('catalog_admin:index')
    return render(request, 'catalog/book_confirm_delete.html', {'book': book})


@librarian_required
def marc_import(request):
    if request.method == 'POST':
        form = MARCImportForm(request.POST, request.FILES)
        if form.is_valid():
            file_bytes = request.FILES['file'].read()
            records, parse_errors = parse_marc_file(file_bytes)
            request.session['marc_import_data'] = records
            return render(request, 'catalog/marc_import.html', {
                'form': MARCImportForm(),
                'preview': records[:5],
                'total': len(records),
                'parse_errors': parse_errors[:10],
                'has_data': True,
            })
    else:
        form = MARCImportForm()
    return render(request, 'catalog/marc_import.html', {'form': form, 'has_data': False})


@librarian_required
@require_POST
def marc_confirm(request):
    records = request.session.pop('marc_import_data', None)
    if not records:
        messages.error(request, 'Данные для импорта не найдены. Загрузите файл снова.')
        return redirect('catalog_admin:marc_import')

    created = updated = 0
    skipped = []

    for data in records:
        inv = data.get('inventory_number', '').strip()
        if not inv:
            skipped.append({'title': data.get('title') or '—', 'reason': 'Нет инвентарного номера'})
            continue
        if not data.get('title', '').strip():
            skipped.append({'title': f'инв. {inv}', 'reason': 'Нет названия'})
            continue
        try:
            _, is_created = Book.objects.update_or_create(
                inventory_number=inv,
                defaults={
                    'title': data['title'].strip(),
                    'author': data.get('author', ''),
                    'isbn': data.get('isbn', ''),
                    'publisher': data.get('publisher', ''),
                    'year': data.get('year'),
                    'genre': data.get('genre', 'OTHER'),
                    'marc_data': data.get('marc_data'),
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            skipped.append({'title': data.get('title', inv), 'reason': str(e)})

    return render(request, 'catalog/marc_import_result.html', {
        'created': created,
        'updated': updated,
        'skipped': skipped,
    })
