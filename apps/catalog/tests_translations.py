from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.catalog.models import Genre, Language
from apps.locations.models import LocationType
from apps.staff.models import StaffProfile


class LocalizedNamesTests(TestCase):
    """Узбекское название жанра, языка и типа вводится сразу в форме."""

    def setUp(self):
        user = User.objects.create_user('adm', password='pw-adm-12345')
        StaffProfile.objects.create(user=user, role=StaffProfile.ROLE_ADMIN)
        self.client.force_login(user)

    def test_genre_created_with_uzbek_name(self):
        self.client.post(reverse('catalog_admin:genre_list'),
                         {'code': 'SCIENCE', 'name': 'Научная', 'name_uz': 'Ilmiy'})
        genre = Genre.objects.get(code='SCIENCE')
        self.assertEqual(genre.name_uz, 'Ilmiy')
        with translation.override('uz'):
            self.assertEqual(genre.localized_name(), 'Ilmiy')
        with translation.override('ru'):
            self.assertEqual(genre.localized_name(), 'Научная')

    def test_uzbek_name_is_optional(self):
        self.client.post(reverse('catalog_admin:genre_list'), {'code': 'HIST', 'name': 'Редкая тема'})
        genre = Genre.objects.get(code='HIST')
        with translation.override('uz'):
            self.assertEqual(genre.localized_name(), 'Редкая тема')

    def test_language_created_with_uzbek_name(self):
        self.client.post(reverse('catalog_admin:language_list'),
                         {'code': 'KK', 'name': 'Казахский', 'name_uz': 'Qozoq'})
        lang = Language.objects.get(code='KK')
        with translation.override('uz'):
            self.assertEqual(lang.localized_name(), 'Qozoq')
        self.assertEqual(lang.uz_name(), 'Qozoq')

    def test_location_type_created_and_edited_with_uzbek_name(self):
        self.client.post(reverse('locations_admin:type_list'),
                         {'code': 'KIDS', 'name': 'Детский клуб', 'name_uz': "Bolalar klubi"})
        lt = LocationType.objects.get(code='KIDS')
        with translation.override('uz'):
            self.assertEqual(lt.localized_name(), 'Bolalar klubi')
        self.client.post(reverse('locations_admin:type_update', args=[lt.pk]),
                         {'code': 'KIDS', 'name': 'Детский клуб', 'name_uz': "Bolalar markazi"})
        lt.refresh_from_db()
        self.assertEqual(lt.name_uz, 'Bolalar markazi')

    def test_existing_names_keep_translation_from_locale_files(self):
        genre = Genre.objects.create(code='POETRY2', name='Поэзия')
        with translation.override('uz'):
            self.assertNotEqual(genre.localized_name(), 'Поэзия')

    def test_management_pages_open(self):
        for name in ('catalog_admin:genre_list', 'catalog_admin:language_list', 'locations_admin:type_list'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)


class OtherLastTests(TestCase):
    """«Другое» всегда последнее в списках жанров и языков."""

    def test_genre_other_is_last(self):
        Genre.objects.get_or_create(code='OTHER', defaults={'name': 'Аааа-другое'})
        Genre.objects.create(code='ZZZ', name='Яяя последний по алфавиту')
        codes = list(Genre.objects.values_list('code', flat=True))
        self.assertEqual(codes[-1], 'OTHER')

    def test_language_other_is_last(self):
        Language.objects.get_or_create(code='OTHER', defaults={'name': 'Аааа-другой'})
        Language.objects.create(code='ZZZ', name='Яяя последний по алфавиту')
        codes = list(Language.objects.values_list('code', flat=True))
        self.assertEqual(codes[-1], 'OTHER')
