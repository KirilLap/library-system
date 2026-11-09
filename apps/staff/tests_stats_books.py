from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.catalog.models import Book, BookTitle
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan
from apps.readers.tests_stats import make_loan, make_reader
from apps.staff.models import StaffProfile
from apps.staff.stats_books import collect_stats


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


class BooksStatsTests(TestCase):
    def setUp(self):
        staff('adm', StaffProfile.ROLE_ADMIN)          # без администратора сайт просит первичную настройку
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.client.force_login(self.librarian)
        reader = make_reader('r', 'M', 20)
        self.l1 = make_loan(reader, days_ago=3)
        make_loan(reader, days_ago=5, returned=True)
        Loan.objects.filter(is_returned=True).update(returned_at=timezone.now())
        make_loan(reader, days_ago=40)                       # вне 30 дней, просрочена
        BookTitle.objects.filter(pk=self.l1.book.book_title.pk).update(title='=ПОДДЕЛКА()')   # название, похожее на формулу
        point = Location.objects.first()
        batch = DeliveryBatch.objects.create(location=point, note='x')
        DeliveryItem.objects.create(batch=batch, book=self.l1.book)
        Book.objects.filter(pk=self.l1.book.pk).update(status='IN_DELIVERY')

    def test_collect_stats_numbers(self):
        today = timezone.localdate()
        data = collect_stats(today - timedelta(days=29), today)
        self.assertEqual(data['period_stats']['loans_issued'], 2)
        self.assertEqual(data['period_stats']['loans_returned'], 1)
        self.assertEqual(data['current']['on_hands'], 2)
        self.assertEqual(data['current']['overdue'], 1)
        self.assertEqual(data['current']['books_in_points'], 1)
        self.assertEqual(sum(data['weekly_counts']), 2)

    def test_page_still_works_and_has_tabs_and_excel_button(self):
        response = self.client.get(reverse('staff:stats'), {'days': 90})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['period_stats']['loans_issued'], 3)
        self.assertContains(response, reverse('readers_admin:stats'))       # вкладка «Читатели»
        self.assertContains(response, reverse('staff:stats_export'))

    def test_reader_stats_pages_sit_under_the_statistics_tab(self):
        for name in ('readers_admin:stats', 'readers_admin:stats_readers', 'readers_admin:stats_unreturned'):
            response = self.client.get(reverse(name))
            self.assertContains(response, reverse('staff:stats'))            # вкладка «Книги»

    def test_export_workbook(self):
        response = self.client.get(reverse('staff:stats_export'), {'days': 90})
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertIn('books-stats-', response['Content-Disposition'])
        wb = load_workbook(BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ['Сводка', 'Выдачи по неделям', 'Жанры', 'Популярные книги', 'Библиопункты'])
        values = {r[0]: r[1] for r in wb['Сводка'].iter_rows(min_row=3, values_only=True) if r[0]}
        self.assertEqual(values['Выдано книг'], 3)
        self.assertEqual(values['На руках сейчас'], 2)
        self.assertEqual(values['Из них просрочено'], 1)
        self.assertEqual(values['В библиопунктах'], 1)

    def test_export_has_no_reader_names_and_formula_stays_text(self):
        response = self.client.get(reverse('staff:stats_export'), {'days': 90})
        wb = load_workbook(BytesIO(response.content))
        cell = [c for row in wb['Популярные книги'].iter_rows() for c in row if str(c.value).startswith('=ПОДДЕЛКА')]
        self.assertTrue(cell)
        self.assertEqual(cell[0].data_type, 's')
        everything = ' '.join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        self.assertNotIn('Каримов', everything)
        self.assertNotIn('demo', everything)
        self.assertNotIn('ID читателя', everything)        # нет колонок с данными читателей

    def test_export_requires_staff(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse('staff:stats_export')).status_code, 200)

    def test_export_in_uzbek(self):
        self.client.cookies['django_language'] = 'uz'
        response = self.client.get(reverse('staff:stats_export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(load_workbook(BytesIO(response.content)).sheetnames[0], 'Xulosa')


class BooksFreePeriodTests(TestCase):
    """На странице книг, как и у читателей, можно выбрать свой период."""

    def setUp(self):
        staff('adm', StaffProfile.ROLE_ADMIN)
        self.client.force_login(staff('lib', StaffProfile.ROLE_LIBRARIAN))
        reader = make_reader('r', 'M', 20)
        make_loan(reader, days_ago=2)
        make_loan(reader, days_ago=10)
        make_loan(reader, days_ago=100)

    def _issued(self, **params):
        response = self.client.get(reverse('staff:stats'), params)
        self.assertEqual(response.status_code, 200)
        return response.context['period_stats']['loans_issued']

    def test_presets_and_all_time(self):
        self.assertEqual(self._issued(), 2)                       # по умолчанию 30 дней
        self.assertEqual(self._issued(days=7), 1)
        self.assertEqual(self._issued(days=365), 3)
        self.assertEqual(self._issued(days='all'), 3)

    def test_custom_dates(self):
        today = timezone.localdate()
        self.assertEqual(self._issued(**{'from': (today - timedelta(days=120)).isoformat(),
                                         'to': (today - timedelta(days=50)).isoformat()}), 1)

    def test_bad_dates_do_not_break(self):
        today = timezone.localdate()
        self.assertEqual(self._issued(**{'from': 'abc', 'to': 'zzz'}), 2)
        self.assertEqual(self._issued(**{'from': today.isoformat(),
                                         'to': (today - timedelta(days=30)).isoformat()}), 2)   # даты поменяются местами

    def test_page_has_date_inputs_and_export_keeps_period(self):
        response = self.client.get(reverse('staff:stats'), {'days': 90})
        self.assertContains(response, 'name="from"')
        self.assertContains(response, 'name="to"')
        self.assertContains(response, reverse('staff:stats_export') + '?days=90')

    def test_export_uses_custom_period(self):
        today = timezone.localdate()
        params = {'from': (today - timedelta(days=120)).isoformat(), 'to': (today - timedelta(days=50)).isoformat()}
        response = self.client.get(reverse('staff:stats_export'), params)
        wb = load_workbook(BytesIO(response.content))
        values = {r[0]: r[1] for r in wb['Сводка'].iter_rows(min_row=3, values_only=True) if r[0]}
        self.assertEqual(values['Выдано книг'], 1)
        self.assertIn('–', values['Период'])
