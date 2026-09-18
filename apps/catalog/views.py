import io
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, ProtectedError, Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from apps.staff.decorators import librarian_required, admin_required
from .forms import BookTitleForm, BookCopyForm, NewBookForm, MARCImportForm, ExcelImportForm, GenreForm, LanguageForm
from .marc_utils import parse_marc_file
from .models import Book, BookTitle, Genre, Language


def _delete_book_copy(book):
    """Удаляет экземпляр книги; если это была последняя копия — удаляет и
    саму библиографическую запись. Поднимает ProtectedError, если есть история выдач."""
    book_title = book.book_title
    book.delete()
    if not book_title.copies.exists():
        book_title.delete()


@librarian_required
def book_list(request):
    qs = BookTitle.objects.annotate(num_copies=Count('copies', distinct=True))

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(copies__inventory_number__icontains=q)
        ).distinct()

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(copies__status=status).distinct()

    genre = request.GET.get('genre', '')
    if genre:
        qs = qs.filter(genre=genre)

    language = request.GET.get('language', '')
    if language:
        qs = qs.filter(language=language)

    qs = qs.order_by('title')
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'catalog/book_list.html', {
        'page_obj': page_obj,
        'q': q,
        'status_filter': status,
        'genre_filter': genre,
        'language_filter': language,
        'status_choices': Book.STATUS_CHOICES,
        'genre_choices': Genre.objects.values_list('code', 'name'),
        'language_choices': Language.objects.values_list('code', 'name'),
        'total': BookTitle.objects.count(),
        'total_copies': Book.objects.count(),
    })


@librarian_required
def book_title_detail(request, pk):
    book_title = get_object_or_404(BookTitle, pk=pk)

    if request.method == 'POST':
        form = BookTitleForm(request.POST, request.FILES, instance=book_title)
        if form.is_valid():
            form.save()
            if hasattr(form, 'duplicate_warning'):
                messages.warning(request, form.duplicate_warning)
            messages.success(request, f'Книга «{book_title.title}» обновлена.')
            return redirect('catalog_admin:book_title_detail', pk=book_title.pk)
    else:
        form = BookTitleForm(instance=book_title)

    copies = book_title.copies.all().order_by('inventory_number')
    return render(request, 'catalog/book_title_detail.html', {
        'book_title': book_title,
        'form': form,
        'copies': copies,
    })


@librarian_required
def book_create(request):
    if request.method == 'POST':
        form = NewBookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
            if hasattr(form, 'duplicate_title'):
                dupe = form.duplicate_title
                messages.warning(
                    request,
                    f'Книга добавлена, но похожая запись «{dupe.title}» ({dupe.author}) уже есть в каталоге '
                    f'({dupe.copies_count} экз.). Если это та же книга — удалите новую и добавьте '
                    f'экземпляр к существующей записи.'
                )
            messages.success(request, f'Книга «{book.title}» добавлена.')
            return redirect('catalog_admin:book_update', pk=book.pk)
    else:
        form = NewBookForm()
    return render(request, 'catalog/book_form.html', {
        'form': form,
        'title': 'Добавить книгу',
    })


@librarian_required
def book_copy_create(request, title_pk):
    book_title = get_object_or_404(BookTitle, pk=title_pk)
    if request.method == 'POST':
        form = BookCopyForm(request.POST)
        if form.is_valid():
            copy = form.save(commit=False)
            copy.book_title = book_title
            copy.save()
            messages.success(request, f'Экземпляр «{copy.inventory_number}» добавлен к «{book_title.title}».')
            return redirect('catalog_admin:book_title_detail', pk=book_title.pk)
    else:
        form = BookCopyForm()
    return render(request, 'catalog/book_copy_form.html', {
        'form': form,
        'book_title': book_title,
    })


@librarian_required
def book_update(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        old_status = book.status
        old_status_display = book.get_status_display()
        title_form = BookTitleForm(request.POST, request.FILES, instance=book.book_title)
        copy_form = BookCopyForm(request.POST, instance=book)
        if title_form.is_valid() and copy_form.is_valid():
            title_form.save()
            copy_form.save()
            if hasattr(title_form, 'duplicate_warning'):
                messages.warning(request, title_form.duplicate_warning)
            messages.success(request, f'Книга «{book.title}» обновлена.')
            if book.status != old_status:
                from apps.staff.models import ActionLog
                ActionLog.log(
                    request.user,
                    f'Книга «{book.title}» (инв. {book.inventory_number}): статус '
                    f'«{old_status_display}» → «{book.get_status_display()}»',
                )
            return redirect('catalog_admin:book_title_detail', pk=book.book_title_id)
    else:
        title_form = BookTitleForm(instance=book.book_title)
        copy_form = BookCopyForm(instance=book)
    return render(request, 'catalog/book_form.html', {
        'title_form': title_form,
        'copy_form': copy_form,
        'book': book,
        'title': f'Редактировать: {book.title}',
        'current_location': book.current_location,
        'sibling_copies_count': book.book_title.copies.exclude(pk=book.pk).count(),
    })


@librarian_required
def book_delete(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        title = book.title
        inv = book.inventory_number
        book_title_id = book.book_title_id
        try:
            _delete_book_copy(book)
        except ProtectedError:
            messages.error(
                request,
                f'Нельзя удалить книгу «{title}»: есть история выдач читателям.'
            )
            return redirect('catalog_admin:book_update', pk=pk)
        messages.success(request, f'Экземпляр «{title}» (инв. {inv}) удалён.')
        from apps.staff.models import ActionLog
        ActionLog.log(request.user, f'Удалил экземпляр книги «{title}» (инв. {inv})')
        if BookTitle.objects.filter(pk=book_title_id).exists():
            return redirect('catalog_admin:book_title_detail', pk=book_title_id)
        return redirect('catalog_admin:index')
    return render(request, 'catalog/book_confirm_delete.html', {'book': book})


@librarian_required
def book_bulk_delete(request):
    """Массовое удаление книг (названий) вместе со всеми их экземплярами."""
    ids = request.POST.getlist('ids') if request.method == 'POST' else request.GET.getlist('ids')
    titles = BookTitle.objects.filter(pk__in=ids).order_by('title')

    if not titles.exists():
        messages.warning(request, 'Не выбрано ни одной книги.')
        return redirect('catalog_admin:index')

    if request.method == 'POST':
        deleted_titles = []
        skipped = []
        for book_title in list(titles):
            name = book_title.title
            copies = list(book_title.copies.all())
            protected = []
            for copy in copies:
                try:
                    copy.delete()
                except ProtectedError:
                    protected.append(copy.inventory_number)
            if protected:
                skipped.append(f'«{name}» (экз. {", ".join(protected)} — есть история выдач)')
            else:
                book_title.delete()
                deleted_titles.append(name)

        if deleted_titles:
            messages.success(request, f'Удалено книг: {len(deleted_titles)}.')
            from apps.staff.models import ActionLog
            names = ', '.join(deleted_titles[:5]) + ('…' if len(deleted_titles) > 5 else '')
            ActionLog.log(request.user, f'Массово удалил книг: {len(deleted_titles)} ({names})')
        if skipped:
            messages.error(
                request,
                'Удалено не полностью (есть история выдач у части экземпляров): ' + '; '.join(skipped)
            )
        return redirect('catalog_admin:index')

    return render(request, 'catalog/book_bulk_confirm_delete.html', {'titles': titles})


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


def _find_or_create_book_title(title, author, defaults):
    book_title = BookTitle.objects.filter(title__iexact=title, author__iexact=author).first()
    if book_title:
        return book_title, False
    return BookTitle.objects.create(title=title, author=author, **defaults), True


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
        title = data.get('title', '').strip()
        if not title:
            skipped.append({'title': f'инв. {inv}', 'reason': 'Нет названия'})
            continue
        author = data.get('author', '')
        try:
            existing = Book.objects.filter(inventory_number=inv).select_related('book_title').first()
            if existing:
                bt = existing.book_title
                bt.title = title
                bt.author = author
                bt.isbn = data.get('isbn', '')
                bt.publisher = data.get('publisher', '')
                bt.year = data.get('year')
                bt.genre = data.get('genre', 'OTHER')
                bt.marc_data = data.get('marc_data')
                bt.save()
                updated += 1
            else:
                bt, _ = _find_or_create_book_title(title, author, {
                    'isbn': data.get('isbn', ''),
                    'publisher': data.get('publisher', ''),
                    'year': data.get('year'),
                    'genre': data.get('genre', 'OTHER'),
                    'marc_data': data.get('marc_data'),
                })
                Book.objects.create(book_title=bt, inventory_number=inv)
                created += 1
        except Exception as e:
            skipped.append({'title': data.get('title', inv), 'reason': str(e)})

    return render(request, 'catalog/marc_import_result.html', {
        'created': created,
        'updated': updated,
        'skipped': skipped,
    })


# ──────────────────────────────
# Labels / barcodes (по экземплярам)
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


@librarian_required
def book_title_labels_batch(request):
    """Печать этикеток для всех экземпляров выбранных названий (из каталога, сгруппированного по книгам)."""
    title_ids = request.GET.getlist('ids')
    if not title_ids:
        messages.warning(request, 'Не выбрано ни одной книги.')
        return redirect('catalog_admin:index')
    books = Book.objects.filter(book_title_id__in=title_ids).order_by('book_title__title', 'inventory_number')
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

    valid_genres = set(Genre.objects.values_list('code', flat=True))
    valid_langs  = set(Language.objects.values_list('code', flat=True))
    default_genre = 'OTHER' if 'OTHER' in valid_genres else (next(iter(valid_genres), ''))
    default_lang  = 'RU'    if 'RU'    in valid_langs  else (next(iter(valid_langs),  ''))
    duplicates = []

    for row in rows:
        inv = (row.get('inventory_number') or '').strip()
        if not inv:
            skipped.append({'title': row.get('title') or '—', 'reason': 'Нет инвентарного номера'})
            continue
        title = (row.get('title') or '').strip()
        if not title:
            skipped.append({'title': f'инв. {inv}', 'reason': 'Нет названия'})
            continue

        author = (row.get('author') or '').strip()

        # Предупреждение: то же название+автор уже есть под другим инв. номером
        dupe_qs = BookTitle.objects.filter(
            title__iexact=title, author__iexact=author
        )
        if dupe_qs.exists() and not Book.objects.filter(inventory_number=inv).exists():
            dupe = dupe_qs.first()
            duplicates.append({
                'title': title,
                'inv': inv,
                'dupe_inv': ', '.join(dupe.copies.values_list('inventory_number', flat=True)) or '—',
            })

        year_raw = row.get('year')
        year = None
        if year_raw:
            try:
                year = int(str(year_raw).strip())
            except ValueError:
                pass

        genre = (row.get('genre') or '').strip().upper()
        if genre not in valid_genres:
            genre = default_genre
        lang = (row.get('language') or '').strip().upper()
        if lang not in valid_langs:
            lang = default_lang

        try:
            existing = Book.objects.filter(inventory_number=inv).select_related('book_title').first()
            if existing:
                bt = existing.book_title
                bt.title = title
                bt.author = author
                bt.year = year
                bt.publisher = (row.get('publisher') or '')
                bt.isbn = (row.get('isbn') or '')
                bt.genre = genre
                bt.language = lang
                bt.description = (row.get('description') or '')
                bt.save()
                updated += 1
            else:
                bt, _ = _find_or_create_book_title(title, author, {
                    'year': year,
                    'publisher': (row.get('publisher') or ''),
                    'isbn': (row.get('isbn') or ''),
                    'genre': genre,
                    'language': lang,
                    'description': (row.get('description') or ''),
                })
                Book.objects.create(book_title=bt, inventory_number=inv)
                created += 1
        except Exception as e:
            skipped.append({'title': title, 'reason': str(e)})

    return render(request, 'catalog/excel_import_result.html', {
        'created': created,
        'updated': updated,
        'skipped': skipped,
        'duplicates': duplicates,
    })


# ──────────────────────────────
# Genre management
# ──────────────────────────────

@librarian_required
def genre_list(request):
    form = GenreForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['code']
        if Genre.objects.filter(code=code).exists():
            messages.error(request, f'Жанр с кодом «{code}» уже существует.')
        else:
            genre = form.save()
            messages.success(request, f'Жанр «{genre.name}» добавлен.')
            return redirect('catalog_admin:genre_list')
    genres = Genre.objects.all()
    return render(request, 'catalog/genre_list.html', {'genres': genres, 'form': form})


@librarian_required
@require_POST
def genre_delete(request, pk):
    genre = get_object_or_404(Genre, pk=pk)
    if BookTitle.objects.filter(genre=genre.code).exists():
        messages.error(request, f'Нельзя удалить: жанр «{genre.name}» используется в книгах.')
    else:
        genre.delete()
        messages.success(request, f'Жанр «{genre.name}» удалён.')
    return redirect('catalog_admin:genre_list')


# ──────────────────────────────
# Language management
# ──────────────────────────────

@librarian_required
def language_list(request):
    form = LanguageForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        code = form.cleaned_data['code']
        if Language.objects.filter(code=code).exists():
            messages.error(request, f'Язык с кодом «{code}» уже существует.')
        else:
            lang = form.save()
            messages.success(request, f'Язык «{lang.name}» добавлен.')
            return redirect('catalog_admin:language_list')
    languages = Language.objects.all()
    return render(request, 'catalog/language_list.html', {'languages': languages, 'form': form})


@librarian_required
@require_POST
def language_delete(request, pk):
    lang = get_object_or_404(Language, pk=pk)
    if BookTitle.objects.filter(language=lang.code).exists():
        messages.error(request, f'Нельзя удалить: язык «{lang.name}» используется в книгах.')
    else:
        lang.delete()
        messages.success(request, f'Язык «{lang.name}» удалён.')
    return redirect('catalog_admin:language_list')


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
            author = record.get('author', '').strip()
            if not inv:
                record['row_status'] = 'error'
                record['row_status_text'] = 'Нет инв. номера'
            elif not title:
                record['row_status'] = 'error'
                record['row_status_text'] = 'Нет названия'
            elif Book.objects.filter(inventory_number=inv).exists():
                record['row_status'] = 'update'
                record['row_status_text'] = 'Обновление'
            elif title and author and BookTitle.objects.filter(
                title__iexact=title, author__iexact=author
            ).exists():
                record['row_status'] = 'duplicate'
                record['row_status_text'] = 'Экземпляр существующей книги'
            else:
                record['row_status'] = 'new'
                record['row_status_text'] = 'Новая'
            rows.append(record)
        wb.close()
    except Exception as e:
        errors.append(f'Ошибка чтения файла: {e}')
    return rows, errors
