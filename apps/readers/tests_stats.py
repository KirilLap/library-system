from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone, translation

from apps.readers.models import AgeGroupSettings, Reader
from apps.readers.stats import build_groups, parse_boundaries, reader_statistics
from apps.staff.models import StaffProfile


class BoundariesTests(SimpleTestCase):
    def setUp(self):
        translation.activate('ru')      # подписи групп проверяем по-русски, что бы ни включили другие тесты
        self.addCleanup(translation.deactivate)

    def test_parse_accepts_commas_spaces_and_sorts(self):
        self.assertEqual(parse_boundaries('31, 14 18;61'), [14, 18, 31, 61])

    def test_parse_rejects_bad_input(self):
        for bad in ('', 'abc', '14,14', '0', '200', '1,2,3,4,5,6,7,8,9,10'):
            with self.assertRaises(ValueError):
                parse_boundaries(bad)

    def test_groups_for_default_boundaries(self):
        labels = [g['label'] for g in build_groups([14, 18, 31, 61])]
        self.assertEqual(labels, ['до 14', '14–17', '18–30', '31–60', '61+'])

    def test_single_year_group_label(self):
        labels = [g['label'] for g in build_groups([18, 19])]
        self.assertEqual(labels, ['до 18', '18', '19+'])


def make_reader(username, gender, age):
    user = User.objects.create_user(username, password='x')
    year = timezone.now().year - age if age is not None else None
    return Reader.objects.create(user=user, gender=gender, birth_year=year)


class StatisticsCountTests(TestCase):
    def setUp(self):
        make_reader('a', 'M', 10)     # до 14
        make_reader('b', 'F', 13)     # до 14
        make_reader('c', 'F', 14)     # 14–17
        make_reader('d', 'M', 17)     # 14–17
        make_reader('e', 'M', 18)     # 18–30
        make_reader('f', 'F', 30)     # 18–30
        make_reader('g', 'F', 31)     # 31–60
        make_reader('h', 'M', 60)     # 31–60
        make_reader('i', 'M', 61)     # 61+
        make_reader('j', '', None)    # ничего не указано

    def test_counts_by_group_and_gender(self):
        stats = reader_statistics(Reader.objects.all(), [14, 18, 31, 61])
        self.assertEqual(stats['total'], 10)
        by_label = {r['label']: r for r in stats['age_rows']}
        self.assertEqual(by_label['до 14']['total'], 2)
        self.assertEqual((by_label['до 14']['male'], by_label['до 14']['female']), (1, 1))
        self.assertEqual(by_label['14–17']['total'], 2)
        self.assertEqual(by_label['18–30']['total'], 2)
        self.assertEqual(by_label['31–60']['total'], 2)
        self.assertEqual(by_label['61+']['total'], 1)
        self.assertEqual(by_label['Возраст не указан']['total'], 1)
        gender = {g['label']: g['count'] for g in stats['gender']}
        self.assertEqual(gender, {'Мужской': 5, 'Женский': 4, 'Не указан': 1})

    def test_custom_boundaries(self):
        stats = reader_statistics(Reader.objects.all(), [20, 50])
        by_label = {r['label']: r['total'] for r in stats['age_rows']}
        self.assertEqual(by_label['до 20'], 5)
        self.assertEqual(by_label['20–49'], 2)
        self.assertEqual(by_label['50+'], 2)


class StatsPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('adm', password='pw-adm-12345')
        StaffProfile.objects.create(user=self.admin, role=StaffProfile.ROLE_ADMIN)
        self.librarian = User.objects.create_user('lib', password='pw-lib-12345')
        StaffProfile.objects.create(user=self.librarian, role=StaffProfile.ROLE_LIBRARIAN)
        make_reader('r1', 'M', 20)

    def test_librarian_sees_stats_but_not_the_form(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse('readers_admin:stats'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['total'], 1)
        self.assertFalse(response.context['is_admin'])

    def test_admin_changes_boundaries(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('readers_admin:stats_settings'), {'boundaries': '12, 25'})
        self.assertEqual(AgeGroupSettings.get_solo().boundaries, '12,25')
        response = self.client.get(reverse('readers_admin:stats'))
        labels = [r['label'] for r in response.context['stats']['age_rows']]
        self.assertEqual(labels[:3], ['до 12', '12–24', '25+'])

    def test_invalid_boundaries_are_not_saved(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('readers_admin:stats_settings'), {'boundaries': 'abc'})
        self.assertEqual(AgeGroupSettings.get_solo().boundaries, '14,18,31,61')

    def test_librarian_cannot_change_boundaries(self):
        self.client.force_login(self.librarian)
        self.client.post(reverse('readers_admin:stats_settings'), {'boundaries': '12, 25'})
        self.assertEqual(AgeGroupSettings.get_solo().boundaries, '14,18,31,61')

    def test_stats_requires_staff(self):
        self.client.logout()
        self.assertNotEqual(self.client.get(reverse('readers_admin:stats')).status_code, 200)


# ───────────── Книги за период ─────────────
from datetime import timedelta

from apps.catalog.models import Book, BookTitle
from apps.locations.models import Location
from apps.readers.models import Loan
from apps.readers.stats import loan_statistics


def make_loan(reader, days_ago=0, returned=False):
    n = Book.objects.count()
    title = BookTitle.objects.create(title=f'Книга {n}', author='Автор')
    book = Book.objects.create(book_title=title, inventory_number=f'LN-{n}')
    location = Location.objects.first() or Location.objects.create(
        name='Пункт', type='MAHALLA', address='ул. Тест', is_active=True, is_public=True)
    loan = Loan.objects.create(book=book, location=location, reader=reader, is_returned=returned)
    if days_ago:
        Loan.objects.filter(pk=loan.pk).update(issued_at=timezone.now() - timedelta(days=days_ago))
    return loan


class LoanStatisticsTests(TestCase):
    def setUp(self):
        self.ann = make_reader('ann', 'F', 16)    # 14–17
        self.bob = make_reader('bob', 'M', 40)    # 31–60
        make_loan(self.ann); make_loan(self.ann, returned=True); make_loan(self.bob)
        make_loan(None)                           # выдача без читателя
        make_loan(self.bob, days_ago=100)         # вне 30 дней

    def _stats(self, loans=None, **kw):
        return loan_statistics(loans if loans is not None else Loan.objects.all(), [14, 18, 31, 61], **kw)

    def test_totals(self):
        stats = self._stats()
        self.assertEqual(stats['total'], 5)
        self.assertEqual(stats['by_readers'], 4)
        self.assertEqual(stats['anonymous'], 1)
        self.assertEqual(stats['readers_total'], 2)
        self.assertEqual(stats['average'], 2.0)

    def test_top_readers_sorted_and_not_returned(self):
        make_loan(self.bob)   # теперь у Боба 3 книги, у Анны 2
        top = self._stats()['top_readers']
        self.assertEqual([r['reader'].user.username for r in top], ['bob', 'ann'])
        by_name = {r['reader'].user.username: r for r in top}
        self.assertEqual(by_name['bob']['taken'], 3)
        self.assertEqual(by_name['ann']['taken'], 2)
        self.assertEqual(by_name['ann']['not_returned'], 1)

    def test_top_limit_reports_hidden_readers(self):
        stats = self._stats(top=1)
        self.assertEqual(len(stats['top_readers']), 1)
        self.assertEqual(stats['hidden_readers'], 1)

    def test_loans_by_age_and_gender(self):
        rows = {r['label']: r for r in self._stats()['age_rows']}
        self.assertEqual((rows['14–17']['female'], rows['14–17']['total']), (2, 2))
        self.assertEqual((rows['31–60']['male'], rows['31–60']['total']), (2, 2))


class LoanPeriodPageTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user('adm', password='pw-adm-12345')
        StaffProfile.objects.create(user=admin, role=StaffProfile.ROLE_ADMIN)
        self.client.force_login(admin)
        reader = make_reader('r', 'M', 20)
        make_loan(reader, days_ago=2)
        make_loan(reader, days_ago=10)
        make_loan(reader, days_ago=100)

    def _total(self, **params):
        response = self.client.get(reverse('readers_admin:stats'), params)
        self.assertEqual(response.status_code, 200)
        return response.context['loan_stats']['total']

    def test_default_period_is_30_days(self):
        self.assertEqual(self._total(), 2)

    def test_presets(self):
        self.assertEqual(self._total(days=7), 1)
        self.assertEqual(self._total(days=365), 3)
        self.assertEqual(self._total(days='all'), 3)

    def test_unknown_preset_falls_back_to_30_days(self):
        self.assertEqual(self._total(days='abc'), 2)

    def test_custom_dates(self):
        today = timezone.localdate()
        first = (today - timedelta(days=120)).isoformat()
        last = (today - timedelta(days=50)).isoformat()
        self.assertEqual(self._total(**{'from': first, 'to': last}), 1)

    def test_reversed_and_invalid_dates_do_not_break(self):
        today = timezone.localdate()
        self.assertEqual(self._total(**{'from': today.isoformat(),
                                        'to': (today - timedelta(days=30)).isoformat()}), 2)
        self.assertEqual(self._total(**{'from': 'garbage', 'to': 'oops'}), 2)
