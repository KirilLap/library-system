from django.db import models


class Book(models.Model):
    GENRE_CHOICES = [
        ('FICTION', 'Художественная'),
        ('CHILDREN', 'Детская'),
        ('EDUCATIONAL', 'Учебная'),
        ('POETRY', 'Поэзия'),
        ('NONFICTION', 'Документальная'),
        ('OTHER', 'Другое'),
    ]

    LANGUAGE_CHOICES = [
        ('RU', 'Русский'),
        ('UZ', 'Узбекский'),
        ('EN', 'Английский'),
        ('OTHER', 'Другой'),
    ]

    STATUS_CHOICES = [
        ('IN_LIBRARY', 'В библиотеке'),
        ('IN_DELIVERY', 'На точке'),
        ('LOST', 'Утеряна'),
    ]

    inventory_number = models.CharField(max_length=50, unique=True, verbose_name='Инв. номер')
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='Штрих-код')
    title = models.CharField(max_length=500, verbose_name='Название')
    author = models.CharField(max_length=300, verbose_name='Автор')
    year = models.IntegerField(null=True, blank=True, verbose_name='Год')
    publisher = models.CharField(max_length=300, blank=True, verbose_name='Издательство')
    genre = models.CharField(max_length=20, choices=GENRE_CHOICES, default='OTHER', verbose_name='Жанр')
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default='RU', verbose_name='Язык')
    description = models.TextField(blank=True, verbose_name='Описание')
    isbn = models.CharField(max_length=20, blank=True, verbose_name='ISBN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_LIBRARY', verbose_name='Статус')
    marc_data = models.JSONField(blank=True, null=True, verbose_name='MARC данные')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Книга'
        verbose_name_plural = 'Книги'
        ordering = ['inventory_number']

    def __str__(self):
        return f'{self.inventory_number} — {self.title}'

    def get_status_badge_class(self):
        return {
            'IN_LIBRARY': 'success',
            'IN_DELIVERY': 'primary',
            'LOST': 'danger',
        }.get(self.status, 'secondary')

    @property
    def current_location(self):
        try:
            from apps.deliveries.models import DeliveryItem
            item = (
                DeliveryItem.objects
                .filter(book=self, is_returned=False)
                .select_related('batch__location')
                .first()
            )
            return item.batch.location if item else None
        except Exception:
            return None
