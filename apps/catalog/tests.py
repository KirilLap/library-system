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
from .models import Book, BookTitle

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

    def test_deleting_last_copy_removes_empty_book_title(self):
        book = make_book('INV-2000b')
        book_title_id = book.book_title_id
        self.client.post(reverse('catalog_admin:book_delete', args=[book.pk]))
        self.assertFalse(BookTitle.objects.filter(pk=book_title_id).exists())

    def test_deleting_one_of_several_copies_keeps_book_title(self):
        book_title = BookTitle.objects.create(title='Одна книга', author='Автор')
        b1 = Book.objects.create(book_title=book_title, inventory_number='INV-2000c')
        b2 = Book.objects.create(book_title=book_title, inventory_number='INV-2000d')
        self.client.post(reverse('catalog_admin:book_delete', args=[b1.pk]))
        self.assertTrue(BookTitle.objects.filter(pk=book_title.pk).exists())
        self.assertTrue(Book.objects.filter(pk=b2.pk).exists())

    def test_cannot_delete_book_with_loan_history(self):
        """Регрессия: раньше здесь падал необработанный ProtectedError (500)."""
        book = make_book('INV-2001')
        give_loan_history(book, self.location)
        response = self.client.post(reverse('catalog_admin:book_delete', args=[book.pk]))
        self.assertRedirects(response, reverse('catalog_admin:book_update', args=[book.pk]))
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())
        self.assertTrue(BookTitle.objects.filter(pk=book.book_title_id).exists())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookBulkDeleteTests(TestCase):
    """Массовое удаление в book_list работает на уровне названий (BookTitle),
    удаляя все их экземпляры."""

    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)
        self.location = make_location()

    def test_confirm_page_lists_selected_titles(self):
        b1 = make_book('INV-2100', title='Книга Один')
        b2 = make_book('INV-2101', title='Книга Два')
        response = self.client.get(reverse('catalog_admin:book_bulk_delete'), {
            'ids': [b1.book_title_id, b2.book_title_id],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Книга Один')
        self.assertContains(response, 'Книга Два')

    def test_no_selection_redirects_with_warning(self):
        response = self.client.get(reverse('catalog_admin:book_bulk_delete'))
        self.assertRedirects(response, reverse('catalog_admin:index'))

    def test_bulk_delete_removes_all_selected_titles_and_copies(self):
        b1 = make_book('INV-2102')
        b2 = make_book('INV-2103')
        b3 = make_book('INV-2104')
        title_ids = [b1.book_title_id, b2.book_title_id, b3.book_title_id]
        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {'ids': title_ids})
        self.assertRedirects(response, reverse('catalog_admin:index'))
        self.assertEqual(Book.objects.filter(pk__in=[b1.pk, b2.pk, b3.pk]).count(), 0)
        self.assertEqual(BookTitle.objects.filter(pk__in=title_ids).count(), 0)

    def test_bulk_delete_skips_titles_with_loan_history(self):
        deletable = make_book('INV-2105')
        protected = make_book('INV-2106')
        give_loan_history(protected, self.location)

        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {
            'ids': [deletable.book_title_id, protected.book_title_id],
        })
        self.assertRedirects(response, reverse('catalog_admin:index'))
        self.assertFalse(Book.objects.filter(pk=deletable.pk).exists())
        self.assertTrue(Book.objects.filter(pk=protected.pk).exists())
        self.assertTrue(BookTitle.objects.filter(pk=protected.book_title_id).exists())

    def test_bulk_delete_requires_login(self):
        self.client.logout()
        b1 = make_book('INV-2107')
        response = self.client.post(reverse('catalog_admin:book_bulk_delete'), {'ids': [b1.book_title_id]})
        self.assertNotEqual(response.status_code, 200)
        self.assertTrue(Book.objects.filter(pk=b1.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookTitleGroupingTests(TestCase):
    """Экземпляры одной книги (разные инв. номера) объединяются в одну
    запись каталога (BookTitle), но остаются раздельными физическими копиями."""

    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)

    def test_book_list_groups_copies_by_title(self):
        book_title = BookTitle.objects.create(title='Русская ономастика', author='В.Д.Бондалетов', year=1983)
        Book.objects.create(book_title=book_title, inventory_number='694682')
        Book.objects.create(book_title=book_title, inventory_number='695600')
        Book.objects.create(book_title=book_title, inventory_number='690140')

        response = self.client.get(reverse('catalog_admin:index'))
        self.assertContains(response, 'Русская ономастика')
        self.assertContains(response, '<span class="badge bg-secondary">3</span>', html=False)
        self.assertEqual(BookTitle.objects.count(), 1)
        self.assertEqual(Book.objects.count(), 3)

    def test_book_title_detail_lists_all_copies(self):
        book_title = BookTitle.objects.create(title='Одна книга', author='Автор')
        Book.objects.create(book_title=book_title, inventory_number='C-1')
        Book.objects.create(book_title=book_title, inventory_number='C-2')

        response = self.client.get(reverse('catalog_admin:book_title_detail', args=[book_title.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'C-1')
        self.assertContains(response, 'C-2')

    def test_add_copy_to_existing_title(self):
        book_title = BookTitle.objects.create(title='Одна книга', author='Автор')
        Book.objects.create(book_title=book_title, inventory_number='C-1')

        response = self.client.post(
            reverse('catalog_admin:book_copy_create', args=[book_title.pk]),
            {'inventory_number': 'C-2', 'status': 'IN_LIBRARY'},
        )
        self.assertRedirects(response, reverse('catalog_admin:book_title_detail', args=[book_title.pk]))
        self.assertEqual(book_title.copies.count(), 2)

    def test_create_new_book_creates_title_and_first_copy(self):
        response = self.client.post(reverse('catalog_admin:book_create'), {
            'title': 'Новая книга', 'author': 'Новый автор', 'genre': 'OTHER', 'language': 'RU',
            'inventory_number': 'NEW-1', 'status': 'IN_LIBRARY',
        })
        book = Book.objects.get(inventory_number='NEW-1')
        self.assertRedirects(response, reverse('catalog_admin:book_update', args=[book.pk]))
        self.assertEqual(book.book_title.title, 'Новая книга')

    def test_editing_copy_updates_shared_title_for_all_copies(self):
        book_title = BookTitle.objects.create(title='Старое название', author='Автор')
        b1 = Book.objects.create(book_title=book_title, inventory_number='C-1')
        b2 = Book.objects.create(book_title=book_title, inventory_number='C-2')

        self.client.post(reverse('catalog_admin:book_update', args=[b1.pk]), {
            'title': 'Новое название', 'author': 'Автор', 'genre': 'OTHER', 'language': 'RU',
            'inventory_number': 'C-1', 'status': 'IN_LIBRARY',
        })
        b2.refresh_from_db()
        self.assertEqual(b2.title, 'Новое название')


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
