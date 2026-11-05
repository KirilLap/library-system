"""Демо-данные для показа: вымышленные читатели и их выдачи книг.

    python manage.py seed_demo                  # 100 читателей, книги в 6 пунктах, выдачи
    python manage.py seed_demo --count 60
    python manage.py seed_demo --points 4       # книги только в 4 пунктах
    python manage.py seed_demo --activate       # при нехватке активных пунктов включить нужные
    python manage.py seed_demo --remove         # удалить все демо-данные и вернуть как было

Книги раскладываются по нескольким библиопунктам партиями (как при настоящей доставке),
в каждый пункт не меньше 5 книг, а выдаются читателям только те книги,
которые в этот момент находятся в пункте.

Имена и данные ВЫМЫШЛЕННЫЕ. С реального списка читателей взято только общее
распределение (доля мужчин и женщин, возрастные группы), поэтому статистика выглядит
правдоподобно, но настоящих людей в базе нет. Все созданные читатели помечены
в поле «Заметки» значением DEMO, войти под ними нельзя (пароль не задан).
"""
import json
import random
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Book
from apps.deliveries.models import DeliveryBatch, DeliveryItem
from apps.locations.models import Location, open_type_codes
from apps.readers.models import Loan, Reader, generate_card_id

DEMO_MARK = 'DEMO'

MALE_NAMES = ['Азиз', 'Бобур', 'Жасур', 'Дилшод', 'Сардор', 'Рустам', 'Акмал', 'Шохруз', 'Улугбек',
              'Фаррух', 'Тимур', 'Достон', 'Иброхим', 'Отабек', 'Нодир', 'Санжар', 'Анвар', 'Мансур',
              'Бекзод', 'Умид', 'Зафар', 'Хуршид', 'Алишер', 'Эльёр', 'Джахонгир']
FEMALE_NAMES = ['Дилноза', 'Зарина', 'Малика', 'Нилуфар', 'Мадина', 'Гулнора', 'Шахноза', 'Камола',
                'Феруза', 'Севара', 'Лола', 'Мохира', 'Нигора', 'Рухсора', 'Азиза', 'Умида', 'Зулайхо',
                'Барно', 'Юлдуз', 'Сабина', 'Ойдин', 'Хилола', 'Саида', 'Лайло', 'Гавхар']
SURNAMES = ['Каримов', 'Рахимов', 'Юсупов', 'Исмоилов', 'Абдуллаев', 'Хасанов', 'Назаров', 'Саидов',
            'Турсунов', 'Мирзаев', 'Усманов', 'Содиков', 'Ортиков', 'Холматов', 'Расулов', 'Эшонов',
            'Бекмуродов', 'Ахмедов', 'Ибрагимов', 'Норматов', 'Жураев', 'Холиков', 'Умаров', 'Салимов']

# Доли возрастных групп (по реальному списку; самые малые группы чуть увеличены,
# чтобы они были видны на демонстрации): до 14, 14–17, 18–30, 31–60, 61+
AGE_GROUPS = [
    ((6, 13), 0.02),
    ((14, 17), 0.22),
    ((18, 30), 0.62),
    ((31, 60), 0.12),
    ((61, 78), 0.02),
]
# Внутри группы чаще встречаются типичные возрасты читателей (учащиеся, студенты)
AGE_WEIGHTS = {17: 6, 16: 3, 15: 1, 18: 10, 19: 9, 20: 6, 21: 4, 22: 3, 23: 2}
FEMALE_SHARE = 0.62   # в реальном списке женщин около 62 %


def _state_path():
    return getattr(settings, 'DEMO_STATE_FILE', settings.BASE_DIR / '.demo_state.json')


def _pick_age(rng, low, high):
    ages = list(range(low, high + 1))
    return rng.choices(ages, weights=[AGE_WEIGHTS.get(a, 1) for a in ages])[0]


def _group_sizes(count):
    sizes = [int(round(count * share)) for _bounds, share in AGE_GROUPS]
    sizes[2] += count - sum(sizes)      # остаток отдаём самой большой группе
    return sizes


class Command(BaseCommand):
    help = 'Создаёт вымышленных читателей и выдачи книг для демонстрации статистики (или удаляет их).'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='Сколько читателей создать (по умолчанию 100)')
        parser.add_argument('--remove', action='store_true', help='Удалить все демо-данные')
        parser.add_argument('--seed', type=int, default=2026, help='Число для повторяемости результата')
        parser.add_argument('--share', type=int, default=70,
                            help='Какую долю книг (в %%) разложить по библиопунктам (по умолчанию 70)')
        parser.add_argument('--points', type=int, default=6,
                            help='В скольких библиопунктах разместить книги (по умолчанию 6, в каждом не меньше 5 книг)')
        parser.add_argument('--activate', '--activate-all', dest='activate', action='store_true',
                            help='Если активных пунктов не хватает, на время включить нужные (--remove вернёт как было)')

    def handle(self, *args, **options):
        if options['remove']:
            return self._remove()
        return self._create(options['count'], options['seed'], options['share'], options['points'], options['activate'])

    # ── удаление ────────────────────────────────────────────────
    @transaction.atomic
    def _remove(self):
        readers = Reader.objects.filter(notes=DEMO_MARK)
        loans = Loan.objects.filter(reader__in=readers)
        n_loans = loans.count()
        loans.delete()

        # Демо-партии: книги возвращаются в библиотеку, партии удаляются
        batches = DeliveryBatch.objects.filter(note=DEMO_MARK)
        book_ids = list(DeliveryItem.objects.filter(batch__in=batches).values_list('book_id', flat=True))
        n_batches = batches.count()
        Book.objects.filter(pk__in=book_ids).update(status='IN_LIBRARY')
        DeliveryItem.objects.filter(batch__in=batches).delete()
        batches.delete()

        user_ids = list(readers.values_list('user_id', flat=True))
        User.objects.filter(pk__in=user_ids).delete()

        # Библиопункты, включённые командой, возвращаются в прежнее состояние
        restored = 0
        path = _state_path()
        if path.exists():
            state = json.loads(path.read_text(encoding='utf-8'))
            for pk, (was_active, was_public) in state.get('activated', {}).items():
                restored += Location.objects.filter(pk=int(pk)).update(is_active=was_active, is_public=was_public)
            path.unlink()

        self.stdout.write(self.style.SUCCESS(
            f'Удалено: читателей {len(user_ids)}, выдач {n_loans}, партий {n_batches} '
            f'(книг возвращено в библиотеку: {len(book_ids)}), библиопунктов восстановлено: {restored}.'))

    # ── создание ────────────────────────────────────────────────
    @transaction.atomic
    def _create(self, count, seed, share, n_points, activate):
        if count < 1 or count > 1000:
            raise CommandError('Укажите количество от 1 до 1000.')
        if share < 1 or share > 100:
            raise CommandError('--share: укажите число от 1 до 100.')
        if n_points < 2 or n_points > 50:
            raise CommandError('--points: укажите число от 2 до 50.')
        if Reader.objects.filter(notes=DEMO_MARK).exists():
            raise CommandError('Демо-данные уже созданы. Сначала удалите их: python manage.py seed_demo --remove')
        if not Book.objects.exists():
            raise CommandError('В базе нет книг: сначала добавьте книги, иначе выдавать нечего.')

        rng = random.Random(seed)
        now = timezone.now()
        year = now.year

        # ── какие библиопункты берём: несколько, а не все ──
        open_codes = open_type_codes()
        active = list(Location.objects.filter(is_active=True).order_by('pk'))
        inactive = list(Location.objects.filter(is_active=False).order_by('pk')) if activate else []
        # примерно две трети — открытые пункты, остальные закрытые, чтобы были видны оба вида
        want_open = -(-n_points * 2 // 3)

        def pick(pool, how_many):
            return pool[:how_many]

        candidates = active + inactive          # сначала уже включённые
        opened = [p for p in candidates if p.type in open_codes]
        closed = [p for p in candidates if p.type not in open_codes]
        chosen = pick(opened, want_open) + pick(closed, n_points - min(want_open, len(opened)))
        chosen += [p for p in candidates if p not in chosen][:max(n_points - len(chosen), 0)]
        chosen = chosen[:n_points]
        if len(chosen) < 2:
            raise CommandError(
                f'Подходящих библиопунктов меньше двух (активных: {len(active)}). '
                'Включите нужные пункты в панели или запустите с --activate: команда на время '
                'включит недостающие, а --remove вернёт прежнее состояние.')

        # ── книги: минимум 5 в каждом выбранном пункте ──
        free_books = list(
            Book.objects.filter(status='IN_LIBRARY').exclude(delivery_items__is_returned=False)
            .exclude(loans__is_returned=False).distinct()
        )
        if len(free_books) < 10:
            raise CommandError('Свободных книг меньше 10: все уже находятся в библиопунктах или на руках.')
        rng.shuffle(free_books)
        total_placed = min(len(free_books), max(round(len(free_books) * share / 100), 5 * len(chosen)))
        usable_points = max(2, min(len(chosen), total_placed // 5))
        chosen = chosen[:usable_points]
        placed = free_books[:max(total_placed, 5 * len(chosen))]

        # включаем только выбранные пункты и запоминаем прежнее состояние
        state = {}
        for loc in chosen:
            if not (loc.is_active and loc.is_public):
                state[str(loc.pk)] = [loc.is_active, loc.is_public]
                Location.objects.filter(pk=loc.pk).update(is_active=True, is_public=True)
        if state:
            _state_path().write_text(json.dumps({'activated': state}), encoding='utf-8')
        points = chosen
        locations = [p for p in points if p.is_public or str(p.pk) in state]
        all_locations = points

        weights = [3 if p.type in open_codes else 2 for p in points]
        by_point = {p.pk: [] for p in points}
        queue = list(placed)
        for p in points:                         # сначала каждому по 5 книг
            for _ in range(5):
                by_point[p.pk].append(queue.pop())
        for book in queue:                       # остальные — с разным весом
            by_point[rng.choices(points, weights=weights)[0].pk].append(book)
        delivered = {}   # book.pk -> пункт, где книга лежит
        today = timezone.localdate()
        n_batches = 0
        for point in points:
            chunk = by_point[point.pk]
            delivery_date = today - timedelta(days=rng.randint(125, 150))
            batch = DeliveryBatch.objects.create(location=point, delivery_date=delivery_date, note=DEMO_MARK)
            DeliveryItem.objects.bulk_create([DeliveryItem(batch=batch, book=b) for b in chunk])
            Book.objects.filter(pk__in=[b.pk for b in chunk]).update(status='IN_DELIVERY')
            for b in chunk:
                delivered[b.pk] = point
            n_batches += 1
        books = [b for b in placed if b.pk in delivered]

        # ── читатели ──
        used_names = set()
        readers = []
        number = 0
        for (low, high), size in zip((b for b, _ in AGE_GROUPS), _group_sizes(count)):
            for _ in range(size):
                number += 1
                female = rng.random() < FEMALE_SHARE
                for _attempt in range(50):
                    first = rng.choice(FEMALE_NAMES if female else MALE_NAMES)
                    surname = rng.choice(SURNAMES) + ('а' if female else '')
                    if (first, surname) not in used_names:
                        break
                used_names.add((first, surname))
                user = User(username=f'demo{number:03d}', first_name=first, last_name=surname)
                user.set_unusable_password()
                user.save()
                readers.append(Reader.objects.create(
                    user=user,
                    card_id=generate_card_id(),
                    gender=Reader.GENDER_FEMALE if female else Reader.GENDER_MALE,
                    birth_year=year - _pick_age(rng, low, high),
                    nearest_location=rng.choice(locations) if locations and rng.random() < 0.75 else None,
                    notes=DEMO_MARK,
                ))

        # ── выдачи: только книги, которые сейчас в пункте; один экземпляр не бывает у двух читателей сразу ──
        busy = {}      # book.pk -> список (с какого, по какое) занятых промежутков
        loan_counts = [0, 1, 2, 3, 4, 6, 9, 14]
        loan_weights = [14, 20, 20, 15, 11, 10, 7, 3]
        n_loans = n_open = n_overdue = 0
        for reader in readers:
            for _ in range(rng.choices(loan_counts, weights=loan_weights)[0]):
                days_ago = int(rng.triangular(0, 120, 12))
                issued = now - timedelta(days=days_ago, hours=rng.randint(0, 6), minutes=rng.randint(0, 59))
                # на руках: свежие выдачи и немного давних, которые уже просрочены
                overdue_from = settings.LOAN_PERIOD_DAYS + 3
                keep_open = ((days_ago <= 20 and rng.random() < 0.35)
                             or (overdue_from <= days_ago <= overdue_from + 50 and rng.random() < 0.12))
                end = None if keep_open else min(issued + timedelta(days=rng.randint(3, 21)), now)
                horizon = end or (now + timedelta(days=3650))
                for _attempt in range(40):
                    book = rng.choice(books)
                    if all(horizon <= s0 or issued >= e0 for s0, e0 in busy.get(book.pk, [])):
                        break
                else:
                    continue
                busy.setdefault(book.pk, []).append((issued, horizon))
                loan = Loan.objects.create(book=book, location=delivered[book.pk], reader=reader,
                                           is_returned=not keep_open)
                fields = {'issued_at': issued}
                if keep_open:
                    n_open += 1
                    n_overdue += days_ago > settings.LOAN_PERIOD_DAYS
                else:
                    fields['returned_at'] = end
                Loan.objects.filter(pk=loan.pk).update(**fields)
                n_loans += 1

        self.stdout.write(self.style.SUCCESS(
            f'Создано читателей: {len(readers)}; книг разложено по библиопунктам: {len(books)} '
            f'(партий: {n_batches}); выдач: {n_loans} (на руках сейчас: {n_open}, из них просрочено: {n_overdue}).'))
        self.stdout.write('Все данные вымышленные и помечены DEMO. Удалить: python manage.py seed_demo --remove')
