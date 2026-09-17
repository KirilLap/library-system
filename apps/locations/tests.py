"""Тесты удаления библиопункта."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.deliveries.models import DeliveryBatch
from apps.staff.models import StaffProfile
from .models import Location, LocationType

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_location(name='Тестовая точка', type='MAHALLA', **kwargs):
    return Location.objects.create(name=name, type=type, address='Адрес', **kwargs)


def make_librarian(username='librarian'):
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
    return user


def make_non_admin_librarian(username='plain_librarian'):
    """Обычный библиотекарь (не админ) — нужен хотя бы один ADMIN отдельно
    для прохождения staff_required."""
    make_librarian('bootstrap-admin')
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_LIBRARIAN, is_active=True)
    return user


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LocationDeleteTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.client.force_login(self.librarian)

    def test_delete_location_without_history(self):
        location = make_location()
        response = self.client.post(reverse('locations_admin:delete', args=[location.pk]))
        self.assertRedirects(response, reverse('locations_admin:index'))
        self.assertFalse(Location.objects.filter(pk=location.pk).exists())

    def test_cannot_delete_location_with_delivery_history(self):
        location = make_location()
        DeliveryBatch.objects.create(location=location)

        response = self.client.get(reverse('locations_admin:delete', args=[location.pk]))
        self.assertContains(response, 'Нельзя удалить')

        response = self.client.post(reverse('locations_admin:delete', args=[location.pk]))
        self.assertRedirects(response, reverse('locations_admin:detail', args=[location.pk]))
        self.assertTrue(Location.objects.filter(pk=location.pk).exists())


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LocationTypeCrudTests(TestCase):
    def setUp(self):
        self.admin = make_librarian()
        self.client.force_login(self.admin)

    def test_seeded_types_exist(self):
        codes = set(LocationType.objects.values_list('code', flat=True))
        self.assertEqual(
            codes, {'MAHALLA', 'SCHOOL', 'KINDERGARTEN', 'ORGANIZATION', 'OTHER'},
        )
        mahalla = LocationType.objects.get(code='MAHALLA')
        self.assertTrue(mahalla.is_open)
        kindergarten = LocationType.objects.get(code='KINDERGARTEN')
        self.assertFalse(kindergarten.is_open)

    def test_create_type(self):
        response = self.client.post(reverse('locations_admin:type_list'), {
            'code': 'clinic', 'name': 'Поликлиника', 'is_open': '',
        })
        self.assertRedirects(response, reverse('locations_admin:type_list'))
        lt = LocationType.objects.get(code='CLINIC')  # clean_code uppercases
        self.assertEqual(lt.name, 'Поликлиника')
        self.assertFalse(lt.is_open)

    def test_cannot_create_duplicate_code(self):
        response = self.client.post(reverse('locations_admin:type_list'), {
            'code': 'MAHALLA', 'name': 'Дубликат', 'is_open': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LocationType.objects.filter(code='MAHALLA').count(), 1)

    def test_update_type(self):
        lt = LocationType.objects.get(code='OTHER')
        response = self.client.post(reverse('locations_admin:type_update', args=[lt.pk]), {
            'code': 'OTHER', 'name': 'Прочее', 'is_open': 'on',
        })
        self.assertRedirects(response, reverse('locations_admin:type_list'))
        lt.refresh_from_db()
        self.assertEqual(lt.name, 'Прочее')
        self.assertTrue(lt.is_open)

    def test_delete_unused_type(self):
        lt = LocationType.objects.create(code='TEMP', name='Временный')
        response = self.client.post(reverse('locations_admin:type_delete', args=[lt.pk]))
        self.assertRedirects(response, reverse('locations_admin:type_list'))
        self.assertFalse(LocationType.objects.filter(pk=lt.pk).exists())

    def test_cannot_delete_type_in_use(self):
        lt = LocationType.objects.get(code='SCHOOL')
        make_location(name='Школа №1', type='SCHOOL')
        response = self.client.post(reverse('locations_admin:type_delete', args=[lt.pk]))
        self.assertRedirects(response, reverse('locations_admin:type_list'))
        self.assertTrue(LocationType.objects.filter(pk=lt.pk).exists())

    def test_non_admin_cannot_manage_types(self):
        librarian = make_non_admin_librarian()
        self.client.force_login(librarian)
        response = self.client.get(reverse('locations_admin:type_list'))
        self.assertNotEqual(response.status_code, 200)

    def test_new_type_usable_in_location_form(self):
        LocationType.objects.create(code='CLINIC', name='Поликлиника')
        response = self.client.post(reverse('locations_admin:create'), {
            'name': 'Тестовая поликлиника',
            'type': 'CLINIC',
            'address': 'Адрес',
            'is_active': 'on',
            'is_public': 'on',
        })
        self.assertRedirects(
            response,
            reverse('locations_admin:detail', args=[Location.objects.get(name='Тестовая поликлиника').pk]),
        )
        loc = Location.objects.get(name='Тестовая поликлиника')
        self.assertEqual(loc.type, 'CLINIC')
        self.assertEqual(loc.get_type_display(), 'Поликлиника')


@override_settings(MEDIA_ROOT=_MEDIA_ROOT)
class LocationIsOpenTests(TestCase):
    def test_is_open_follows_type_setting(self):
        mahalla = make_location(name='Махалля', type='MAHALLA')
        self.assertTrue(mahalla.is_open)

        school = make_location(name='Школа', type='SCHOOL')
        self.assertFalse(school.is_open)

    def test_is_open_reflects_type_edit(self):
        loc = make_location(name='Точка', type='OTHER')
        self.assertFalse(loc.is_open)
        LocationType.objects.filter(code='OTHER').update(is_open=True)
        loc.refresh_from_db()
        self.assertTrue(loc.is_open)


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
