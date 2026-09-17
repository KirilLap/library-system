from django.db import models
from django.utils import timezone


class DeliveryBatch(models.Model):
    """A delivery batch: a set of books sent to one location."""

    location = models.ForeignKey(
        'locations.Location',
        on_delete=models.PROTECT,
        related_name='batches',
        verbose_name='Библиопункт',
    )
    delivery_date = models.DateField(default=timezone.localdate, verbose_name='Дата доставки')
    note = models.TextField(blank=True, verbose_name='Примечание')
    is_returned = models.BooleanField(default=False, verbose_name='Возвращена')
    returned_date = models.DateField(null=True, blank=True, verbose_name='Дата возврата')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Партия'
        verbose_name_plural = 'Партии'
        ordering = ['-delivery_date', '-pk']

    def __str__(self):
        return f'Партия #{self.pk} → {self.location.name} ({self.delivery_date})'

    def books_count(self):
        return self.items.count()

    def mark_returned(self):
        self.is_returned = True
        self.returned_date = timezone.localdate()
        self.save()
        # Return all books that haven't been individually returned
        for item in self.items.filter(is_returned=False):
            item.mark_returned()


class DeliveryItem(models.Model):
    """A single book within a delivery batch."""

    batch = models.ForeignKey(
        DeliveryBatch,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Партия',
    )
    book = models.ForeignKey(
        'catalog.Book',
        on_delete=models.PROTECT,
        related_name='delivery_items',
        verbose_name='Книга',
    )
    is_returned = models.BooleanField(default=False, verbose_name='Возвращена')
    returned_at = models.DateTimeField(null=True, blank=True, verbose_name='Время возврата')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Книга в партии'
        verbose_name_plural = 'Книги в партии'
        unique_together = [('batch', 'book')]

    def __str__(self):
        return f'{self.book.inventory_number} в партии #{self.batch_id}'

    def mark_returned(self):
        from apps.catalog.models import Book
        self.is_returned = True
        self.returned_at = timezone.now()
        self.save()
        Book.objects.filter(pk=self.book_id).update(status='IN_LIBRARY')
