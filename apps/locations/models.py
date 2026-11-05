from django.db import models
from django.utils.text import slugify

from config.localized import LocalizedNameMixin


def _translit(text):
    """Transliterate Cyrillic to Latin for slug generation."""
    table = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'j', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'ў': 'o', 'қ': 'q', 'ғ': 'g', 'ҳ': 'h', 'ө': 'o',
    }
    result = ''
    for ch in text.lower():
        result += table.get(ch, ch)
    return slugify(result)


class LocationType(LocalizedNameMixin, models.Model):
    """Настраиваемый тип библиопункта (Махалля, Школа, Детский сад, ...)."""

    code = models.CharField(max_length=30, unique=True, verbose_name='Код')
    name = models.CharField(max_length=100, verbose_name='Название')
    name_uz = models.CharField(max_length=100, blank=True, verbose_name='Название на узбекском')
    is_open = models.BooleanField(
        default=False,
        verbose_name='Открытый тип',
        help_text='Читатель может прийти и взять книгу сам (как в махалле). '
                   'Если не отмечено — точка закрытая: выдачу оформляет работник.',
    )

    class Meta:
        verbose_name = 'Тип библиопункта'
        verbose_name_plural = 'Типы библиопунктов'
        ordering = ['name']

    def __str__(self):
        return self.name


class MapSettings(models.Model):
    """Общая настройка публичной карты (одна запись на весь сайт)."""

    MODE_MARK = 'MARK'
    MODE_SEPARATE = 'SEPARATE'
    MODE_HIDE = 'HIDE'
    MODE_CHOICES = [
        (MODE_MARK, 'Показывать все, закрытые помечены'),
        (MODE_SEPARATE, 'На карте только открытые, закрытые отдельным списком'),
        (MODE_HIDE, 'Закрытые на публичной карте не показывать'),
    ]

    closed_points_mode = models.CharField(
        max_length=10, choices=MODE_CHOICES, default=MODE_MARK,
        verbose_name='Закрытые библиопункты на публичной карте',
    )

    class Meta:
        verbose_name = 'Настройки карты'
        verbose_name_plural = 'Настройки карты'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


def open_type_codes():
    """Коды типов, у которых читатель берёт книгу сам (самообслуживание)."""
    return set(LocationType.objects.filter(is_open=True).values_list('code', flat=True))


class Location(models.Model):
    name = models.CharField(max_length=300, verbose_name='Название')
    type = models.CharField(max_length=30, verbose_name='Тип')
    address = models.TextField(verbose_name='Адрес')
    contact_person = models.CharField(max_length=200, blank=True, verbose_name='Контактное лицо')
    contact_phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон контакта')
    latitude = models.FloatField(null=True, blank=True, verbose_name='Широта')
    longitude = models.FloatField(null=True, blank=True, verbose_name='Долгота')
    slug = models.SlugField(max_length=200, unique=True, blank=True, verbose_name='URL-slug')
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, verbose_name='QR-код')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    is_public = models.BooleanField(
        default=True,
        verbose_name='Показывать в публичном каталоге',
        help_text='Если выключено — библиопункт не появляется на карте, в фильтре каталога '
                   'и в бейджах книг (книга просто покажется «в библиопункте», без названия). '
                   'Страница по QR-коду продолжит работать напрямую.',
    )
    notes = models.TextField(blank=True, verbose_name='Заметки')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Библиопункт'
        verbose_name_plural = 'Библиопункты'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_type_display(self):
        try:
            return LocationType.objects.get(code=self.type).localized_name()
        except LocationType.DoesNotExist:
            return self.type

    @property
    def is_open(self):
        """Открытый библиопункт — читатель может прийти и взять книгу сам.
        Закрытые точки доступны только своим (ученикам/сотрудникам), выдачу
        там оформляет работник библиопункта. Определяется настраиваемым типом."""
        try:
            return LocationType.objects.get(code=self.type).is_open
        except LocationType.DoesNotExist:
            return False

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._make_unique_slug()
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new or not self.qr_code:
            self._generate_qr_code()

    def _make_unique_slug(self):
        base = _translit(self.name) or 'location'
        slug = base
        n = 1
        while Location.objects.filter(slug=slug).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def _generate_qr_code(self):
        try:
            import qrcode
            from io import BytesIO
            from django.conf import settings
            from django.core.files.base import ContentFile
            from django.core.files.storage import default_storage

            url = f'{settings.SITE_URL}/p/{self.slug}/'
            img = qrcode.make(url)
            buf = BytesIO()
            img.save(buf, format='PNG')
            buf.seek(0)

            filename = f'qr_codes/qr_{self.slug}.png'
            if default_storage.exists(filename):
                default_storage.delete(filename)
            saved = default_storage.save(filename, ContentFile(buf.read()))

            Location.objects.filter(pk=self.pk).update(qr_code=saved)
            self.qr_code = saved
        except Exception:
            pass

    def get_qr_url(self):
        from django.conf import settings
        return f'{settings.SITE_URL}/p/{self.slug}/'

    @property
    def books_count(self):
        try:
            from apps.deliveries.models import DeliveryItem
            return DeliveryItem.objects.filter(
                batch__location=self, is_returned=False
            ).count()
        except Exception:
            return 0

    @property
    def last_delivery_date(self):
        try:
            from apps.deliveries.models import DeliveryBatch
            batch = DeliveryBatch.objects.filter(
                location=self
            ).order_by('-delivery_date').first()
            return batch.delivery_date if batch else None
        except Exception:
            return None

    def get_current_books(self):
        try:
            from apps.deliveries.models import DeliveryItem
            from apps.catalog.models import Book
            ids = DeliveryItem.objects.filter(
                batch__location=self, is_returned=False
            ).values_list('book_id', flat=True)
            return Book.objects.filter(id__in=ids)
        except Exception:
            return []

    def get_delivery_history(self):
        try:
            from apps.deliveries.models import DeliveryBatch
            return DeliveryBatch.objects.filter(
                location=self
            ).order_by('-delivery_date')[:10]
        except Exception:
            return []
