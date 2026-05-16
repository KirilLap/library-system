from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST
from django.utils import timezone

from .forms import DeliveryBatchForm, AddBookForm
from .models import DeliveryBatch, DeliveryItem

LOGIN_URL = '/django-admin/login/'


def librarian_required(func):
    return login_required(func, login_url=LOGIN_URL)


# ──────────────────────────────
# Batch list
# ──────────────────────────────

@librarian_required
def batch_list(request):
    batches = DeliveryBatch.objects.select_related('location')
    show_returned = request.GET.get('returned')
    if not show_returned:
        batches = batches.filter(is_returned=False)
    return render(request, 'deliveries/batch_list.html', {
        'batches': batches,
        'show_returned': show_returned,
    })


# ──────────────────────────────
# Create batch
# ──────────────────────────────

@librarian_required
def batch_create(request):
    if request.method == 'POST':
        form = DeliveryBatchForm(request.POST)
        if form.is_valid():
            batch = form.save()
            messages.success(request, f'Партия #{batch.pk} создана. Добавьте книги.')
            return redirect('deliveries_admin:detail', pk=batch.pk)
    else:
        form = DeliveryBatchForm()
    return render(request, 'deliveries/batch_form.html', {
        'form': form,
        'title': 'Новая партия',
    })


# ──────────────────────────────
# Batch detail + add/remove books
# ──────────────────────────────

@librarian_required
def batch_detail(request, pk):
    batch = get_object_or_404(DeliveryBatch.objects.select_related('location'), pk=pk)
    items = batch.items.select_related('book').order_by('book__inventory_number')
    add_form = AddBookForm()

    if request.method == 'POST' and 'inventory_number' in request.POST:
        add_form = AddBookForm(request.POST)
        if add_form.is_valid():
            inv = add_form.cleaned_data['inventory_number'].strip()
            _add_book_to_batch(request, batch, inv)
            return redirect('deliveries_admin:detail', pk=pk)

    return render(request, 'deliveries/batch_detail.html', {
        'batch': batch,
        'items': items,
        'add_form': add_form,
    })


def _add_book_to_batch(request, batch, inventory_number):
    from apps.catalog.models import Book

    if batch.is_returned:
        messages.error(request, 'Партия уже возвращена — нельзя добавлять книги.')
        return

    try:
        book = Book.objects.get(inventory_number=inventory_number)
    except Book.DoesNotExist:
        messages.error(request, f'Книга с инв. номером «{inventory_number}» не найдена.')
        return

    if book.status == 'LOST':
        messages.error(request, f'Книга «{book.title}» помечена как утерянная.')
        return

    # Check if already on another active delivery
    active_item = DeliveryItem.objects.filter(book=book, is_returned=False).exclude(batch=batch).first()
    if active_item:
        messages.error(
            request,
            f'Книга «{book.title}» уже находится на точке «{active_item.batch.location.name}» '
            f'(партия #{active_item.batch_id}).'
        )
        return

    _, created = DeliveryItem.objects.get_or_create(batch=batch, book=book)
    if created:
        Book.objects.filter(pk=book.pk).update(status='IN_DELIVERY')
        messages.success(request, f'✓ {book.inventory_number} — «{book.title}» добавлена.')
    else:
        messages.warning(request, f'Книга «{book.title}» уже в этой партии.')


# ──────────────────────────────
# Remove single book from batch
# ──────────────────────────────

@librarian_required
@require_POST
def batch_remove_item(request, pk, item_pk):
    batch = get_object_or_404(DeliveryBatch, pk=pk)
    item = get_object_or_404(DeliveryItem, pk=item_pk, batch=batch)

    if batch.is_returned:
        messages.error(request, 'Партия уже возвращена.')
        return redirect('deliveries_admin:detail', pk=pk)

    from apps.catalog.models import Book
    book = item.book
    item.delete()
    Book.objects.filter(pk=book.pk).update(status='IN_LIBRARY')
    messages.success(request, f'Книга «{book.title}» удалена из партии.')
    return redirect('deliveries_admin:detail', pk=pk)


# ──────────────────────────────
# Mark batch returned
# ──────────────────────────────

@librarian_required
@require_POST
def batch_return(request, pk):
    batch = get_object_or_404(DeliveryBatch, pk=pk)
    if batch.is_returned:
        messages.warning(request, 'Партия уже отмечена как возвращённая.')
    else:
        batch.mark_returned()
        messages.success(
            request,
            f'Партия #{batch.pk} отмечена как возвращённая. Все книги переведены в «В библиотеке».'
        )
    return redirect('deliveries_admin:detail', pk=pk)


# ──────────────────────────────
# PDF act download
# ──────────────────────────────

@librarian_required
def batch_pdf(request, pk):
    batch = get_object_or_404(DeliveryBatch.objects.select_related('location'), pk=pk)
    try:
        from .pdf_utils import generate_batch_pdf
        pdf_bytes = generate_batch_pdf(batch)
    except Exception as e:
        messages.error(request, f'Ошибка генерации PDF: {e}')
        return redirect('deliveries_admin:detail', pk=pk)

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    filename = f'act_batch_{batch.pk}_{batch.delivery_date}.pdf'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
