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


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class ActDownloadTests(TestCase):
    def setUp(self):
        self.client.force_login(make_librarian())
        self.location = make_location(name="Ko'chma nuqta", contact_person='Иванов И.')
        self.batch = DeliveryBatch.objects.create(location=self.location, note='Хрупкие книги')
        for n, title in (('INV-901', 'Русская ономастика'), ('INV-902', "O'zbek ertaklari")):
            book = make_book(n, title=title, author='Автор', year=1983)
            DeliveryItem.objects.create(batch=self.batch, book=book)

    def _docx_text(self, response):
        import io
        from docx import Document
        doc = Document(io.BytesIO(response.content))
        parts = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                parts.extend(cell.text for cell in row.cells)
        return '\n'.join(parts)

    def test_pdf_download(self):
        response = self.client.get(reverse('deliveries_admin:pdf', args=[self.batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF'))
        self.assertIn('.pdf', response['Content-Disposition'])

    def test_word_download_contains_batch_data(self):
        response = self.client.get(reverse('deliveries_admin:docx', args=[self.batch.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertIn('wordprocessingml', response['Content-Type'])
        self.assertIn('.docx', response['Content-Disposition'])
        text = self._docx_text(response)
        for expected in ('INV-901', 'INV-902', 'Русская ономастика', "Ko'chma nuqta",
                         'Иванов И.', 'Хрупкие книги', 'Итого книг'):
            self.assertIn(expected, text)

    def test_word_act_follows_active_language(self):
        self.client.cookies['django_language'] = 'uz'
        response = self.client.get(reverse('deliveries_admin:docx', args=[self.batch.pk]))
        text = self._docx_text(response)
        self.assertIn('Jami kitoblar', text)
        self.assertNotIn('Итого книг', text)

    def test_pdf_in_uzbek_does_not_fail(self):
        self.client.cookies['django_language'] = 'uz'
        response = self.client.get(reverse('deliveries_admin:pdf', args=[self.batch.pk]))
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_requires_login(self):
        self.client.logout()
        for name in ('pdf', 'docx'):
            response = self.client.get(reverse(f'deliveries_admin:{name}', args=[self.batch.pk]))
            self.assertEqual(response.status_code, 302)
