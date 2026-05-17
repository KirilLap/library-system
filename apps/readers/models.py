from django.contrib.auth.models import User
from django.db import models


class Reader(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='reader_profile')
    phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон')
    address = models.TextField(blank=True, verbose_name='Адрес')
    is_blocked = models.BooleanField(default=False, verbose_name='Заблокирован')
    notes = models.TextField(blank=True, verbose_name='Заметки библиотекаря')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Читатель'
        verbose_name_plural = 'Читатели'
        ordering = ['-created_at']

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def active_requests_count(self):
        return self.requests.filter(status__in=['PENDING', 'APPROVED']).count()


class BookRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING', 'Новая'),
        ('APPROVED', 'Одобрена'),
        ('REJECTED', 'Отклонена'),
        ('FULFILLED', 'Выдана'),
        ('CANCELLED', 'Отменена'),
    ]

    reader = models.ForeignKey(Reader, on_delete=models.CASCADE, related_name='requests', verbose_name='Читатель')
    book = models.ForeignKey(
        'catalog.Book', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requests', verbose_name='Книга'
    )
    message = models.TextField(blank=True, verbose_name='Сообщение читателя')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', verbose_name='Статус')
    librarian_note = models.TextField(blank=True, verbose_name='Ответ библиотекаря')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заявка'
        verbose_name_plural = 'Заявки'
        ordering = ['-created_at']

    def __str__(self):
        book_title = self.book.title if self.book else '—'
        return f'Заявка #{self.pk}: {self.reader} → «{book_title}»'

    def get_status_badge_class(self):
        return {
            'PENDING': 'warning',
            'APPROVED': 'primary',
            'REJECTED': 'danger',
            'FULFILLED': 'success',
            'CANCELLED': 'secondary',
        }.get(self.status, 'secondary')
