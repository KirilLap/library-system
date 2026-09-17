"""Тесты подачи заявки из публичного каталога."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Book
from apps.readers.models import BookRequest, Reader

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_book(inventory_number, **kwargs):
    defaults = dict(title='Тестовая книга', author='Тестовый автор', status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(inventory_number=inventory_number, **defaults)


def make_reader(username, phone='+998900000000', **kwargs):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone=phone, **kwargs)


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


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
