from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone, translation
from openpyxl import load_workbook

from apps.catalog.models import Book, BookTitle
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan
from apps.readers.tests_stats import make_reader
from apps.staff.models import StaffProfile
from apps.staff.stats_points import collect_points_stats


def staff(username, role):
    user = User.objects.create_user(username, password='pw-123456')
    StaffProfile.objects.create(user=user, role=role)
    return user


def point(name, kind='MAHALLA', active=True):
    return Location.objects.create(name=name, type=kind, address='x', is_active=active, is_public=active)


def book(n):
    title = BookTitle.objects.create(title=f'Книга {n}', author='А')
    return Book.objects.create(book_title=title, inventory_number=f'PT-{n}')


def batch(location, days_ago, books):
    obj = DeliveryBatch.objects.create(location=location, delivery_date=timezone.localdate() - timedelta(days=days_ago))
    for b in books:
        DeliveryItem.objects.create(batch=obj, book=b)
        Book.objects.filter(pk=b.pk).update(status='IN_DELIVERY')
    return obj


def loan(reader, location, book_obj, days_ago, returned=False):
    obj = Loan.objects.create(book=book_obj, location=location, reader=reader, is_returned=returned)
    Loan.objects.filter(pk=obj.pk).update(issued_at=timezone.now() - timedelta(days=days_ago))
    return obj


class PointsStatsTests(TestCase):
    def setUp(self):
        staff('adm', StaffProfile.ROLE_ADMIN)
        self.librarian = staff('lib', StaffProfile.ROLE_LIBRARIAN)
        self.a, self.b, self.idle = point('Пункт А'), point('Пункт Б', 'SCHOOL'), point('Пустой пункт')
        self.off = point('Выключенный', active=False)
        books = [book(i) for i in range(10)]
        batch(self.a, 5, books[:4])             # свежая партия: 4 книги
        batch(self.a, 100, books[4:6])          # старая партия: 2 книги
        batch(self.b, 10, books[6:9])           # 3 книги
        r1, r2 = make_reader('r1', 'F', 20), make_reader('r2', 'M', 30)
        loan(r1, self.a, books[0], 2)
        loan(r1, self.a, books[1], 3, returned=True)
        loan(r2, self.a, books[2], 4)
        loan(r1, self.b, books[6], 6)
        loan(r2, self.a, books[4], 90)          # вне 30 дней
        loan(r2, self.a, books[5], 60)          # не возвращена и просрочена
        r1.nearest_location = self.a
        r1.save()
        self.client.force_login(self.librarian)

    def _stats(self, days=30):
        today = timezone.localdate()
        return collect_points_stats(today - timedelta(days=days - 1), today)

    def _row(self, data, location):
        return next(r for r in data['rows'] if r['location'] == location)

    def test_batches_and_books_by_period_and_total(self):
        row = self._row(self._stats(30), self.a)
        self.assertEqual((row['batches_period'], row['batches_all']), (1, 2))
        self.assertEqual((row['books_period'], row['books_all']), (4, 6))
        self.assertEqual(row['in_point'], 6)

    def test_loans_and_distinct_readers(self):
        row = self._row(self._stats(30), self.a)
        self.assertEqual((row['loans'], row['readers']), (3, 2))                   # r1 дважды, r2 один раз
        wide = self._row(self._stats(365), self.a)
        self.assertEqual(wide['loans'], 5)

    def test_open_overdue_and_nearest(self):
        row = self._row(self._stats(30), self.a)
        self.assertEqual(row['open'], 4)           # на руках: выдачи 2, 4, 60 и 90 дней назад
        self.assertEqual(row['overdue'], 2)        # просрочены только 60 и 90 дней (срок 30)
        self.assertEqual(row['nearest'], 1)

    def test_totals_count_readers_without_repeats(self):
        totals = self._stats(30)['totals']
        self.assertEqual(totals['readers'], 2)                  # r1 брал в двух пунктах, но один человек
        self.assertEqual(totals['loans'], 4)
        self.assertEqual((totals['batches_all'], totals['books_all']), (3, 9))

    def test_inactive_empty_point_is_hidden_active_empty_shown(self):
        names = [r['location'].name for r in self._stats()['rows']]
        self.assertIn('Пустой пункт', names)
        self.assertNotIn('Выключенный', names)

    def test_inactive_point_with_activity_is_shown(self):
        batch(self.off, 3, [book(50)])
        names = [r['location'].name for r in self._stats()['rows']]
        self.assertIn('Выключенный', names)

    def test_sorted_by_loans(self):
        rows = self._stats()['rows']
        self.assertEqual(rows[0]['location'], self.a)

    # ── страница и Excel ──
    def test_page_and_tabs(self):
        response = self.client.get(reverse('staff:stats_points'), {'days': 30})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Пункт А')
        self.assertContains(response, reverse('staff:stats_points_export'))
        for url in ('staff:stats', 'readers_admin:stats', 'staff:stats_points'):
            self.assertContains(response, reverse(url))                   # вкладки

    def test_free_period_and_all_time(self):
        today = timezone.localdate()
        wide = self.client.get(reverse('staff:stats_points'), {'days': 'all'})
        self.assertEqual(wide.context['totals']['loans'], 6)
        custom = self.client.get(reverse('staff:stats_points'), {
            'from': (today - timedelta(days=120)).isoformat(), 'to': (today - timedelta(days=50)).isoformat()})
        self.assertEqual(custom.context['totals']['loans'], 2)

    def test_books_page_links_to_points_tab(self):
        self.assertContains(self.client.get(reverse('staff:stats')), reverse('staff:stats_points'))

    def test_export_workbook(self):
        response = self.client.get(reverse('staff:stats_points_export'), {'days': 'all'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('points-stats-', response['Content-Disposition'])
        wb = load_workbook(BytesIO(response.content))
        self.assertEqual(wb.sheetnames, ['Сводка', 'По библиопунктам'])
        rows = list(wb['По библиопунктам'].iter_rows(values_only=True))
        self.assertEqual(rows[0][0], 'Библиопункт')
        names = [r[0] for r in rows[1:]]
        self.assertEqual(names[-1], 'Итого')
        self.assertIn('Пункт А', names)
        first = next(r for r in rows if r[0] == 'Пункт А')
        self.assertEqual(first[3], 2)             # партий всего
        self.assertEqual(first[5], 6)             # книг завезено всего

    def test_export_has_no_reader_names(self):
        response = self.client.get(reverse('staff:stats_points_export'), {'days': 'all'})
        wb = load_workbook(BytesIO(response.content))
        text = ' '.join(str(c) for ws in wb for row in ws.iter_rows(values_only=True) for c in row if c is not None)
        self.assertNotIn('r1', text)
        self.assertNotIn('r2', text)

    def test_requires_staff(self):
        self.client.logout()
        for name in ('staff:stats_points', 'staff:stats_points_export'):
            self.assertNotEqual(self.client.get(reverse(name)).status_code, 200)

    def test_uzbek_page_and_file(self):
        self.addCleanup(translation.activate, 'ru')      # язык после запроса остаётся включённым, возвращаем русский
        self.client.cookies['django_language'] = 'uz'
        self.assertEqual(self.client.get(reverse('staff:stats_points')).status_code, 200)
        wb = load_workbook(BytesIO(self.client.get(reverse('staff:stats_points_export')).content))
        self.assertEqual(wb.sheetnames[0], 'Xulosa')
