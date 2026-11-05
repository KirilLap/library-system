import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.catalog.models import Book, BookTitle
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location
from apps.readers.models import Loan, Reader
from apps.readers.stats import loan_statistics, reader_statistics


STATE = Path(tempfile.gettempdir()) / 'demo_state_test.json'


@override_settings(DEMO_STATE_FILE=STATE)
class SeedDemoTests(TestCase):
    def setUp(self):
        STATE.unlink(missing_ok=True)
        for i, kind in enumerate(['MAHALLA', 'MAHALLA', 'SCHOOL', 'KINDERGARTEN']):
            Location.objects.create(name=f'Пункт {i}', type=kind, address='x', is_active=True, is_public=True)
        for i in range(40):
            title = BookTitle.objects.create(title=f'Книга {i}', author='Автор', year=2000 + i % 20)
            Book.objects.create(book_title=title, inventory_number=f'DEMO-{i}')

    def _run(self, *args):
        out = StringIO()
        call_command('seed_demo', *args, stdout=out)
        return out.getvalue()

    def test_creates_readers_with_realistic_groups(self):
        self._run()
        readers = Reader.objects.filter(notes='DEMO')
        self.assertEqual(readers.count(), 100)
        stats = reader_statistics(readers, [14, 18, 31, 61])
        sizes = [r['total'] for r in stats['age_rows'][:5]]
        self.assertEqual(sizes, [2, 22, 62, 12, 2])
        self.assertEqual(stats['age_rows'][5]['total'], 0)            # возраст есть у всех
        male, female = stats['gender'][0]['count'], stats['gender'][1]['count']
        self.assertEqual(male + female, 100)
        self.assertGreater(female, male)                              # женщин больше, как в реальном списке

    def test_demo_users_cannot_log_in_and_have_unique_ids(self):
        self._run('--count', '30')
        users = User.objects.filter(username__startswith='demo')
        self.assertEqual(users.count(), 30)
        self.assertTrue(all(not u.has_usable_password() for u in users))
        ids = list(Reader.objects.values_list('card_id', flat=True))
        self.assertEqual(len(set(ids)), len(ids))

    def test_creates_loans_for_statistics(self):
        self._run()
        loans = Loan.objects.filter(reader__notes='DEMO')
        self.assertGreater(loans.count(), 100)
        stats = loan_statistics(loans, [14, 18, 31, 61])
        self.assertGreater(stats['readers_total'], 50)
        self.assertTrue(stats['top_readers'])
        # возвращённые выдачи имеют дату возврата не раньше даты выдачи
        for loan in loans.filter(is_returned=True):
            self.assertIsNotNone(loan.returned_at)
            self.assertGreaterEqual(loan.returned_at, loan.issued_at)
        # есть и просроченные, чтобы на показе страница «Просрочки» не была пустой
        from apps.readers.stats import open_loans
        self.assertTrue(open_loans(only_overdue=True).filter(reader__notes='DEMO').exists())
        # на одну книгу не больше одной незакрытой выдачи
        open_books = list(loans.filter(is_returned=False).values_list('book_id', flat=True))
        self.assertEqual(len(open_books), len(set(open_books)))

    def test_is_repeatable_with_same_seed(self):
        self._run()
        first = sorted(Reader.objects.values_list('user__last_name', 'birth_year'))
        self._run('--remove')
        self._run()
        self.assertEqual(sorted(Reader.objects.values_list('user__last_name', 'birth_year')), first)

    def test_refuses_to_run_twice(self):
        self._run('--count', '10')
        with self.assertRaises(CommandError):
            self._run('--count', '10')

    def test_remove_deletes_only_demo_data(self):
        real_user = User.objects.create_user('real_reader', password='x')
        real = Reader.objects.create(user=real_user, notes='настоящий читатель')
        self._run()
        self._run('--remove')
        self.assertEqual(Reader.objects.filter(notes='DEMO').count(), 0)
        self.assertEqual(Loan.objects.filter(reader__notes='DEMO').count(), 0)
        self.assertEqual(User.objects.filter(username__startswith='demo').count(), 0)
        self.assertTrue(Reader.objects.filter(pk=real.pk).exists())

    def test_needs_books(self):
        Book.objects.all().delete()
        with self.assertRaises(CommandError):
            self._run()


@override_settings(DEMO_STATE_FILE=STATE)
class DemoDistributionTests(TestCase):
    """Книги раскладываются по библиопунктам, а выдачи согласованы с этим."""

    def setUp(self):
        STATE.unlink(missing_ok=True)
        for i, kind in enumerate(['MAHALLA', 'MAHALLA', 'SCHOOL', 'KINDERGARTEN']):
            Location.objects.create(name=f'Пункт {i}', type=kind, address='x', is_active=True, is_public=True)
        for i in range(50):
            title = BookTitle.objects.create(title=f'Книга {i}', author='Автор')
            Book.objects.create(book_title=title, inventory_number=f'DST-{i}')

    def _run(self, *args):
        call_command('seed_demo', *args, stdout=StringIO())

    def test_books_spread_over_points_in_batches(self):
        self._run()
        batches = DeliveryBatch.objects.filter(note='DEMO')
        self.assertEqual(batches.count(), 4)                       # доступно 4 пункта из 6 запрошенных
        for batch in batches:
            self.assertGreaterEqual(batch.items.count(), 5)        # в каждом пункте не меньше 5 книг
        placed = Book.objects.filter(status='IN_DELIVERY')
        self.assertEqual(placed.count(), 35)                       # 70 % из 50
        self.assertEqual(Book.objects.filter(status='IN_LIBRARY').count(), 15)
        for book in placed:
            self.assertIsNotNone(book.current_location)

    def test_loans_come_from_the_point_where_the_book_is(self):
        self._run()
        loans = Loan.objects.filter(reader__notes='DEMO')
        self.assertTrue(loans.exists())
        for loan in loans:
            self.assertEqual(loan.location, loan.book.current_location)
            self.assertEqual(loan.book.status, 'IN_DELIVERY')

    def test_a_book_is_never_with_two_readers_at_once(self):
        self._run()
        by_book = {}
        for loan in Loan.objects.filter(reader__notes='DEMO'):
            end = loan.returned_at if loan.is_returned else None
            by_book.setdefault(loan.book_id, []).append((loan.issued_at, end))
        for spans in by_book.values():
            spans.sort(key=lambda s: s[0])
            for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
                self.assertIsNotNone(e1)          # предыдущая выдача закрыта
                self.assertLessEqual(e1, s2)      # и закрыта до следующей

    def test_points_option_limits_how_many_points_get_books(self):
        self._run('--points', '2')
        batches = DeliveryBatch.objects.filter(note='DEMO')
        self.assertEqual(batches.count(), 2)
        for batch in batches:
            self.assertGreaterEqual(batch.items.count(), 5)

    def test_few_active_points_need_the_flag_and_it_is_reversible(self):
        Location.objects.filter(name__in=['Пункт 1', 'Пункт 2', 'Пункт 3']).update(is_active=False)
        with self.assertRaises(CommandError):
            self._run()
        self._run('--activate')
        self.assertEqual(DeliveryBatch.objects.filter(note='DEMO').count(), 4)
        self.assertEqual(Location.objects.filter(is_active=True).count(), 4)
        self._run('--remove')
        self.assertEqual(sorted(Location.objects.filter(is_active=True).values_list('name', flat=True)), ['Пункт 0'])

    def test_only_chosen_points_are_activated(self):
        for i in range(6):
            Location.objects.create(name=f'Лишний {i}', type='MAHALLA', address='x', is_active=False, is_public=False)
        Location.objects.filter(name__startswith='Пункт').update(is_active=False)
        self._run('--activate', '--points', '3')
        self.assertEqual(DeliveryBatch.objects.filter(note='DEMO').count(), 3)
        self.assertEqual(Location.objects.filter(is_active=True).count(), 3)   # остальные пункты не тронуты

    def test_remove_returns_books_to_library_and_keeps_real_batches(self):
        real_book = Book.objects.get(inventory_number='DST-0')
        real_batch = DeliveryBatch.objects.create(location=Location.objects.first(), note='настоящая партия')
        DeliveryItem.objects.create(batch=real_batch, book=real_book)
        Book.objects.filter(pk=real_book.pk).update(status='IN_DELIVERY')
        self._run()
        self._run('--remove')
        self.assertEqual(DeliveryBatch.objects.filter(note='DEMO').count(), 0)
        self.assertEqual(Book.objects.filter(status='IN_DELIVERY').count(), 1)     # только настоящая
        self.assertEqual(Book.objects.get(pk=real_book.pk).status, 'IN_DELIVERY')
        self.assertTrue(DeliveryBatch.objects.filter(pk=real_batch.pk).exists())
        self.assertEqual(Loan.objects.count(), 0)
