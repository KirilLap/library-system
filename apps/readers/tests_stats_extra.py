from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.readers.models import Loan, Reader
from apps.readers.stats import open_loans
from apps.readers.tests_stats import make_loan, make_reader
from apps.staff.models import StaffProfile


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


@override_settings(LOAN_PERIOD_DAYS=30)
class StatsListsTests(TestCase):
    def setUp(self):
        self.admin = staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.client.force_login(self.admin)

    def _many_readers(self, n):
        for i in range(n):
            reader = make_reader(f'rd{i:02d}', 'F', 20)
            for _ in range(i % 3 + 1):
                make_loan(reader, days_ago=1)

    # ── первые 10 и полный список ──
    def test_stats_page_shows_only_first_ten_readers(self):
        self._many_readers(15)
        response = self.client.get(reverse('readers_admin:stats'))
        stats = response.context['loan_stats']
        self.assertEqual(len(stats['top_readers']), 10)
        self.assertEqual(stats['readers_total'], 15)
        self.assertEqual(stats['hidden_readers'], 5)
        self.assertContains(response, reverse('readers_admin:stats_readers'))

    def test_full_list_has_everyone_and_pages(self):
        self._many_readers(60)
        response = self.client.get(reverse('readers_admin:stats_readers'))
        self.assertEqual(response.context['total_readers'], 60)
        self.assertEqual(len(response.context['rows']), 50)
        page2 = self.client.get(reverse('readers_admin:stats_readers'), {'page': 2})
        self.assertEqual(len(page2.context['rows']), 10)

    def test_full_list_search_by_name_and_id(self):
        self._many_readers(5)
        target = Reader.objects.get(user__username='rd03')
        by_name = self.client.get(reverse('readers_admin:stats_readers'), {'q': 'rd03'})
        self.assertEqual(by_name.context['total_readers'], 1)
        target.card_id = '1234567890'
        target.save()
        by_id = self.client.get(reverse('readers_admin:stats_readers'), {'q': '1234567890'})
        self.assertEqual(by_id.context['total_readers'], 1)

    def test_full_list_respects_period(self):
        reader = make_reader('old', 'M', 30)
        make_loan(reader, days_ago=200)
        self.assertEqual(self.client.get(reverse('readers_admin:stats_readers')).context['total_readers'], 0)
        self.assertEqual(self.client.get(reverse('readers_admin:stats_readers'), {'days': 'all'}).context['total_readers'], 1)

    # ── не возвращённые и просрочки ──
    def test_unreturned_and_overdue_pages(self):
        reader = make_reader('slow', 'M', 25)
        make_loan(reader, days_ago=40)                     # просрочена
        make_loan(reader, days_ago=5)                      # на руках, срок не вышел
        make_loan(reader, days_ago=3, returned=True)       # возвращена: не показывается
        # open_loans() смотрит на is_returned, поэтому «возвращённая» не попадает в списки
        everything = self.client.get(reverse('readers_admin:stats_unreturned'))
        self.assertEqual(len(everything.context['loans']), 2)
        overdue = self.client.get(reverse('readers_admin:stats_unreturned'), {'only': 'overdue'})
        self.assertEqual(len(overdue.context['loans']), 1)
        self.assertTrue(overdue.context['only_overdue'])
        stats = self.client.get(reverse('readers_admin:stats')).context
        self.assertEqual((stats['unreturned_count'], stats['overdue_count']), (2, 1))

    def test_overdue_filter_matches_loan_property(self):
        reader = make_reader('edge', 'F', 22)
        for hours in (-1, 0, 1, 24, 24 * 29, 24 * 30 - 1, 24 * 30 + 1, 24 * 31 + 1, 24 * 45):
            loan = make_loan(reader)
            Loan.objects.filter(pk=loan.pk).update(issued_at=timezone.now() - timedelta(hours=hours))
        by_property = {loan.pk for loan in open_loans() if loan.is_overdue}
        by_filter = set(open_loans(only_overdue=True).values_list('pk', flat=True))
        self.assertEqual(by_property, by_filter)
        self.assertTrue(by_filter)

    def test_pages_require_staff(self):
        self.client.logout()
        for name in ('stats_readers', 'stats_unreturned', 'stats_export'):
            self.assertNotEqual(self.client.get(reverse(f'readers_admin:{name}')).status_code, 200)


class StatsExportTests(TestCase):
    def setUp(self):
        self.admin = staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        reader = make_reader('anna', 'F', 20)
        reader.user.first_name = '=HYPERLINK("http://evil.example","Нажми")'   # попытка подсунуть формулу
        reader.user.last_name = 'Анна'
        reader.user.save()
        make_loan(reader, days_ago=40)
        make_loan(reader, days_ago=2, returned=True)

    def _workbook(self, user, **params):
        self.client.force_login(user)
        response = self.client.get(reverse('readers_admin:stats_export'), params)
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertIn('.xlsx', response['Content-Disposition'])
        return load_workbook(BytesIO(response.content))

    def test_admin_gets_all_sheets_with_readers(self):
        wb = self._workbook(self.admin, days='all')
        self.assertEqual(wb.sheetnames, ['Сводка', 'Читатели по возрасту', 'Книги по возрасту',
                                         'Читатели и книги', 'Не возвращены'])
        rows = list(wb['Читатели и книги'].iter_rows(values_only=True))
        self.assertEqual(rows[0][0], 'Читатель')
        self.assertEqual(rows[1][4:6], (2, 1))                      # взято 2, не возвращено 1
        unreturned = list(wb['Не возвращены'].iter_rows(values_only=True))
        self.assertEqual(len(unreturned), 2)                        # заголовок + одна не возвращённая
        self.assertEqual(unreturned[1][-1], 'Да')                   # просрочена

    def test_librarian_file_has_no_reader_lists(self):
        wb = self._workbook(self.librarian, days='all')
        self.assertEqual(wb.sheetnames, ['Сводка', 'Читатели по возрасту', 'Книги по возрасту'])
        text = ' '.join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        self.assertNotIn('Анна', text)

    def test_summary_numbers_match_the_page(self):
        wb = self._workbook(self.admin, days='all')
        values = {row[0]: row[1] for row in wb['Сводка'].iter_rows(min_row=3, values_only=True) if row[0]}
        self.assertEqual(values['Всего читателей'], 1)
        self.assertEqual(values['Взято книг за период'], 2)
        self.assertEqual(values['Не возвращено сейчас'], 1)
        self.assertEqual(values['Из них просрочено'], 1)

    def test_formula_in_name_stays_text(self):
        wb = self._workbook(self.admin, days='all')
        cell = wb['Читатели и книги']['A2']
        self.assertEqual(cell.data_type, 's')
        self.assertTrue(str(cell.value).startswith('=HYPERLINK'))

    def test_period_is_applied(self):
        wb = self._workbook(self.admin, days='7')
        values = {row[0]: row[1] for row in wb['Сводка'].iter_rows(min_row=3, values_only=True) if row[0]}
        self.assertEqual(values['Взято книг за период'], 1)         # только выдача 2-дневной давности
