"""Тесты выдачи/возврата книг работником закрытой точки (школа/организация)."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Book
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan, Reader
from .models import LocationWorker

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_book(inventory_number, **kwargs):
    defaults = dict(title='Тестовая книга', author='Тестовый автор', status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(inventory_number=inventory_number, **defaults)


def make_location(name='Школа №1', type='SCHOOL', **kwargs):
    return Location.objects.create(name=name, type=type, address='Тестовый адрес', **kwargs)


def deliver_book(book, location):
    batch = DeliveryBatch.objects.create(location=location)
    DeliveryItem.objects.create(batch=batch, book=book)
    Book.objects.filter(pk=book.pk).update(status='IN_DELIVERY')
    book.refresh_from_db()
    return batch


def make_worker(location, username='worker1'):
    user = User.objects.create_user(username=username, password='pass12345')
    return LocationWorker.objects.create(user=user, location=location, is_active=True)


def make_reader(username, **kwargs):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone='+998900000000', **kwargs)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class WorkerIssueTests(TestCase):
    def setUp(self):
        self.location = make_location()
        self.other_location = make_location(name='Школа №2')
        self.worker = make_worker(self.location)
        self.reader = make_reader('reader1', affiliated_location=self.location)
        self.client.force_login(self.worker.user)

    def test_lookup_book_at_own_location(self):
        book = make_book('INV-500')
        deliver_book(book, self.location)
        response = self.client.post(reverse('organizations:worker_issue'), {
            'action': 'lookup_book', 'inventory_number': 'INV-500',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, book.title)

    def test_lookup_book_at_other_location_shows_error(self):
        book = make_book('INV-501')
        deliver_book(book, self.other_location)
        response = self.client.post(reverse('organizations:worker_issue'), {
            'action': 'lookup_book', 'inventory_number': 'INV-501',
        })
        self.assertContains(response, 'не находится на вашей точке')

    def test_issue_creates_loan_with_issued_by(self):
        book = make_book('INV-502')
        deliver_book(book, self.location)
        response = self.client.post(reverse('organizations:worker_issue'), {
            'action': 'issue', 'inventory_number': 'INV-502', 'reader_pk': str(self.reader.pk),
        })
        self.assertRedirects(response, reverse('organizations:worker_cabinet'))
        loan = Loan.objects.get(book=book)
        self.assertEqual(loan.reader, self.reader)
        self.assertEqual(loan.issued_by, self.worker)
        self.assertFalse(loan.is_returned)

    def test_cannot_issue_already_loaned_book(self):
        book = make_book('INV-503')
        deliver_book(book, self.location)
        Loan.objects.create(book=book, location=self.location, reader=self.reader, issued_by=self.worker)

        other_reader = make_reader('reader2', affiliated_location=self.location)
        response = self.client.post(reverse('organizations:worker_issue'), {
            'action': 'issue', 'inventory_number': 'INV-503', 'reader_pk': str(other_reader.pk),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.filter(book=book).count(), 1)

    def test_non_worker_cannot_access(self):
        outsider = User.objects.create_user(username='outsider', password='pass12345')
        self.client.force_login(outsider)
        response = self.client.get(reverse('organizations:worker_issue'))
        self.assertNotEqual(response.status_code, 200)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class WorkerReturnTests(TestCase):
    def setUp(self):
        self.location = make_location()
        self.other_location = make_location(name='Школа №2')
        self.worker = make_worker(self.location)
        self.reader = make_reader('reader1', affiliated_location=self.location)
        self.book = make_book('INV-600')
        deliver_book(self.book, self.location)
        self.loan = Loan.objects.create(
            book=self.book, location=self.location, reader=self.reader, issued_by=self.worker,
        )
        self.client.force_login(self.worker.user)

    def test_worker_returns_loan_from_own_location(self):
        response = self.client.post(reverse('organizations:worker_return'), {'loan_pk': self.loan.pk})
        self.assertRedirects(response, reverse('organizations:worker_return'))
        self.loan.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertIsNotNone(self.loan.returned_at)

    def test_worker_cannot_return_loan_from_other_location(self):
        other_worker = make_worker(self.other_location, username='worker2')
        self.client.force_login(other_worker.user)
        response = self.client.post(reverse('organizations:worker_return'), {'loan_pk': self.loan.pk})
        self.assertEqual(response.status_code, 404)
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_returned)


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
