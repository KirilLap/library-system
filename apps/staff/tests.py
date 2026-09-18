"""Тесты страницы статистики и журнала действий сотрудников."""
import datetime
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Book, BookTitle
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import BookRequest, Loan, Reader
from .models import ActionLog, StaffProfile

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_admin(username='admin'):
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
    return user


def make_librarian(username='librarian'):
    """Librarian (non-admin) role — нужен хотя бы один ADMIN в системе отдельно."""
    make_admin('bootstrap-admin')
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_LIBRARIAN, is_active=True)
    return user


def make_location(name='Точка', **kwargs):
    return Location.objects.create(name=name, type='MAHALLA', address='Адрес', **kwargs)


def make_book(inventory_number, **kwargs):
    title_fields = {}
    for key in ('title', 'author', 'year', 'publisher', 'genre', 'language', 'description', 'isbn'):
        if key in kwargs:
            title_fields[key] = kwargs.pop(key)
    title_defaults = dict(title='Книга', author='Автор')
    title_defaults.update(title_fields)
    book_title = BookTitle.objects.create(**title_defaults)
    defaults = dict(status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(book_title=book_title, inventory_number=inventory_number, **defaults)


def make_reader(username):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone='+998900000000')


def deliver_book(book, location):
    batch = DeliveryBatch.objects.create(location=location)
    DeliveryItem.objects.create(batch=batch, book=book)
    Book.objects.filter(pk=book.pk).update(status='IN_DELIVERY')
    book.refresh_from_db()
    return batch


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class StatsViewTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_stats_page_loads(self):
        response = self.client.get(reverse('staff:stats'))
        self.assertEqual(response.status_code, 200)

    def test_stats_counts_loans_in_period(self):
        location = make_location()
        book = make_book('INV-900')
        deliver_book(book, location)
        reader = make_reader('reader1')
        Loan.objects.create(book=book, location=location, reader=reader)

        response = self.client.get(reverse('staff:stats'), {'days': 30})
        self.assertEqual(response.context['period_stats']['loans_issued'], 1)

    def test_invalid_days_falls_back_to_default(self):
        response = self.client.get(reverse('staff:stats'), {'days': 'garbage'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['days'], 30)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class DashboardOverdueTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_dashboard_flags_overdue_loan(self):
        from django.conf import settings
        location = make_location()
        book = make_book('INV-902')
        deliver_book(book, location)
        reader = make_reader('reader1')
        loan = Loan.objects.create(book=book, location=location, reader=reader)
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - datetime.timedelta(days=settings.LOAN_PERIOD_DAYS + 1)
        )

        response = self.client.get(reverse('staff:dashboard'))
        self.assertEqual(response.context['stats']['loans_overdue'], 1)
        self.assertContains(response, 'Просроченные займы')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class ActionLogTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client.force_login(self.admin)

    def test_log_helper_creates_entry(self):
        ActionLog.log(self.admin, 'Тестовое действие')
        entry = ActionLog.objects.get()
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(entry.action, 'Тестовое действие')

    def test_request_status_change_is_logged(self):
        reader = make_reader('reader1')
        req = BookRequest.objects.create(reader=reader, requested_title='Книга')
        self.client.post(reverse('readers_admin_extra:request_approve', args=[req.pk]))
        self.assertTrue(ActionLog.objects.filter(action__icontains=f'Заявка #{req.pk}').exists())

    def test_reader_block_is_logged(self):
        reader = make_reader('reader1')
        self.client.post(reverse('readers_admin:toggle_block', args=[reader.pk]))
        self.assertTrue(ActionLog.objects.filter(action__icontains=reader.full_name).exists())

    def test_book_status_manual_change_is_logged(self):
        book = make_book('INV-901', status='IN_LIBRARY')
        self.client.post(reverse('catalog_admin:book_update', args=[book.pk]), {
            'inventory_number': 'INV-901',
            'title': 'Книга',
            'author': 'Автор',
            'genre': 'OTHER',
            'language': 'RU',
            'status': 'LOST',
        })
        book.refresh_from_db()
        self.assertEqual(book.status, 'LOST')
        self.assertTrue(ActionLog.objects.filter(action__icontains='LOST').exists() or
                         ActionLog.objects.filter(action__icontains='Утеряна').exists())

    def test_batch_delete_is_logged(self):
        location = make_location()
        batch = DeliveryBatch.objects.create(location=location)
        self.client.post(reverse('deliveries_admin:delete', args=[batch.pk]))
        self.assertTrue(ActionLog.objects.filter(action__icontains=f'партию #{batch.pk}').exists())

    def test_location_delete_is_logged(self):
        location = make_location()
        self.client.post(reverse('locations_admin:delete', args=[location.pk]))
        self.assertTrue(ActionLog.objects.filter(action__icontains=location.name).exists())

    def test_log_page_requires_admin(self):
        librarian = make_librarian()
        self.client.force_login(librarian)
        response = self.client.get(reverse('staff:action_log'))
        self.assertNotEqual(response.status_code, 200)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LanguagePreferenceTests(TestCase):
    """Выбор языка сотрудником запоминается в профиле и применяется при следующем входе."""

    def setUp(self):
        self.user = make_admin()

    def test_switching_language_saves_it_to_profile(self):
        self.client.force_login(self.user)
        self.client.post(reverse('staff:set_language'), {'language': 'uz', 'next': '/admin-panel/'})
        self.user.staff_profile.refresh_from_db()
        self.assertEqual(self.user.staff_profile.language, 'uz')

    def test_switching_language_ignored_for_unknown_code(self):
        self.client.force_login(self.user)
        self.client.post(reverse('staff:set_language'), {'language': 'xx', 'next': '/admin-panel/'})
        self.user.staff_profile.refresh_from_db()
        self.assertEqual(self.user.staff_profile.language, '')

    def test_login_activates_saved_language(self):
        self.user.staff_profile.language = 'uz'
        self.user.staff_profile.save(update_fields=['language'])
        response = self.client.post(reverse('staff:login'), {
            'username': self.user.username, 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies['django_language'].value, 'uz')

    def test_login_without_saved_language_leaves_cookie_untouched(self):
        response = self.client.post(reverse('staff:login'), {
            'username': self.user.username, 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('django_language', response.cookies)


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
