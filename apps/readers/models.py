from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class AgeGroupSettings(models.Model):
    """Границы возрастных групп для статистики (одна запись на весь сайт).
    Хранятся как начало каждой группы: «14,18,31,61» — до 14, 14–17, 18–30, 31–60, 61+."""

    boundaries = models.CharField(
        max_length=100, default='14,18,31,61', verbose_name='Границы возрастных групп',
    )

    class Meta:
        verbose_name = 'Настройки возрастных групп'
        verbose_name_plural = 'Настройки возрастных групп'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


def generate_card_id():
    """Случайный 10-значный ID читателя (не подбирается по порядку)."""
    import secrets
    while True:
        value = str(secrets.randbelow(9 * 10 ** 9) + 10 ** 9)
        if not Reader.objects.filter(card_id=value).exists() \
                and not User.objects.filter(username=value).exists():
            return value


class Reader(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='reader_profile')
    phone = models.CharField(max_length=50, blank=True, verbose_name='Телефон')
    address = models.TextField(blank=True, verbose_name='Адрес')
    affiliated_location = models.ForeignKey(
        'locations.Location', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='affiliated_readers', verbose_name='Прикреплённый библиопункт'
    )
    card_id = models.CharField(
        max_length=10, unique=True, null=True, blank=True, editable=False,
        verbose_name='ID читателя',
        help_text='Случайный 10-значный номер, создаётся автоматически.',
    )
    GENDER_MALE = 'M'
    GENDER_FEMALE = 'F'
    GENDER_CHOICES = [
        (GENDER_MALE, _('Мужской')),
        (GENDER_FEMALE, _('Женский')),
    ]

    gender = models.CharField(
        max_length=1, choices=GENDER_CHOICES, blank=True, default='', verbose_name='Пол',
        help_text='Нужен для статистики.',
    )
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name='Год рождения')
    nearest_location = models.ForeignKey(
        'locations.Location', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='nearby_readers', verbose_name='Ближайший библиопункт',
        help_text='Читатель сам отмечает, какой библиопункт ему ближе всего.',
    )
    must_change_password = models.BooleanField(
        default=False, verbose_name='Нужно сменить пароль',
        help_text='Включается, когда читателя зарегистрировал сотрудник с временным паролем.',
    )
    is_blocked = models.BooleanField(default=False, verbose_name='Заблокирован')
    notes = models.TextField(blank=True, verbose_name='Заметки библиотекаря')
    language = models.CharField(
        max_length=10, blank=True, verbose_name='Язык интерфейса',
        help_text='Запоминается при переключении языка и применяется при следующем входе.',
    )
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
    def age(self):
        if not self.birth_year:
            return None
        return timezone.now().year - self.birth_year

    @property
    def active_requests_count(self):
        return self.requests.filter(status__in=['PENDING', 'APPROVED']).count()

    @property
    def active_loans(self):
        return self.loans.filter(is_returned=False).select_related('book', 'location')


class Loan(models.Model):
    book = models.ForeignKey(
        'catalog.Book', on_delete=models.PROTECT, related_name='loans', verbose_name='Книга'
    )
    location = models.ForeignKey(
        'locations.Location', on_delete=models.PROTECT, related_name='loans', verbose_name='Библиопункт'
    )
    reader = models.ForeignKey(
        'Reader', on_delete=models.PROTECT, null=True, blank=True,
        related_name='loans', verbose_name='Читатель'
    )
    issued_by = models.ForeignKey(
        'organizations.LocationWorker', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='issued_loans', verbose_name='Выдал работник'
    )
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата выдачи')
    returned_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата возврата')
    is_lost = models.BooleanField(
        default=False, verbose_name='Книга утеряна',
        help_text='Выдача закрыта не возвратом, а утерей книги.',
    )
    is_returned = models.BooleanField(default=False, verbose_name='Возвращена')

    class Meta:
        verbose_name = 'Выдача'
        verbose_name_plural = 'Выдачи'
        ordering = ['-issued_at']

    def __str__(self):
        reader_str = str(self.reader) if self.reader else 'Аноним'
        return f'{self.book.title} → {reader_str}'

    @property
    def days_held(self):
        end = self.returned_at or timezone.now()
        return (end - self.issued_at).days

    @property
    def is_overdue(self):
        from django.conf import settings
        return not self.is_returned and self.days_held > settings.LOAN_PERIOD_DAYS


class BookRequest(models.Model):
    STATUS_CHOICES = [
        ('PENDING',    _('Новая')),
        ('APPROVED',   _('Одобрена')),
        ('PURCHASING', _('Закупается')),
        ('FULFILLED',  _('Выполнена')),
        ('REJECTED',   _('Отклонена')),
        ('CANCELLED',  _('Отменена')),
    ]

    # Финальные статусы — изменение запрещено
    FINAL_STATUSES = {'FULFILLED', 'REJECTED', 'CANCELLED'}

    # Допустимые переходы статусов
    ALLOWED_TRANSITIONS = {
        'PENDING':    ['APPROVED', 'PURCHASING', 'REJECTED'],
        'APPROVED':   ['PURCHASING', 'FULFILLED', 'REJECTED'],
        'PURCHASING': ['FULFILLED', 'REJECTED'],
    }

    reader = models.ForeignKey(Reader, on_delete=models.CASCADE, related_name='requests', verbose_name='Читатель')
    book = models.ForeignKey(
        'catalog.Book', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='requests', verbose_name='Книга из каталога'
    )
    requested_title = models.CharField(max_length=500, blank=True, verbose_name='Название (не из каталога)')
    requested_author = models.CharField(max_length=300, blank=True, verbose_name='Автор (не из каталога)')
    preferred_location = models.ForeignKey(
        'locations.Location', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='book_requests', verbose_name='Желаемый библиопункт получения'
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
            'PENDING':    'warning',
            'APPROVED':   'primary',
            'PURCHASING': 'info',
            'FULFILLED':  'success',
            'REJECTED':   'danger',
            'CANCELLED':  'secondary',
        }.get(self.status, 'secondary')

    @property
    def is_final(self):
        return self.status in self.FINAL_STATUSES

    @property
    def allowed_next_statuses(self):
        return self.ALLOWED_TRANSITIONS.get(self.status, [])


class BookQueue(models.Model):
    """Очередь на книгу, которая сейчас на руках у другого читателя."""

    book = models.ForeignKey(
        'catalog.Book', on_delete=models.CASCADE, related_name='queue_entries', verbose_name='Книга'
    )
    reader = models.ForeignKey(
        Reader, on_delete=models.CASCADE, related_name='queue_entries', verbose_name='Читатель'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Встал в очередь')

    class Meta:
        verbose_name = 'Очередь на книгу'
        verbose_name_plural = 'Очереди на книги'
        ordering = ['created_at']
        unique_together = [('book', 'reader')]

    def __str__(self):
        return f'{self.reader.full_name} → «{self.book.title}»'

    @property
    def position(self):
        """Место читателя в очереди (1 — следующий)."""
        return BookQueue.objects.filter(
            book_id=self.book_id, created_at__lt=self.created_at
        ).count() + 1
