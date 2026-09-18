"""Тесты удаления партии доставки."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Book, BookTitle
from apps.locations.models import Location
from apps.readers.models import Loan, Reader
from apps.staff.models import StaffProfile
from .models import DeliveryBatch, DeliveryItem

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


def make_location(name='Тестовая точка', **kwargs):
    return Location.objects.create(name=name, type='MAHALLA', address='Адрес', **kwargs)


def make_librarian(username='librarian'):
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
    return user


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BatchDeleteTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)
        self.location = make_location()
        self.batch = DeliveryBatch.objects.create(location=self.location)
        self.book = make_book('INV-700')
        DeliveryItem.objects.create(batch=self.batch, book=self.book)
        Book.objects.filter(pk=self.book.pk).update(status='IN_DELIVERY')

    def test_delete_batch_resets_book_status(self):
        response = self.client.post(reverse('deliveries_admin:delete', args=[self.batch.pk]))
        self.assertRedirects(response, reverse('deliveries_admin:index'))
        self.assertFalse(DeliveryBatch.objects.filter(pk=self.batch.pk).exists())
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, 'IN_LIBRARY')

    def test_cannot_delete_batch_with_active_loan(self):
        user = User.objects.create_user(username='reader1', password='pass12345')
        reader = Reader.objects.create(user=user, phone='+998900000000')
        Loan.objects.create(book=self.book, location=self.location, reader=reader)

        response = self.client.get(reverse('deliveries_admin:delete', args=[self.batch.pk]))
        self.assertContains(response, 'Нельзя удалить')

        response = self.client.post(reverse('deliveries_admin:delete', args=[self.batch.pk]))
        self.assertRedirects(response, reverse('deliveries_admin:detail', args=[self.batch.pk]))
        self.assertTrue(DeliveryBatch.objects.filter(pk=self.batch.pk).exists())
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, 'IN_DELIVERY')


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
