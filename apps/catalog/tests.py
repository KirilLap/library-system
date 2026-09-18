"""Тесты удаления книг (одиночного и массового)."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan, Reader
from apps.staff.models import StaffProfile
from .models import Book

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_book(inventory_number, **kwargs):
    defaults = dict(title='Тестовая книга', author='Тестовый автор', status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(inventory_number=inventory_number, **defaults)


def make_location(name='Точка', **kwargs):
    return Location.objects.create(name=name, type='MAHALLA', address='Адрес', **kwargs)


def make_librarian(username='librarian'):
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
    return user


def make_reader(username):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone='+998900000000')


def give_loan_history(book, location):
    """Создаёт (возвращённую) выдачу книги — на неё ссылается Loan.book с
    on_delete=PROTECT, поэтому такую книгу нельзя удалить обычным способом."""
    reader = make_reader(f'reader_{book.pk}')
    Loan.objects.create(book=book, location=location, reader=reader, is_returned=True)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookDeleteTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)
        self.location = make_location()

    def test_delete_book_without_history(self):
        book = make_book('INV-2000')
        response = self.client.post(reverse('catalog_admin:book_delete', args=[book.pk]))
        self.assertRedirects(response, reverse('catalog_admin:index'))
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())

    def test_cannot_delete_book_with_loan_history(self):
        """Регрессия: раньше здесь падал необработанный ProtectedError (500)."""
        book = make_book('INV-2001')
        give_loan_history(book, self.location)
        response = self.client.post(reverse('catalog_admin:book_delete', args=[book.pk]))
        self.assertRedirects(response, reverse('catalog_admin:book_update', args=[book.pk]))
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookBulkDeleteTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)
        self.location = make_location()

    def test_confirm_page_lists_selected_books(self):
        b1 = make_book('INV-2100')
        b2 = make_book('INV-2101')
        response = self.client.get(reverse('catalog_admin:book_bulk_delete'), {'ids': [b1.pk, b2.pk]})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'INV-2100')
        self.assertContains(response, 'INV-2101')

    def test_no_selection_redirects_with_warning(self):
        response = self.client.get(reverse('catalog_admin:book_bulk_delete'))
        self.assertRedirects(response, reverse('catalog_admin:index'))

    def test_bulk_delete_removes_all_selected(self):
        b1 = make_book('INV-2102')
        b2 = make_book('INV-2103')
        b3 = make_book('INV-2104')
        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {
            'ids': [b1.pk, b2.pk, b3.pk],
        })
        self.assertRedirects(response, reverse('catalog_admin:index'))
        self.assertEqual(Book.objects.filter(pk__in=[b1.pk, b2.pk, b3.pk]).count(), 0)

    def test_bulk_delete_skips_books_with_loan_history(self):
        deletable = make_book('INV-2105')
        protected = make_book('INV-2106')
        give_loan_history(protected, self.location)

        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {
            'ids': [deletable.pk, protected.pk],
        })
        self.assertRedirects(response, reverse('catalog_admin:index'))
        self.assertFalse(Book.objects.filter(pk=deletable.pk).exists())
        self.assertTrue(Book.objects.filter(pk=protected.pk).exists())

    def test_bulk_delete_requires_login(self):
        self.client.logout()
        b1 = make_book('INV-2107')
        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {'ids': [b1.pk]})
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(Book.objects.filter(pk=b1.pk).exists())


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
