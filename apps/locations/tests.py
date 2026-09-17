"""Тесты удаления библиопункта."""
import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.deliveries.models import DeliveryBatch
from apps.staff.models import StaffProfile
from .models import Location

_MEDIA_ROOT = tempfile.mkdtemp(prefix='library_test_media_')


def make_location(name='Тестовая точка', **kwargs):
    return Location.objects.create(name=name, type='MAHALLA', address='Адрес', **kwargs)


def make_librarian(username='librarian'):
    user = User.objects.create_user(username=username, password='pass12345')
    StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN, is_active=True)
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


def tearDownModule():
    shutil.rmtree(_MEDIA_ROOT, ignore_errors=True)
