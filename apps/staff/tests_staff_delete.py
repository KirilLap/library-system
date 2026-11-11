from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.readers.models import Reader
from apps.staff.models import ActionLog, StaffProfile


def staff(username, role, first='', last=''):
    user = User.objects.create_user(username, password='pw-123456', first_name=first, last_name=last)
    return StaffProfile.objects.create(user=user, role=role)


class StaffDeleteTests(TestCase):
    """Администратор может удалить учётную запись сотрудника совсем, а не только заблокировать."""

    def setUp(self):
        self.admin = staff('adm', StaffProfile.ROLE_ADMIN, 'Главный', 'Админов')
        self.lib = staff('lib', StaffProfile.ROLE_LIBRARIAN, 'Анна', 'Библиотекарева')
        self.client.force_login(self.admin.user)

    def _delete(self, profile):
        return self.client.post(reverse('staff:delete', args=[profile.pk]))

    def test_admin_deletes_librarian(self):
        response = self._delete(self.lib)
        self.assertRedirects(response, reverse('staff:list'))
        self.assertFalse(User.objects.filter(username='lib').exists())
        self.assertFalse(StaffProfile.objects.filter(pk=self.lib.pk).exists())

    def test_can_delete_blocked_staff_too(self):
        StaffProfile.objects.filter(pk=self.lib.pk).update(is_active=False)
        self._delete(self.lib)
        self.assertFalse(User.objects.filter(username='lib').exists())

    def test_deletion_is_logged_and_history_keeps_the_name(self):
        ActionLog.log(self.lib.user, 'Принял возврат книги')
        self._delete(self.lib)
        entry = ActionLog.objects.get(action='Принял возврат книги')
        self.assertIsNone(entry.actor)                                    # учётной записи уже нет
        self.assertEqual(entry.actor_name, 'Анна Библиотекарева')         # но имя в истории сохранилось
        self.assertIn('Анна Библиотекарева', str(entry))
        last = ActionLog.objects.latest('pk')
        self.assertEqual(last.actor, self.admin.user)
        self.assertIn('Удалил учётную запись', last.action)
        page = self.client.get(reverse('staff:action_log'))
        self.assertContains(page, 'Анна Библиотекарева')
        self.assertContains(page, 'учётная запись удалена')

    def test_cannot_delete_yourself(self):
        self._delete(self.admin)
        self.assertTrue(User.objects.filter(username='adm').exists())

    def test_can_delete_another_admin(self):
        other = staff('adm2', StaffProfile.ROLE_ADMIN)
        self._delete(other)
        self.assertFalse(User.objects.filter(username='adm2').exists())
        self.assertTrue(User.objects.filter(username='adm').exists())

    def test_librarian_cannot_delete(self):
        self.client.force_login(self.lib.user)
        victim = staff('lib2', StaffProfile.ROLE_LIBRARIAN)
        self._delete(victim)
        self.assertTrue(User.objects.filter(username='lib2').exists())

    def test_anonymous_cannot_delete(self):
        self.client.logout()
        self._delete(self.lib)
        self.assertTrue(User.objects.filter(username='lib').exists())

    def test_get_not_allowed(self):
        response = self.client.get(reverse('staff:delete', args=[self.lib.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(User.objects.filter(username='lib').exists())

    def test_account_that_is_also_a_reader_is_not_deleted(self):
        Reader.objects.create(user=self.lib.user)
        self._delete(self.lib)
        self.assertTrue(User.objects.filter(username='lib').exists())

    def test_delete_button_in_list_but_not_for_yourself(self):
        page = self.client.get(reverse('staff:list'))
        self.assertContains(page, reverse('staff:delete', args=[self.lib.pk]))
        self.assertNotContains(page, reverse('staff:delete', args=[self.admin.pk]))

    def test_new_log_entries_store_the_name(self):
        ActionLog.log(self.admin.user, 'Что-то сделал')
        self.assertEqual(ActionLog.objects.latest('pk').actor_name, 'Главный Админов')
