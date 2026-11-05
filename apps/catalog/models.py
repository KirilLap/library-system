from django.db import models
from django.db.models import Case, IntegerField, When
from django.utils.translation import gettext_lazy as _

from config.localized import LocalizedNameMixin

# В списках жанров и языков пункт «Другое» всегда стоит последним
OTHER_LAST = Case(When(code='OTHER', then=1), default=0, output_field=IntegerField()).asc()


class Genre(LocalizedNameMixin, models.Model):
    code = models.CharField(max_length=30, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, verbose_name='Название')
    name_uz = models.CharField(max_length=100, blank=True, verbose_name='Название на узбекском')

    class Meta:
        verbose_name = 'Жанр'
        verbose_name_plural = 'Жанры'
        ordering = [OTHER_LAST, 'name']

    def __str__(self):
        return self.name


class Language(LocalizedNameMixin, models.Model):
    code = models.CharField(max_length=20, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, verbose_name='Название')
    name_uz = models.CharField(max_length=100, blank=True, verbose_name='Название на узбекском')

    class Meta:
        verbose_name = 'Язык'
        verbose_name_plural = 'Языки'
        ordering = [OTHER_LAST, 'name']

    def __str__(self):
        return self.name


_PLACEHOLDER_COLORS = [
    '#2E5C9A', '#3D6B94', '#3D8A5C', '#5B6572',
    '#B8823A', '#A5673D', '#6B5B95', '#46708C',
]


class BookTitle(models.Model):
    """Библиографическая запись — общие данные книги (название, автор и т.д.),
    не зависящие от конкретного экземпляра. Один BookTitle может иметь
    несколько экземпляров (Book) с разными инвентарными номерами."""

    cover = models.ImageField(upload_to='covers/', blank=True, null=True, verbose_name='Обложка')
    title = models.CharField(max_length=500, verbose_name='Название')
    author = models.CharField(max_length=300, verbose_name='Автор')
    year = models.IntegerField(null=True, blank=True, verbose_name='Год')
    publisher = models.CharField(max_length=300, blank=True, verbose_name='Издательство')
    genre = models.CharField(max_length=30, default='OTHER', verbose_name='Жанр')
    language = models.CharField(max_length=20, default='RU', verbose_name='Язык')
    description = models.TextField(blank=True, verbose_name='Описание')
    isbn = models.CharField(max_length=20, blank=True, verbose_name='ISBN')
    marc_data = models.JSONField(blank=True, null=True, verbose_name='MARC данные')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Книга (название)'
        verbose_name_plural = 'Книги (названия)'
        ordering = ['title']

    def __str__(self):
        return self.title

    def get_genre_display(self):
        try:
            return Genre.objects.get(code=self.genre).localized_name()
        except Genre.DoesNotExist:
            return self.genre

    def get_language_display(self):
        try:
            return Language.objects.get(code=self.language).localized_name()
        except Language.DoesNotExist:
            return self.language

    @property
    def cover_placeholder_color(self):
        return _PLACEHOLDER_COLORS[self.pk % len(_PLACEHOLDER_COLORS)]

    @property
    def cover_placeholder_letter(self):
        return (self.title[0] if self.title else '?').upper()

    @property
    def copies_count(self):
        return self.copies.count()


class Book(models.Model):
    """Экземпляр книги — конкретная физическая копия с инвентарным номером.
    Библиографические данные (название, автор и т.п.) хранятся в BookTitle
    и доступны здесь через свойства-проксі, чтобы не переписывать весь код,
    ссылающийся на book.title / book.author и т.д."""

    STATUS_CHOICES = [
        ('IN_LIBRARY', _('В библиотеке')),
        ('IN_DELIVERY', _('В библиопункте')),
        ('LOST', _('Утеряна')),
    ]

    book_title = models.ForeignKey(
        BookTitle, on_delete=models.CASCADE, related_name='copies', verbose_name='Название'
    )
    inventory_number = models.CharField(max_length=50, unique=True, verbose_name='Инв. номер')
    barcode = models.CharField(max_length=50, unique=True, blank=True, null=True, verbose_name='Штрих-код')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_LIBRARY', verbose_name='Статус')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Экземпляр книги'
        verbose_name_plural = 'Экземпляры книг'
        ordering = ['inventory_number']

    def save(self, *args, **kwargs):
        # Штрих-код всегда равен инвентарному номеру
        self.barcode = self.inventory_number or None
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.inventory_number} — {self.title}'

    # ── проксі к библиографической записи ──────────────────────────
    @property
    def title(self):
        return self.book_title.title

    @property
    def author(self):
        return self.book_title.author

    @property
    def year(self):
        return self.book_title.year

    @property
    def publisher(self):
        return self.book_title.publisher

    @property
    def genre(self):
        return self.book_title.genre

    @property
    def language(self):
        return self.book_title.language

    @property
    def description(self):
        return self.book_title.description

    @property
    def isbn(self):
        return self.book_title.isbn

    @property
    def cover(self):
        return self.book_title.cover

    @property
    def marc_data(self):
        return self.book_title.marc_data

    def get_genre_display(self):
        return self.book_title.get_genre_display()

    def get_language_display(self):
        return self.book_title.get_language_display()

    @property
    def cover_placeholder_color(self):
        return self.book_title.cover_placeholder_color

    @property
    def cover_placeholder_letter(self):
        return self.book_title.cover_placeholder_letter

    # ── свойства экземпляра ─────────────────────────────────────────
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
