from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.readers.models import Loan, LoanSettings, get_loan_period
from apps.readers.stats import open_loans
from apps.readers.tests_stats import make_loan, make_reader
from apps.staff.models import StaffProfile


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


@override_settings(LOAN_PERIOD_DAYS=30)
class LoanPeriodTests(TestCase):
    def setUp(self):
        self.admin = staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.reader = make_reader('slow', 'M', 25)
        self.loan = make_loan(self.reader, days_ago=40)

    def _set(self, enabled, days=30):
        obj = LoanSettings.get_solo()
        obj.limit_enabled, obj.period_days = enabled, days
        obj.save()

    # ── срок по умолчанию и свой ──
    def test_default_uses_settings_value(self):
        self.assertEqual(get_loan_period(), 30)
        loan = Loan.objects.get(pk=self.loan.pk)         # свежие данные из базы (issued_at меняли запросом)
        self.assertEqual((loan.is_overdue, loan.overdue_days), (True, 10))

    def test_custom_period_changes_overdue(self):
        self._set(True, 60)
        self.assertEqual(get_loan_period(), 60)
        loan = Loan.objects.get(pk=self.loan.pk)
        self.assertEqual((loan.is_overdue, loan.overdue_days), (False, 0))
        self.assertEqual(open_loans(only_overdue=True).count(), 0)
        self._set(True, 7)
        self.assertEqual(Loan.objects.get(pk=self.loan.pk).overdue_days, 33)
        self.assertEqual(open_loans(only_overdue=True).count(), 1)

    def test_period_can_be_switched_off(self):
        self._set(False, 30)
        self.assertIsNone(get_loan_period())
        loan = Loan.objects.get(pk=self.loan.pk)
        self.assertEqual((loan.is_overdue, loan.overdue_days), (False, 0))
        self.assertEqual(open_loans(only_overdue=True).count(), 0)
        self.assertEqual(open_loans().count(), 1)                 # книга всё равно на руках
        self._set(True, 30)                                        # включили обратно: прежнее значение
        self.assertTrue(Loan.objects.get(pk=self.loan.pk).is_overdue)

    def test_overdue_days_zero_for_returned_loan(self):
        Loan.objects.filter(pk=self.loan.pk).update(is_returned=True, returned_at=timezone.now())
        self.assertEqual(Loan.objects.get(pk=self.loan.pk).overdue_days, 0)

    # ── страница настроек ──
    def test_admin_saves_period(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('readers_admin:loan_settings'),
                                    {'limit_enabled': 'on', 'period_days': '45'})
        self.assertRedirects(response, reverse('readers_admin:loan_settings'))
        self.assertEqual((LoanSettings.get_solo().limit_enabled, get_loan_period()), (True, 45))

    def test_admin_switches_off_limit(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('readers_admin:loan_settings'), {'period_days': '30'})   # галочка не отмечена
        self.assertIsNone(get_loan_period())

    def test_invalid_values_rejected(self):
        self.client.force_login(self.admin)
        for bad in ('0', '400', 'abc', ''):
            self.client.post(reverse('readers_admin:loan_settings'), {'limit_enabled': 'on', 'period_days': bad})
            self.assertEqual(get_loan_period(), 30, bad)

    def test_librarian_cannot_change(self):
        self.client.force_login(self.librarian)
        self.client.post(reverse('readers_admin:loan_settings'), {'limit_enabled': 'on', 'period_days': '99'})
        self.assertEqual(get_loan_period(), 30)
        self.assertNotEqual(self.client.get(reverse('readers_admin:loan_settings')).status_code, 200)

    def test_settings_page_and_buttons(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('readers_admin:loan_settings')).status_code, 200)
        self.assertContains(self.client.get(reverse('readers_admin:index')), reverse('readers_admin:loan_settings'))
        self.client.force_login(self.librarian)
        self.assertNotContains(self.client.get(reverse('readers_admin:index')), reverse('readers_admin:loan_settings'))

    # ── тексты и счётчики ──
    def test_badge_shows_overdue_days(self):
        self.client.force_login(self.librarian)
        page = self.client.get(reverse('readers_admin:stats_unreturned'))
        self.assertContains(page, 'просрочено дней: 10')
        self.assertNotContains(page, 'просрочка')

    def test_pages_when_limit_is_off(self):
        self._set(False)
        self.client.force_login(self.librarian)
        stats = self.client.get(reverse('readers_admin:stats'))
        self.assertEqual(stats.context['overdue_count'], 0)
        self.assertContains(stats, 'срок не ограничен')
        page = self.client.get(reverse('readers_admin:stats_unreturned'), {'only': 'overdue'})
        self.assertContains(page, 'просрочек нет')
        self.assertEqual(len(page.context['loans']), 0)
        dash = self.client.get(reverse('staff:dashboard'))
        self.assertEqual(dash.context['stats']['loans_overdue'], 0)

    def test_dashboard_uses_the_same_overdue_rule(self):
        self.client.force_login(self.librarian)
        dash = self.client.get(reverse('staff:dashboard'))
        self.assertEqual(dash.context['stats']['loans_overdue'], 1)
        self.assertContains(dash, 'просрочено дней: 10')

    def test_reader_cabinet_and_card_show_overdue_days(self):
        self.client.force_login(self.reader.user)
        self.assertContains(self.client.get(reverse('main:my')), 'просрочено дней: 10')
        self.client.force_login(self.librarian)
        self.assertContains(self.client.get(reverse('readers_admin:detail', args=[self.reader.pk])), 'просрочено дней: 10')

    def test_excel_shows_period_and_overdue_days(self):
        self.client.force_login(self.admin)
        wb = load_workbook(BytesIO(self.client.get(reverse('readers_admin:stats_export'), {'days': 'all'}).content))
        summary = {r[0]: r[1] for r in wb['Сводка'].iter_rows(min_row=3, values_only=True) if r[0]}
        self.assertEqual(summary['Срок возврата, дней'], 30)
        rows = list(wb['Не возвращены'].iter_rows(values_only=True))
        self.assertEqual(rows[0][-1], 'Просрочено дней')
        self.assertEqual(rows[1][-1], 10)
        self._set(False)
        wb = load_workbook(BytesIO(self.client.get(reverse('readers_admin:stats_export'), {'days': 'all'}).content))
        summary = {r[0]: r[1] for r in wb['Сводка'].iter_rows(min_row=3, values_only=True) if r[0]}
        self.assertEqual(summary['Срок возврата, дней'], 'без ограничения')

    def test_queries_per_list_page_do_not_grow_with_loans(self):
        for _ in range(8):
            make_loan(self.reader, days_ago=50)
        self.client.force_login(self.librarian)
        from django.db import connection
        from django.test.utils import CaptureQueriesContext
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse('readers_admin:stats_unreturned'))
        Loan.objects.filter(reader=self.reader).exclude(pk=self.loan.pk).delete()
        with CaptureQueriesContext(connection) as one:
            self.client.get(reverse('readers_admin:stats_unreturned'))
        self.assertLessEqual(len(many) - len(one), 3)             # срок читается один раз за запрос
