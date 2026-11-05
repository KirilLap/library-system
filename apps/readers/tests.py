"""
Тесты жизненного цикла: заявка → одобрение/закупка → выполнение,
и самостоятельная выдача/возврат книги читателем (открытые библиопункты).
"""
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
from apps.staff.models import StaffProfile
from .models import BookRequest, Loan, Reader

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
    """Отправляет книгу в библиопункт (переводит в IN_DELIVERY)."""
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
    """Самостоятельная выдача книги читателем по инв. номеру (открытый библиопункт)."""

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

    def test_take_book_does_not_require_phone(self):
        reader = make_reader('nophone', phone='')
        self.client.force_login(reader.user)
        book = make_book('INV-203')
        deliver_book(book, self.location)
        self.client.post(reverse('main:take_book'), {'inventory_number': 'INV-203'})
        self.assertEqual(Loan.objects.filter(reader=reader).count(), 1)

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


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LoanOverdueTests(TestCase):
    def setUp(self):
        self.location = make_location()
        self.reader = make_reader('reader1')
        self.book = make_book('INV-1000')
        deliver_book(self.book, self.location)

    def test_fresh_loan_is_not_overdue(self):
        loan = Loan.objects.create(book=self.book, location=self.location, reader=self.reader)
        self.assertFalse(loan.is_overdue)
        self.assertEqual(loan.days_held, 0)

    def test_old_unreturned_loan_is_overdue(self):
        from django.conf import settings
        loan = Loan.objects.create(book=self.book, location=self.location, reader=self.reader)
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - datetime.timedelta(days=settings.LOAN_PERIOD_DAYS + 5)
        )
        loan.refresh_from_db()
        self.assertTrue(loan.is_overdue)
        self.assertEqual(loan.days_held, settings.LOAN_PERIOD_DAYS + 5)

    def test_returned_loan_is_never_overdue(self):
        loan = Loan.objects.create(
            book=self.book, location=self.location, reader=self.reader, is_returned=True,
        )
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - datetime.timedelta(days=9999)
        )
        loan.refresh_from_db()
        self.assertFalse(loan.is_overdue)

    def test_my_cabinet_shows_overdue_reminder(self):
        loan = Loan.objects.create(book=self.book, location=self.location, reader=self.reader)
        Loan.objects.filter(pk=loan.pk).update(issued_at=timezone.now() - datetime.timedelta(days=40))
        self.client.force_login(self.reader.user)
        response = self.client.get(reverse('main:my'))
        self.assertContains(response, 'Пора вернуть книгу')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class ReaderDeleteTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)

    def test_delete_reader_without_loan_history(self):
        reader = make_reader('reader1')
        user_pk = reader.user_id
        response = self.client.post(reverse('readers_admin:delete', args=[reader.pk]))
        self.assertRedirects(response, reverse('readers_admin:index'))
        self.assertFalse(Reader.objects.filter(pk=reader.pk).exists())
        self.assertFalse(User.objects.filter(pk=user_pk).exists())

    def test_delete_reader_removes_their_requests(self):
        reader = make_reader('reader1')
        BookRequest.objects.create(reader=reader, requested_title='Книга')
        self.client.post(reverse('readers_admin:delete', args=[reader.pk]))
        self.assertEqual(BookRequest.objects.count(), 0)

    def test_cannot_delete_reader_with_loan_history(self):
        location = make_location()
        reader = make_reader('reader1')
        book = make_book('INV-800')
        deliver_book(book, location)
        Loan.objects.create(book=book, location=location, reader=reader, is_returned=True)

        response = self.client.get(reverse('readers_admin:delete', args=[reader.pk]))
        self.assertContains(response, 'Нельзя удалить')

        response = self.client.post(reverse('readers_admin:delete', args=[reader.pk]))
        self.assertRedirects(response, reverse('readers_admin:detail', args=[reader.pk]))
        self.assertTrue(Reader.objects.filter(pk=reader.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LanguagePreferenceTests(TestCase):
    """Выбор языка читателем запоминается в профиле и применяется при следующем входе."""

    def setUp(self):
        self.reader = make_reader('reader_lang')

    def test_switching_language_saves_it_to_profile(self):
        self.client.force_login(self.reader.user)
        self.client.post(reverse('main:set_language'), {'language': 'uz', 'next': '/catalog/'})
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.language, 'uz')

    def test_switching_language_ignored_for_unknown_code(self):
        self.client.force_login(self.reader.user)
        self.client.post(reverse('main:set_language'), {'language': 'xx', 'next': '/catalog/'})
        self.reader.refresh_from_db()
        self.assertEqual(self.reader.language, '')

    def test_login_activates_saved_language(self):
        self.reader.language = 'uz'
        self.reader.save(update_fields=['language'])
        response = self.client.post(reverse('main:login'), {
            'username': self.reader.user.username, 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.cookies['django_language'].value, 'uz')

    def test_login_without_saved_language_leaves_cookie_untouched(self):
        response = self.client.post(reverse('main:login'), {
            'username': self.reader.user.username, 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('django_language', response.cookies)


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)


class SimpleRegistrationTests(TestCase):
    """Упрощённая регистрация: ФИО, год рождения, ближайший библиопункт; без телефона и адреса."""

    def setUp(self):
        self.point = make_location('Махалля Тест')

    def _data(self, **extra):
        data = {
            'last_name': 'Каримов', 'first_name': 'Али', 'gender': 'M', 'birth_year': 2008,
            'nearest_location': self.point.pk, 'username': 'ali2008',
            'password1': 'Str0ng-pass-77', 'password2': 'Str0ng-pass-77',
        }
        data.update(extra)
        return data

    def test_register_without_phone_and_address(self):
        response = self.client.post(reverse('readers_auth:register'), self._data())
        self.assertRedirects(response, reverse('main:my'))
        reader = Reader.objects.get(user__username='ali2008')
        self.assertEqual(reader.birth_year, 2008)
        self.assertEqual(reader.gender, 'M')
        self.assertEqual(reader.nearest_location, self.point)
        self.assertEqual(reader.phone, '')
        self.assertFalse(reader.must_change_password)
        self.assertRegex(reader.card_id, r'^[1-9]\d{9}$')
        self.assertEqual(reader.user.username, 'ali2008')

    def test_nearest_location_is_optional(self):
        self.client.post(reverse('readers_auth:register'), self._data(nearest_location=''))
        self.assertIsNone(Reader.objects.get(user__username='ali2008').nearest_location)

    def test_gender_is_required_and_limited_to_two_values(self):
        self.client.post(reverse('readers_auth:register'), self._data(gender=''))
        self.assertFalse(Reader.objects.filter(user__username='ali2008').exists())
        self.client.post(reverse('readers_auth:register'), self._data(gender='X'))
        self.assertFalse(Reader.objects.filter(user__username='ali2008').exists())
        self.client.post(reverse('readers_auth:register'), self._data(gender='F'))
        self.assertEqual(Reader.objects.get(user__username='ali2008').gender, 'F')

    def test_future_birth_year_rejected(self):
        self.client.post(reverse('readers_auth:register'), self._data(birth_year=2999))
        self.assertFalse(Reader.objects.filter(user__username='ali2008').exists())

    def test_hidden_location_not_offered(self):
        hidden = make_location('Скрытый', is_public=False)
        self.client.post(reverse('readers_auth:register'), self._data(nearest_location=hidden.pk))
        self.assertFalse(Reader.objects.filter(user__username='ali2008').exists())

    def test_cabinet_works_without_phone(self):
        reader = make_reader('nophone2', phone='')
        self.client.force_login(reader.user)
        response = self.client.get(reverse('main:my'))
        self.assertEqual(response.status_code, 200)


class StaffCreateReaderTests(TestCase):
    """Сотрудник вносит читателя вручную: ID = логин = временный пароль, при входе пароль меняется."""

    def setUp(self):
        from apps.staff.models import StaffProfile
        self.staff_user = User.objects.create_user('lib', password='pw-lib-123')
        StaffProfile.objects.create(user=self.staff_user, role=StaffProfile.ROLE_ADMIN)
        self.client.force_login(self.staff_user)

    def _create(self, **extra):
        data = {'last_name': 'Саидов', 'first_name': 'Бобур', 'gender': 'M', 'birth_year': 1999, 'nearest_location': ''}
        data.update(extra)
        return self.client.post(reverse('readers_admin:create'), data)

    def _new_reader(self):
        self._create()
        return Reader.objects.get(user__last_name='Саидов')

    def test_staff_can_create_reader_with_generated_id(self):
        response = self._create()
        reader = Reader.objects.get(user__last_name='Саидов')
        self.assertRedirects(response, reverse('readers_admin:detail', args=[reader.pk]))
        self.assertRegex(reader.card_id, r'^[1-9]\d{9}$')
        self.assertEqual(reader.user.username, reader.card_id)
        self.assertTrue(reader.user.check_password(reader.card_id))
        self.assertTrue(reader.must_change_password)

    def test_each_reader_gets_unique_id(self):
        self._create()
        self._create(first_name='Другой')
        ids = list(Reader.objects.values_list('card_id', flat=True))
        self.assertEqual(len(ids), 2)
        self.assertEqual(len(set(ids)), 2)

    def test_create_form_requires_staff(self):
        self.client.logout()
        response = self.client.get(reverse('readers_admin:create'))
        self.assertNotEqual(response.status_code, 200)

    def test_search_by_id(self):
        reader = self._new_reader()
        response = self.client.get(reverse('readers_admin:index'), {'q': reader.card_id})
        self.assertContains(response, reader.card_id)

    def test_first_login_forces_password_change(self):
        reader = self._new_reader()
        self.client.logout()
        response = self.client.post(reverse('main:login'), {'username': reader.card_id, 'password': reader.card_id})
        self.assertRedirects(response, reverse('main:change_password'))
        response = self.client.get(reverse('main:my'))
        self.assertRedirects(response, reverse('main:change_password'), fetch_redirect_response=False)

    def test_password_change_unlocks_cabinet(self):
        reader = self._new_reader()
        self.client.logout()
        self.client.post(reverse('main:login'), {'username': reader.card_id, 'password': reader.card_id})
        response = self.client.post(reverse('main:change_password'), {
            'new_password1': 'Mine-Own-Pass-55', 'new_password2': 'Mine-Own-Pass-55',
        })
        self.assertRedirects(response, reverse('main:my'))
        reader.refresh_from_db()
        self.assertFalse(reader.must_change_password)
        self.assertEqual(self.client.get(reverse('main:my')).status_code, 200)
