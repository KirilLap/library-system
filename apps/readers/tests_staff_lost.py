from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Book
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan
from apps.readers.stats import open_loans
from apps.readers.tests_stats import make_loan, make_reader
from apps.staff.models import ActionLog, StaffProfile
from apps.staff.stats_books import collect_stats


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


class LostBookTests(TestCase):
    """Утерянная книга остаётся в базе, но скрыта из каталога и не ставится в пункты."""

    def setUp(self):
        staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.reader = make_reader('ann', 'F', 22)
        self.loan = make_loan(self.reader, days_ago=45)
        self.book = self.loan.book
        # книга стоит в библиопункте, как при настоящей выдаче
        self.batch = DeliveryBatch.objects.create(location=self.loan.location, note='x')
        self.item = DeliveryItem.objects.create(batch=self.batch, book=self.book)
        Book.objects.filter(pk=self.book.pk).update(status='IN_DELIVERY')
        self.client.force_login(self.librarian)

    def _lost(self, **data):
        return self.client.post(reverse('readers_admin:loan_lost', args=[self.loan.pk]), data)

    def test_marking_lost_closes_loan_and_hides_book(self):
        response = self._lost()
        self.assertRedirects(response, reverse('readers_admin:stats_unreturned'))
        self.loan.refresh_from_db()
        self.book.refresh_from_db()
        self.item.refresh_from_db()
        self.assertTrue(self.loan.is_returned)
        self.assertTrue(self.loan.is_lost)
        self.assertIsNotNone(self.loan.returned_at)
        self.assertEqual(self.book.status, 'LOST')
        self.assertTrue(self.item.is_returned)               # больше не числится в пункте
        self.assertIsNone(self.book.current_location)
        self.assertTrue(Book.objects.filter(pk=self.book.pk).exists())     # из базы не удалена

    def test_lost_loan_is_not_open_or_overdue(self):
        self._lost()
        self.assertEqual(open_loans().count(), 0)
        self.assertEqual(open_loans(only_overdue=True).count(), 0)

    def test_action_is_logged(self):
        self._lost()
        entry = ActionLog.objects.latest('pk')
        self.assertEqual(entry.actor, self.librarian)
        self.assertIn('утерянную', entry.action)
        self.assertIn(self.book.inventory_number, entry.action)

    def test_lost_book_is_hidden_from_public_catalog(self):
        self.client.logout()
        before = self.client.get(reverse('catalog:index'))
        self.assertContains(before, self.book.title)
        self.client.force_login(self.librarian)
        self._lost()
        self.client.logout()
        after = self.client.get(reverse('catalog:index'))
        self.assertNotContains(after, self.book.title)
        self.assertEqual(self.client.get(reverse('catalog:detail', args=[self.book.pk])).status_code, 404)

    def test_lost_book_cannot_be_put_into_a_point(self):
        self._lost()
        new_batch = DeliveryBatch.objects.create(location=Location.objects.first(), note='новая')
        self.client.post(reverse('deliveries_admin:detail', args=[new_batch.pk]),
                         {'inventory_number': self.book.inventory_number})
        self.assertFalse(DeliveryItem.objects.filter(batch=new_batch, book=self.book).exists())
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, 'LOST')

    def test_returning_old_batch_does_not_resurrect_lost_book(self):
        self._lost()
        self.batch.mark_returned()
        self.book.refresh_from_db()
        self.assertEqual(self.book.status, 'LOST')

    def test_reader_cannot_take_a_lost_book(self):
        self._lost()
        other = make_reader('bob', 'M', 30)
        self.client.force_login(other.user)
        response = self.client.post(reverse('main:take_book'), {'inventory_number': self.book.inventory_number})
        self.assertContains(response, 'утерянной')
        self.assertEqual(Loan.objects.filter(reader=other).count(), 0)

    def test_statistics_count_lost_separately(self):
        today = timezone.localdate()
        make_loan(self.reader, days_ago=2, returned=True)
        Loan.objects.filter(is_returned=True).update(returned_at=timezone.now())
        before = collect_stats(None, today)['period_stats']
        self.assertEqual((before['loans_returned'], before['loans_lost']), (1, 0))
        self._lost()
        after = collect_stats(None, today)['period_stats']
        self.assertEqual((after['loans_returned'], after['loans_lost']), (1, 1))     # утеря не считается возвратом
        self.assertEqual(collect_stats(None, today)['current']['books_lost'], 1)

    def test_reader_card_shows_lost_badge_and_no_buttons(self):
        self._lost()
        response = self.client.get(reverse('readers_admin:detail', args=[self.reader.pk]))
        self.assertContains(response, 'Утеряна')
        self.assertNotContains(response, reverse('readers_admin:loan_lost', args=[self.loan.pk]))

    def test_buttons_shown_for_open_loans(self):
        url = reverse('readers_admin:loan_lost', args=[self.loan.pk])
        self.assertContains(self.client.get(reverse('readers_admin:stats_unreturned')), url)
        self.assertContains(self.client.get(reverse('readers_admin:detail', args=[self.reader.pk])), url)

    def test_get_forbidden_repeat_404_and_unsafe_next_ignored(self):
        self.assertEqual(self.client.get(reverse('readers_admin:loan_lost', args=[self.loan.pk])).status_code, 405)
        self.assertRedirects(self._lost(next='https://evil.example/'), reverse('readers_admin:stats_unreturned'))
        self.assertEqual(self._lost().status_code, 404)

    def test_only_staff_can_mark_lost(self):
        self.client.logout()
        self._lost()
        self.client.force_login(self.reader.user)
        self._lost()
        self.loan.refresh_from_db()
        self.assertFalse(self.loan.is_lost)
        self.assertEqual(Book.objects.get(pk=self.book.pk).status, 'IN_DELIVERY')
