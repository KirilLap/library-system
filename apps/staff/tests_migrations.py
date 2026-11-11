from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BackfillActorNameMigrationTests(TransactionTestCase):
    """Перенос имён сотрудников в журнал должен работать на базе, где записи журнала уже есть."""

    before = [('staff', '0004_actionlog_actor_name')]
    after = [('staff', '0005_backfill_actor_name')]

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())      # возвращаем базу к последней миграции

    def test_old_entries_get_the_actor_name(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old_apps = executor.loader.project_state(self.before).apps
        User = old_apps.get_model('auth', 'User')
        ActionLog = old_apps.get_model('staff', 'ActionLog')
        named = User.objects.create(username='anna', first_name='Анна', last_name='Иванова')
        nameless = User.objects.create(username='only_login')
        ActionLog.objects.create(actor=named, action='действие 1')
        ActionLog.objects.create(actor=nameless, action='действие 2')
        ActionLog.objects.create(actor=None, action='действие системы')

        executor = MigrationExecutor(connection)
        executor.migrate(self.after)
        new_apps = executor.loader.project_state(self.after).apps
        names = {e.action: e.actor_name for e in new_apps.get_model('staff', 'ActionLog').objects.all()}
        self.assertEqual(names['действие 1'], 'Анна Иванова')
        self.assertEqual(names['действие 2'], 'only_login')
        self.assertEqual(names['действие системы'], '')
