from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.readers.models import Loan
from apps.readers.tests_stats import make_loan, make_reader
from apps.staff.models import ActionLog, StaffProfile


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


class StaffReturnTests(TestCase):
    """Сотрудник принимает возврат за читателя, в том числе просроченной книги."""

    def setUp(self):
        staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.reader = make_reader('slow', 'F', 21)
        self.loan = make_loan(self.reader, days_ago=45)          # просрочена
        self.client.force_login(self.librarian)

    def _return(self, pk=None, **data):
        return self.client.post(reverse('readers_admin:loan_return', args=[pk or self.loan.pk]), data)

    def test_librarian_returns_overdue_book(self):
        response = self._return()
        self.assertRedirects(response, reverse('readers_admin:stats_unreturned'))
        self.loan.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertIsNotNone(self.loan.returned_at)
        self.assertFalse(self.loan.is_overdue)

    def test_action_is_logged(self):
        self._return()
        entry = ActionLog.objects.latest('pk')
        self.assertEqual(entry.actor, self.librarian)
        self.assertIn('Принял возврат', entry.action)
        self.assertIn(self.loan.book.inventory_number, entry.action)

    def test_overdue_counter_drops(self):
        before = self.client.get(reverse('readers_admin:stats')).context['overdue_count']
        self._return()
        after = self.client.get(reverse('readers_admin:stats')).context['overdue_count']
        self.assertEqual((before, after), (1, 0))

    def test_returns_to_the_page_it_came_from(self):
        target = reverse('readers_admin:detail', args=[self.reader.pk])
        self.assertRedirects(self._return(next=target), target)

    def test_unsafe_next_is_ignored(self):
        for bad in ('https://evil.example/', '//evil.example/', '/my/', 'javascript:alert(1)'):
            loan = make_loan(self.reader, days_ago=50)
            response = self._return(pk=loan.pk, next=bad)
            self.assertRedirects(response, reverse('readers_admin:stats_unreturned'))

    def test_get_is_not_allowed(self):
        response = self.client.get(reverse('readers_admin:loan_return', args=[self.loan.pk]))
        self.assertEqual(response.status_code, 405)
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_returned)

    def test_already_returned_loan_gives_404(self):
        self._return()
        self.assertEqual(self._return().status_code, 404)

    def test_anonymous_and_plain_readers_cannot_return(self):
        self.client.logout()
        self._return()
        self.client.force_login(self.reader.user)
        self._return()
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_returned)

    def test_buttons_are_shown_for_open_loans(self):
        url = reverse('readers_admin:loan_return', args=[self.loan.pk])
        self.assertContains(self.client.get(reverse('readers_admin:stats_unreturned')), url)
        self.assertContains(self.client.get(reverse('readers_admin:detail', args=[self.reader.pk])), url)

    def test_button_disappears_after_return(self):
        self._return()
        url = reverse('readers_admin:loan_return', args=[self.loan.pk])
        self.assertNotContains(self.client.get(reverse('readers_admin:detail', args=[self.reader.pk])), url)
