"""Тесты подачи заявки из публичного каталога."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Book, BookTitle
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import BookQueue, BookRequest, Loan, Reader

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_book(inventory_number, **kwargs):
    title_fields = {}
    for key in ('title', 'author', 'year', 'publisher', 'genre', 'language', 'description', 'isbn'):
        if key in kwargs:
            title_fields[key] = kwargs.pop(key)
    title_defaults = dict(title='Тестовая книга', author='Тестовый автор')
    title_defaults.update(title_fields)
    book_title = BookTitle.objects.create(**title_defaults)
    defaults = dict(status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(book_title=book_title, inventory_number=inventory_number, **defaults)


def make_reader(username, phone='+998900000000', **kwargs):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone=phone, **kwargs)


def make_location(name='Точка', **kwargs):
    return Location.objects.create(name=name, type='MAHALLA', address='Адрес', **kwargs)


def deliver_book(book, location):
    batch = DeliveryBatch.objects.create(location=location)
    DeliveryItem.objects.create(batch=batch, book=book)
    Book.objects.filter(pk=book.pk).update(status='IN_DELIVERY')
    book.refresh_from_db()
    return batch


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookRequestFromCatalogTests(TestCase):
    def setUp(self):
        self.book = make_book('INV-400')
        self.reader = make_reader('reader1')

    def test_anonymous_redirected_to_login(self):
        response = self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'хочу'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])
        self.assertEqual(BookRequest.objects.count(), 0)

    def test_authenticated_reader_creates_request(self):
        self.client.force_login(self.reader.user)
        response = self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'хочу'})
        self.assertRedirects(response, reverse('catalog:detail', args=[self.book.pk]))
        req = BookRequest.objects.get(book=self.book, reader=self.reader)
        self.assertEqual(req.status, 'PENDING')

    def test_duplicate_active_request_is_prevented(self):
        self.client.force_login(self.reader.user)
        self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'первая'})
        self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'вторая'})
        self.assertEqual(BookRequest.objects.filter(book=self.book, reader=self.reader).count(), 1)

    def test_request_requires_phone(self):
        reader = make_reader('nophone', phone='')
        self.client.force_login(reader.user)
        response = self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'хочу'})
        self.assertRedirects(response, reverse('main:edit_profile'))
        self.assertEqual(BookRequest.objects.count(), 0)

    def test_blocked_reader_cannot_request(self):
        self.reader.is_blocked = True
        self.reader.save()
        self.client.force_login(self.reader.user)
        self.client.post(reverse('catalog:request', args=[self.book.pk]), {'message': 'хочу'})
        self.assertEqual(BookRequest.objects.count(), 0)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class FreeBookRequestTests(TestCase):
    def setUp(self):
        self.reader = make_reader('reader1')
        self.client.force_login(self.reader.user)

    def test_create_free_request_for_book_not_in_catalog(self):
        response = self.client.post(reverse('catalog:free_request'), {
            'requested_title': 'Гарри Поттер',
            'requested_author': 'Дж. Роулинг',
            'message': '',
        })
        self.assertRedirects(response, reverse('main:my'))
        req = BookRequest.objects.get(reader=self.reader)
        self.assertIsNone(req.book)
        self.assertEqual(req.requested_title, 'Гарри Поттер')
        self.assertEqual(req.status, 'PENDING')

    def test_title_is_required(self):
        response = self.client.post(reverse('catalog:free_request'), {
            'requested_title': '',
            'requested_author': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BookRequest.objects.count(), 0)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookQueueTests(TestCase):
    def setUp(self):
        self.location = make_location()
        self.book = make_book('INV-1100')
        deliver_book(self.book, self.location)
        self.holder = make_reader('holder')
        Loan.objects.create(book=self.book, location=self.location, reader=self.holder)
        self.reader = make_reader('reader1')

    def test_cannot_join_queue_for_available_book(self):
        available_book = make_book('INV-1101')
        self.client.force_login(self.reader.user)
        response = self.client.post(reverse('catalog:queue_join', args=[available_book.pk]))
        self.assertRedirects(response, reverse('catalog:detail', args=[available_book.pk]))
        self.assertEqual(BookQueue.objects.count(), 0)

    def test_join_queue_for_loaned_book(self):
        self.client.force_login(self.reader.user)
        response = self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.assertRedirects(response, reverse('catalog:detail', args=[self.book.pk]))
        entry = BookQueue.objects.get(book=self.book, reader=self.reader)
        self.assertEqual(entry.position, 1)

    def test_duplicate_join_is_idempotent(self):
        self.client.force_login(self.reader.user)
        self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.assertEqual(BookQueue.objects.filter(book=self.book, reader=self.reader).count(), 1)

    def test_queue_position_increments(self):
        reader2 = make_reader('reader2')
        self.client.force_login(self.reader.user)
        self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.client.force_login(reader2.user)
        self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))

        entry1 = BookQueue.objects.get(book=self.book, reader=self.reader)
        entry2 = BookQueue.objects.get(book=self.book, reader=reader2)
        self.assertEqual(entry1.position, 1)
        self.assertEqual(entry2.position, 2)

    def test_leave_queue(self):
        BookQueue.objects.create(book=self.book, reader=self.reader)
        self.client.force_login(self.reader.user)
        response = self.client.post(reverse('catalog:queue_leave', args=[self.book.pk]))
        self.assertRedirects(response, reverse('catalog:detail', args=[self.book.pk]))
        self.assertFalse(BookQueue.objects.filter(book=self.book, reader=self.reader).exists())

    def test_queue_requires_phone(self):
        reader = make_reader('nophone', phone='')
        self.client.force_login(reader.user)
        response = self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.assertRedirects(response, reverse('main:edit_profile'))
        self.assertEqual(BookQueue.objects.count(), 0)

    def test_blocked_reader_cannot_join_queue(self):
        self.reader.is_blocked = True
        self.reader.save()
        self.client.force_login(self.reader.user)
        self.client.post(reverse('catalog:queue_join', args=[self.book.pk]))
        self.assertEqual(BookQueue.objects.count(), 0)

    def test_book_detail_shows_queue_ui_when_loaned(self):
        self.client.force_login(self.reader.user)
        response = self.client.get(reverse('catalog:detail', args=[self.book.pk]))
        self.assertContains(response, 'Встать в очередь')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class HiddenLocationCatalogTests(TestCase):
    """Скрытые (is_public=False) библиопункты не должны раскрываться в каталоге."""

    def setUp(self):
        self.hidden = make_location(name='Секретная точка', is_public=False)
        self.visible = make_location(name='Открытая точка', is_public=True)
        self.book_hidden = make_book('INV-1200')
        deliver_book(self.book_hidden, self.hidden)
        self.book_visible = make_book('INV-1201')
        deliver_book(self.book_visible, self.visible)

    def test_hidden_location_name_not_shown_on_card(self):
        response = self.client.get(reverse('catalog:index'))
        self.assertNotContains(response, 'Секретная точка')
        self.assertContains(response, 'Открытая точка')

    def test_hidden_location_not_in_filter_dropdown(self):
        response = self.client.get(reverse('catalog:index'))
        self.assertNotContains(response, f'value="{self.hidden.pk}"')
        self.assertContains(response, f'value="{self.visible.pk}"')

    def test_filtering_by_hidden_location_id_returns_nothing(self):
        response = self.client.get(reverse('catalog:index'), {'location': self.hidden.pk})
        self.assertNotContains(response, self.book_hidden.title)

    def test_hidden_location_not_shown_on_book_detail(self):
        response = self.client.get(reverse('catalog:detail', args=[self.book_hidden.pk]))
        self.assertNotContains(response, 'Секретная точка')

    def test_visible_location_shown_on_book_detail(self):
        response = self.client.get(reverse('catalog:detail', args=[self.book_visible.pk]))
        self.assertContains(response, 'Открытая точка')

    def test_hidden_location_excluded_from_public_map(self):
        self.hidden.latitude, self.hidden.longitude = 39.6, 66.9
        self.hidden.save()
        self.visible.latitude, self.visible.longitude = 39.6, 66.9
        self.visible.save()
        response = self.client.get(reverse('locations_public:map'))
        self.assertNotContains(response, 'Секретная точка')
        self.assertContains(response, 'Открытая точка')

    def test_hidden_location_still_reachable_by_direct_qr_link(self):
        response = self.client.get(f'/p/{self.hidden.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Секретная точка')


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
