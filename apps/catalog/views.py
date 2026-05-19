import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required
from .forms import BookForm, MARCImportForm, ExcelImportForm
from .marc_utils import parse_marc_file
from .models import Book


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
        form = BookForm(request.POST, request.FILES)
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
        form = BookForm(request.POST, request.FILES, instance=book)
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


# ──────────────────────────────
# Labels / barcodes
# ──────────────────────────────

@librarian_required
def book_label(request, pk):
    book = get_object_or_404(Book, pk=pk)
    return render(request, 'catalog/book_label.html', {'books': [book]})


@librarian_required
def book_labels_batch(request):
    ids = request.GET.getlist('ids')
    if not ids:
        messages.warning(request, 'Не выбрано ни одной книги.')
        return redirect('catalog_admin:index')
    books = Book.objects.filter(pk__in=ids)
    return render(request, 'catalog/book_label.html', {'books': books})


# ──────────────────────────────
# Excel import
# ──────────────────────────────

_EXCEL_COLUMNS = [
    ('inventory_number', 'Инв. номер *'),
    ('title',            'Название *'),
    ('author',           'Автор'),
    ('year',             'Год'),
    ('publisher',        'Издательство'),
    ('isbn',             'ISBN'),
    ('genre',            'Жанр (FICTION/CHILDREN/EDUCATIONAL/POETRY/NONFICTION/OTHER)'),
    ('language',         'Язык (RU/UZ/EN/OTHER)'),
    ('description',      'Описание'),
]

_EXCEL_EXAMPLE = [
    'КН-0001', 'Война и мир', 'Лев Толстой', '1869',
    'Азбука', '978-5-389-06256-6', 'FICTION', 'RU', '',
]


@librarian_required
def excel_template_download(request):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Книги'

    header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)

    for col_idx, (_, label) in enumerate(_EXCEL_COLUMNS, start=1):
        cell = ws.cell(row=1, column=col_idx, value=label)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        ws.column_dimensions[cell.column_letter].width = max(len(label) + 4, 18)

    for col_idx, value in enumerate(_EXCEL_EXAMPLE, start=1):
        ws.cell(row=2, column=col_idx, value=value)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    response = HttpResponse(
        buf.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="books_template.xlsx"'
    return response


@librarian_required
def excel_import(request):
    if request.method == 'POST':
        form = ExcelImportForm(request.POST, request.FILES)
        if form.is_valid():
            rows, errors = _parse_excel(request.FILES['file'])
            request.session['excel_import_data'] = rows
            return render(request, 'catalog/excel_import.html', {
                'form': ExcelImportForm(),
                'preview': rows[:20],
                'total': len(rows),
                'parse_errors': errors,
                'has_data': True,
            })
    else:
        form = ExcelImportForm()
    return render(request, 'catalog/excel_import.html', {'form': form, 'has_data': False})


@librarian_required
@require_POST
def excel_confirm(request):
    rows = request.session.pop('excel_import_data', None)
    if not rows:
        messages.error(request, 'Данные для импорта не найдены. Загрузите файл снова.')
        return redirect('catalog_admin:excel_import')

    created = updated = 0
    skipped = []

    valid_genres = {k for k, _ in Book.GENRE_CHOICES}
    valid_langs  = {k for k, _ in Book.LANGUAGE_CHOICES}

    for row in rows:
        inv = (row.get('inventory_number') or '').strip()
        if not inv:
            skipped.append({'title': row.get('title') or '—', 'reason': 'Нет инвентарного номера'})
            continue
        title = (row.get('title') or '').strip()
        if not title:
            skipped.append({'title': f'инв. {inv}', 'reason': 'Нет названия'})
            continue

        year_raw = row.get('year')
        year = None
        if year_raw:
            try:
                year = int(str(year_raw).strip())
            except ValueError:
                pass

        genre = (row.get('genre') or '').strip().upper()
        if genre not in valid_genres:
            genre = 'OTHER'
        lang = (row.get('language') or '').strip().upper()
        if lang not in valid_langs:
            lang = 'RU'

        try:
            _, is_created = Book.objects.update_or_create(
                inventory_number=inv,
                defaults={
                    'title':       title,
                    'author':      (row.get('author') or ''),
                    'year':        year,
                    'publisher':   (row.get('publisher') or ''),
                    'isbn':        (row.get('isbn') or ''),
                    'genre':       genre,
                    'language':    lang,
                    'description': (row.get('description') or ''),
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1
        except Exception as e:
            skipped.append({'title': title, 'reason': str(e)})

    return render(request, 'catalog/excel_import_result.html', {
        'created': created,
        'updated': updated,
        'skipped': skipped,
    })


def _parse_excel(file_obj):
    """Return (rows_list, errors_list). rows_list items match _EXCEL_COLUMNS keys."""
    rows = []
    errors = []
    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        ws = wb.active
        col_keys = [k for k, _ in _EXCEL_COLUMNS]
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if all(cell is None or str(cell).strip() == '' for cell in row):
                continue
            record = {}
            for col_idx, key in enumerate(col_keys):
                val = row[col_idx] if col_idx < len(row) else None
                record[key] = str(val).strip() if val is not None else ''
            # Determine import status for preview
            inv = record.get('inventory_number', '').strip()
            title = record.get('title', '').strip()
            if not inv:
                record['_status'] = 'error'
                record['_status_text'] = 'Нет инв. номера'
            elif not title:
                record['_status'] = 'error'
                record['_status_text'] = 'Нет названия'
            elif Book.objects.filter(inventory_number=inv).exists():
                record['_status'] = 'update'
                record['_status_text'] = 'Обновление'
            else:
                record['_status'] = 'new'
                record['_status_text'] = 'Новая'
            rows.append(record)
        wb.close()
    except Exception as e:
        errors.append(f'Ошибка чтения файла: {e}')
    return rows, errors
