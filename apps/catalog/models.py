from django.db import models


class Genre(models.Model):
    code = models.CharField(max_length=30, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, verbose_name='Название')

    class Meta:
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанры'
        ordering = ['name']

    def __str__(self):
        return self.name


class Language(models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, verbose_name='Название')

    class Meta:
        verbose_name = 'Язык'
        verbose_name_plural = 'Языки'
        ordering = ['name']

    def __str__(self):
        return self.name


class Book(models.Model):
    STATUS_CHOICES = [
        ('IN_LIBRARY', 'В библиотеке'),
        ('IN_DELIVERY', 'В библиопункте'),
        ('LOST', 'Утеряна'),
    ]

    cover = models.ImageField(upload_to='covers/', blank=True, null=True, verbose_name='Обложка')
    inventory_number = models.CharField(max_length=50, unique=True, verbose_name='Инв. номер')
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='Штрих-код')
    title = models.CharField(max_length=500, verbose_name='Название')
    author = models.CharField(max_length=300, verbose_name='Автор')
    year = models.IntegerField(null=True, blank=True, verbose_name='Год')
    publisher = models.CharField(max_length=300, blank=True, verbose_name='Издательство')
    genre = models.CharField(max_length=30, default='OTHER', verbose_name='Жанр')
    language = models.CharField(max_length=20, default='RU', verbose_name='Язык')
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

    def save(self, *args, **kwargs):
        # Штрих-код всегда равен инвентарному номеру
        self.barcode = self.inventory_number or None
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.inventory_number} — {self.title}'

    def get_genre_display(self):
        try:
            return Genre.objects.get(code=self.genre).name
        except Genre.DoesNotExist:
            return self.genre

    def get_language_display(self):
        try:
            return Language.objects.get(code=self.language).name
        except Language.DoesNotExist:
            return self.language

    def get_status_badge_class(self):
        return {
            'IN_LIBRARY': 'success',
            'IN_DELIVERY': 'primary',
            'LOST': 'danger',
        }.get(self.status, 'secondary')

    _PLACEHOLDER_COLORS = [
        '#4e73df', '#1cc88a', '#36b9cc', '#f6c23e',
        '#e74a3b', '#6f42c1', '#fd7e14', '#20c997',
    ]

    @property
    def cover_placeholder_color(self):
        return self._PLACEHOLDER_COLORS[self.pk % len(self._PLACEHOLDER_COLORS)]

    @property
    def cover_placeholder_letter(self):
        return (self.title[0] if self.title else '?').upper()

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
