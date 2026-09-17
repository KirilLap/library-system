"""
Тесты жизненного цикла: заявка → одобрение/закупка → выполнение,
и самостоятельная выдача/возврат книги читателем (открытые точки).
"""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.catalog.models import Book
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.staff.models import StaffProfile
from .models import BookRequest, Loan, Reader

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_book(inventory_number, **kwargs):
    defaults = dict(title='Тестовая книга', author='Тестовый автор', status='IN_LIBRARY')
    defaults.update(kwargs)
    return Book.objects.create(inventory_number=inventory_number, **defaults)


def make_location(name='Тестовая махалля', type='MAHALLA', **kwargs):
    return Location.objects.create(name=name, type=type, address='Тестовый адрес', **kwargs)


def make_reader(username, phone='+998900000000', **kwargs):
    user = User.objects.create_user(username=username, password='pass12345')
    return Reader.objects.create(user=user, phone=phone, **kwargs)


def make_librarian(username='librarian'):
    """Роль ADMIN, т.к. staff_required требует существования хотя бы одного
    администратора в системе (иначе редиректит на страницу инициализации)."""
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
    return user


def deliver_book(book, location):
    """Отправляет книгу на точку (переводит в IN_DELIVERY)."""
    batch = DeliveryBatch.objects.create(location=location)
    DeliveryItem.objects.create(batch=batch, book=book)
    Book.objects.filter(pk=book.pk).update(status='IN_DELIVERY')
    book.refresh_from_db()
    return batch


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class BookRequestTransitionsTests(TestCase):
    """Модельные правила смены статуса заявки."""

    def setUp(self):
        self.reader = make_reader('reader1')

    def test_pending_allows_approve_purchasing_reject(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        self.assertEqual(set(req.allowed_next_statuses), {'APPROVED', 'PURCHASING', 'REJECTED'})
        self.assertFalse(req.is_final)

    def test_approved_allows_purchasing_fulfilled_reject(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='APPROVED')
        self.assertEqual(set(req.allowed_next_statuses), {'PURCHASING', 'FULFILLED', 'REJECTED'})

    def test_final_statuses_have_no_further_transitions(self):
        for status in ['FULFILLED', 'REJECTED', 'CANCELLED']:
            req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status=status)
            self.assertTrue(req.is_final)
            self.assertEqual(req.allowed_next_statuses, [])


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LibrarianRequestManagementTests(TestCase):
    """Действия библиотекаря над заявкой: одобрить/закупить/отклонить/выполнить."""

    def setUp(self):
        self.librarian = make_librarian()
        self.reader = make_reader('reader1')
        self.client.force_login(self.librarian)

    def test_approve_pending_request(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        self.client.post(reverse('readers_admin_extra:request_approve', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'APPROVED')

    def test_reject_pending_request(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        self.client.post(reverse('readers_admin_extra:request_reject', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'REJECTED')

    def test_purchasing_transition(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        self.client.post(reverse('readers_admin_extra:request_purchasing', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'PURCHASING')

    def test_fulfill_approved_request_with_already_linked_book(self):
        book = make_book('INV-100')
        req = BookRequest.objects.create(reader=self.reader, book=book, status='APPROVED')
        self.client.post(reverse('readers_admin_extra:request_fulfill', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'FULFILLED')

    def test_cannot_change_status_of_final_request(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='FULFILLED')
        self.client.post(reverse('readers_admin_extra:request_reject', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'FULFILLED')

    def test_invalid_transition_is_rejected(self):
        # PENDING -> FULFILLED напрямую не разрешён (нужно сначала approve/purchasing)
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        self.client.post(reverse('readers_admin_extra:request_fulfill', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'PENDING')

    def test_anonymous_cannot_manage_requests(self):
        self.client.logout()
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        response = self.client.post(reverse('readers_admin_extra:request_approve', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'PENDING')
        self.assertNotEqual(response.status_code, 200)

    def test_fulfill_with_book_select_existing(self):
        book = make_book('INV-101')
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='APPROVED')
        response = self.client.post(
            reverse('readers_admin_extra:request_fulfill_with_book', args=[req.pk]),
            {'action': 'select', 'book_id': str(book.pk)},
        )
        req.refresh_from_db()
        self.assertEqual(req.status, 'FULFILLED')
        self.assertEqual(req.book_id, book.pk)
        self.assertRedirects(response, reverse('readers_admin_extra:request_detail', args=[req.pk]))

    def test_fulfill_with_book_select_nonexistent_book_does_not_crash(self):
        """Регрессия: раньше здесь падал UnboundLocalError на `form`."""
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='APPROVED')
        response = self.client.post(
            reverse('readers_admin_extra:request_fulfill_with_book', args=[req.pk]),
            {'action': 'select', 'book_id': '999999'},
        )
        self.assertEqual(response.status_code, 200)
        req.refresh_from_db()
        self.assertEqual(req.status, 'APPROVED')

    def test_fulfill_with_book_create_new(self):
        req = BookRequest.objects.create(
            reader=self.reader, requested_title='Новая книга', requested_author='Автор', status='PURCHASING',
        )
        response = self.client.post(
            reverse('readers_admin_extra:request_fulfill_with_book', args=[req.pk]),
            {
                'action': 'create',
                'inventory_number': 'INV-102',
                'title': 'Новая книга',
                'author': 'Автор',
                'genre': 'OTHER',
                'language': 'RU',
                'status': 'IN_LIBRARY',
            },
        )
        req.refresh_from_db()
        self.assertEqual(req.status, 'FULFILLED')
        self.assertIsNotNone(req.book)
        self.assertEqual(req.book.inventory_number, 'INV-102')
        self.assertRedirects(response, reverse('readers_admin_extra:request_detail', args=[req.pk]))

    def test_fulfill_with_book_on_final_request_redirects_without_crash(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='FULFILLED')
        response = self.client.get(reverse('readers_admin_extra:request_fulfill_with_book', args=[req.pk]))
        self.assertRedirects(response, reverse('readers_admin_extra:request_detail', args=[req.pk]))


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class TakeBookTests(TestCase):
    """Самостоятельная выдача книги читателем по инв. номеру (открытая точка)."""

    def setUp(self):
        self.location = make_location()
        self.reader = make_reader('reader1')
        self.client.force_login(self.reader.user)

    def test_take_available_book(self):
        book = make_book('INV-200')
        deliver_book(book, self.location)
        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-200'})
        self.assertRedirects(response, reverse('main:my'))
        loan = Loan.objects.get(book=book)
        self.assertEqual(loan.reader, self.reader)
        self.assertFalse(loan.is_returned)
        self.assertIsNone(loan.issued_by)

    def test_cannot_take_book_still_in_library(self):
        make_book('INV-201')  # status='IN_LIBRARY' by default, никуда не доставлена
        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-201'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.count(), 0)

    def test_cannot_take_already_loaned_book(self):
        book = make_book('INV-202')
        deliver_book(book, self.location)
        other_reader = make_reader('reader2')
        Loan.objects.create(book=book, location=self.location, reader=other_reader)

        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-202'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Loan.objects.filter(book=book).count(), 1)

    def test_unknown_inventory_number_shows_error_without_crash(self):
        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'DOES-NOT-EXIST'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'не найдена')

    def test_take_book_requires_phone(self):
        reader = make_reader('nophone', phone='')
        self.client.force_login(reader.user)
        book = make_book('INV-203')
        deliver_book(book, self.location)
        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-203'})
        self.assertRedirects(response, reverse('main:edit_profile'))
        self.assertEqual(Loan.objects.count(), 0)

    def test_blocked_reader_cannot_take_book(self):
        self.reader.is_blocked = True
        self.reader.save()
        book = make_book('INV-204')
        deliver_book(book, self.location)
        response = self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-204'})
        self.assertRedirects(response, reverse('main:my'))
        self.assertEqual(Loan.objects.count(), 0)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class ReturnLoanTests(TestCase):
    """Возврат книги читателем."""

    def setUp(self):
        self.location = make_location()
        self.reader = make_reader('reader1')
        self.book = make_book('INV-300')
        deliver_book(self.book, self.location)
        self.loan = Loan.objects.create(book=self.book, location=self.location, reader=self.reader)
        self.client.force_login(self.reader.user)

    def test_return_own_loan(self):
        response = self.client.post(reverse('main:return_loan', args=[self.loan.pk]))
        self.assertRedirects(response, reverse('main:my'))
        self.loan.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertIsNotNone(self.loan.returned_at)

    def test_cannot_return_someone_elses_loan(self):
        other_reader = make_reader('reader2')
        self.client.force_login(other_reader.user)
        response = self.client.post(reverse('main:return_loan', args=[self.loan.pk]))
        self.assertEqual(response.status_code, 404)
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_returned)

    def test_cannot_return_already_returned_loan(self):
        self.loan.is_returned = True
        self.loan.save()
        response = self.client.post(reverse('main:return_loan', args=[self.loan.pk]))
        self.assertEqual(response.status_code, 404)

    def test_return_requires_post(self):
        response = self.client.get(reverse('main:return_loan', args=[self.loan.pk]))
        self.assertEqual(response.status_code, 405)


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class CancelRequestTests(TestCase):
    """Отмена заявки читателем."""

    def setUp(self):
        self.reader = make_reader('reader1')
        self.client.force_login(self.reader.user)

    def test_cancel_pending_request(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга')
        response = self.client.post(reverse('main:cancel_request', args=[req.pk]))
        self.assertRedirects(response, reverse('main:my'))
        req.refresh_from_db()
        self.assertEqual(req.status, 'CANCELLED')

    def test_cannot_cancel_fulfilled_request(self):
        req = BookRequest.objects.create(reader=self.reader, requested_title='Книга', status='FULFILLED')
        self.client.post(reverse('main:cancel_request', args=[req.pk]))
        req.refresh_from_db()
        self.assertEqual(req.status, 'FULFILLED')

    def test_cannot_cancel_someone_elses_request(self):
        other_reader = make_reader('reader2')
        req = BookRequest.objects.create(reader=other_reader, requested_title='Книга')
        response = self.client.post(reverse('main:cancel_request', args=[req.pk]))
        self.assertEqual(response.status_code, 404)


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
