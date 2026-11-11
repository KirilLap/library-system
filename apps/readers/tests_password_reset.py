from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.readers.models import PasswordResetRequest, Reader
from apps.readers.passwords import ALPHABET, TEMP_PASSWORD_LENGTH, generate_temp_password, pending_count
from apps.staff.models import ActionLog, StaffProfile


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


def make_reader(username='ali', last='Каримов', card='1234567890'):
    user = User.objects.create_user(username, password='old-password-1', first_name='Али', last_name=last)
    return Reader.objects.create(user=user, card_id=card)


NEUTRAL = 'запрос передан администратору'


class SelfServiceRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.reader = make_reader()
        staff('adm', StaffProfile.ROLE_ADMIN)           # без администратора сайт просит первичную настройку

    def _post(self, login, last):
        return self.client.post(reverse('main:password_reset'), {'login': login, 'last_name': last})

    def test_request_by_username_and_by_id(self):
        self.assertContains(self._post('ali', 'Каримов'), NEUTRAL)
        self.assertEqual(PasswordResetRequest.objects.count(), 1)
        PasswordResetRequest.objects.all().delete()
        self._post('1234567890', 'каримов ')                    # по ID, регистр и пробелы не важны
        self.assertEqual(PasswordResetRequest.objects.count(), 1)
        self.assertEqual(PasswordResetRequest.objects.get().source, 'SELF')

    def test_wrong_surname_or_unknown_login_create_nothing_but_look_the_same(self):
        ok = self._post('ali', 'Каримов')
        PasswordResetRequest.objects.all().delete()
        for login, last in (('ali', 'Другой'), ('nobody', 'Каримов'), ('', '')):
            response = self._post(login, last)
            self.assertEqual(PasswordResetRequest.objects.count(), 0, (login, last))
        # для существующего и несуществующего читателя ответ одинаковый: так нельзя узнать, кто зарегистрирован
        same = self._post('nobody', 'Каримов')
        self.assertEqual(ok.status_code, same.status_code)
        self.assertContains(same, NEUTRAL)

    def test_no_duplicate_pending_requests(self):
        self._post('ali', 'Каримов')
        self._post('ali', 'Каримов')
        self.assertEqual(PasswordResetRequest.objects.count(), 1)

    def test_too_many_attempts_are_throttled(self):
        for _ in range(8):
            self._post('nobody', 'x')
        response = self._post('ali', 'Каримов')
        self.assertContains(response, 'Слишком много попыток')
        self.assertEqual(PasswordResetRequest.objects.count(), 0)

    def test_page_and_login_link(self):
        self.assertEqual(self.client.get(reverse('main:password_reset')).status_code, 200)
        self.assertContains(self.client.get(reverse('main:login')), reverse('main:password_reset'))


class AdminIssuesPasswordTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.reader = make_reader()
        self.reset = PasswordResetRequest.objects.create(reader=self.reader)
        self.client.force_login(self.admin)

    def _issue(self):
        return self.client.post(reverse('readers_admin:reset_issue', args=[self.reset.pk]))

    def _password(self, response):
        follow = self.client.get(response['Location'])
        return follow.context['password']

    def test_temp_password_works_and_forces_change(self):
        response = self._issue()
        self.assertRedirects(response, reverse('readers_admin:temp_password', args=[self.reader.pk]), fetch_redirect_response=False)
        password = self._password(response)
        self.assertEqual(len(password), TEMP_PASSWORD_LENGTH)
        self.assertTrue(set(password) <= set(ALPHABET))
        self.reader.refresh_from_db()
        self.assertTrue(self.reader.must_change_password)
        self.assertFalse(User.objects.get(username='ali').check_password('old-password-1'))     # старый перестал работать
        self.client.logout()
        login = self.client.post(reverse('main:login'), {'username': 'ali', 'password': password})
        self.assertRedirects(login, reverse('main:change_password'))                           # сразу просит новый

    def test_password_is_shown_only_once_and_not_stored_in_clear(self):
        response = self._issue()
        url = response['Location']
        first = self.client.get(url)
        self.assertIsNotNone(first.context['password'])
        self.assertContains(first, first.context['password'])
        self.assertEqual(first['Cache-Control'], 'no-store')
        second = self.client.get(url)
        self.assertIsNone(second.context['password'])
        self.assertContains(second, 'уже был показан')
        self.assertNotIn(first.context['password'], User.objects.get(username='ali').password)

    def test_request_is_closed_and_logged_without_the_password(self):
        password = self._password(self._issue())
        self.reset.refresh_from_db()
        self.assertEqual((self.reset.status, self.reset.handled_by), ('DONE', self.admin))
        self.assertEqual(pending_count(), 0)
        entry = ActionLog.objects.latest('pk')
        self.assertIn('временный пароль', entry.action)
        self.assertNotIn(password, entry.action)

    def test_temp_passwords_differ(self):
        self.assertNotEqual(generate_temp_password(), generate_temp_password())

    def test_reject(self):
        self.client.post(reverse('readers_admin:reset_reject', args=[self.reset.pk]))
        self.reset.refresh_from_db()
        self.assertEqual(self.reset.status, 'REJECTED')
        self.assertTrue(User.objects.get(username='ali').check_password('old-password-1'))      # пароль не тронут

    def test_handled_request_cannot_be_issued_twice(self):
        self._issue()
        self.assertEqual(self._issue().status_code, 404)

    def test_admin_resets_straight_from_the_card_and_closes_pending(self):
        response = self.client.post(reverse('readers_admin:reader_reset_password', args=[self.reader.pk]))
        self.assertTrue(self._password(response))
        self.reset.refresh_from_db()
        self.assertEqual(self.reset.status, 'DONE')

    def test_requests_page_and_counters(self):
        page = self.client.get(reverse('readers_admin:reset_requests'))
        self.assertContains(page, 'Каримов')
        self.assertEqual(self.client.get(reverse('readers_admin:index')).context['reset_pending'], 1)
        self.assertEqual(self.client.get(reverse('staff:dashboard')).context['reset_pending'], 1)
        self.assertContains(self.client.get(reverse('staff:dashboard')), 'Запросов на сброс пароля: 1')

    def test_get_not_allowed_on_actions(self):
        for name, pk in (('reset_issue', self.reset.pk), ('reset_reject', self.reset.pk),
                         ('reader_reset_password', self.reader.pk), ('reader_request_reset', self.reader.pk)):
            self.assertEqual(self.client.get(reverse(f'readers_admin:{name}', args=[pk])).status_code, 405, name)


class LibrarianLimitsTests(TestCase):
    """Библиотекарь пароль выдать не может, только оформить запрос; читатель тем более."""

    def setUp(self):
        cache.clear()
        staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.reader = make_reader()
        self.client.force_login(self.librarian)

    def test_librarian_can_only_create_a_request(self):
        response = self.client.post(reverse('readers_admin:reader_request_reset', args=[self.reader.pk]))
        self.assertRedirects(response, reverse('readers_admin:detail', args=[self.reader.pk]))
        reset = PasswordResetRequest.objects.get()
        self.assertEqual((reset.source, reset.requested_by), ('STAFF', self.librarian))
        self.client.post(reverse('readers_admin:reader_request_reset', args=[self.reader.pk]))   # повтор не плодит запросы
        self.assertEqual(PasswordResetRequest.objects.count(), 1)

    def test_librarian_cannot_issue_reject_or_list(self):
        reset = PasswordResetRequest.objects.create(reader=self.reader)
        self.client.post(reverse('readers_admin:reset_issue', args=[reset.pk]))
        self.client.post(reverse('readers_admin:reset_reject', args=[reset.pk]))
        self.client.post(reverse('readers_admin:reader_reset_password', args=[self.reader.pk]))
        reset.refresh_from_db()
        self.assertEqual(reset.status, 'NEW')
        self.assertTrue(User.objects.get(username='ali').check_password('old-password-1'))
        self.assertNotEqual(self.client.get(reverse('readers_admin:reset_requests')).status_code, 200)
        self.assertNotEqual(self.client.get(reverse('readers_admin:temp_password', args=[self.reader.pk])).status_code, 200)

    def test_card_shows_the_right_button_for_each_role(self):
        card = self.client.get(reverse('readers_admin:detail', args=[self.reader.pk]))
        self.assertContains(card, reverse('readers_admin:reader_request_reset', args=[self.reader.pk]))
        self.assertNotContains(card, reverse('readers_admin:reader_reset_password', args=[self.reader.pk]))
        self.client.force_login(User.objects.get(username='adm'))
        card = self.client.get(reverse('readers_admin:detail', args=[self.reader.pk]))
        self.assertContains(card, reverse('readers_admin:reader_reset_password', args=[self.reader.pk]))

    def test_reader_cannot_reach_admin_endpoints(self):
        self.client.force_login(self.reader.user)
        self.client.post(reverse('readers_admin:reader_reset_password', args=[self.reader.pk]))
        self.assertTrue(User.objects.get(username='ali').check_password('old-password-1'))
