from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.locations.models import Location, MapSettings
from apps.readers.forms import ReaderRegistrationForm
from apps.staff.models import StaffProfile


def make_point(name, type_code, **kw):
    return Location.objects.create(
        name=name, type=type_code, address='ул. Тестовая', latitude=39.65, longitude=66.96,
        is_active=True, is_public=True, **kw)


class MapModesTests(TestCase):
    """Администратор выбирает, как показывать закрытые библиопункты на публичной карте."""

    def setUp(self):
        self.open_point = make_point('Открытая махалля', 'MAHALLA')
        self.closed_point = make_point('Закрытая школа', 'SCHOOL')

    def _set_mode(self, mode):
        obj = MapSettings.get_solo()
        obj.closed_points_mode = mode
        obj.save()

    def _map(self):
        return self.client.get(reverse('locations_public:map'))

    def test_default_mode_marks_closed_points(self):
        response = self._map()
        self.assertEqual(MapSettings.get_solo().closed_points_mode, MapSettings.MODE_MARK)
        self.assertContains(response, 'Закрытая школа')
        self.assertContains(response, 'closed: true')
        self.assertContains(response, 'only-open')

    def test_separate_mode_moves_closed_to_list(self):
        self._set_mode(MapSettings.MODE_SEPARATE)
        response = self._map()
        self.assertContains(response, 'Закрытая школа')       # в списке под картой
        self.assertNotContains(response, 'closed: true')       # но не маркером
        self.assertContains(response, 'Закрытые библиопункты')

    def test_hide_mode_hides_closed_points(self):
        self._set_mode(MapSettings.MODE_HIDE)
        response = self._map()
        self.assertContains(response, 'Открытая махалля')
        self.assertNotContains(response, 'Закрытая школа')

    def test_closed_point_page_opens_and_shows_badge_in_every_mode(self):
        self._set_mode(MapSettings.MODE_HIDE)
        response = self.client.get(reverse('locations_public:point', args=[self.closed_point.slug]))
        self.assertContains(response, 'Закрытый')


class MapSettingsPageTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('adm', password='pw-adm-12345')
        StaffProfile.objects.create(user=self.admin, role=StaffProfile.ROLE_ADMIN)
        self.librarian = User.objects.create_user('lib', password='pw-lib-12345')
        StaffProfile.objects.create(user=self.librarian, role=StaffProfile.ROLE_LIBRARIAN)

    def test_admin_can_change_mode(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('locations_admin:map_settings'), {'closed_points_mode': 'HIDE'})
        self.assertRedirects(response, reverse('locations_admin:map_settings'))
        self.assertEqual(MapSettings.get_solo().closed_points_mode, 'HIDE')

    def test_invalid_mode_rejected(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('locations_admin:map_settings'), {'closed_points_mode': 'WHATEVER'})
        self.assertEqual(MapSettings.get_solo().closed_points_mode, 'MARK')

    def test_librarian_cannot_change_mode(self):
        self.client.force_login(self.librarian)
        self.client.post(reverse('locations_admin:map_settings'), {'closed_points_mode': 'HIDE'})
        self.assertEqual(MapSettings.get_solo().closed_points_mode, 'MARK')


class NearestChoiceTests(TestCase):
    """Какие пункты читатель может выбрать как ближайший."""

    def setUp(self):
        self.open_point = make_point('Открытая махалля', 'MAHALLA')
        self.closed_point = make_point('Закрытая школа', 'SCHOOL')

    def _labels(self):
        form = ReaderRegistrationForm()
        field = form.fields['nearest_location']
        return [field.label_from_instance(loc) for loc in field.queryset]

    def test_closed_points_marked_with_lock(self):
        labels = self._labels()
        self.assertIn('Открытая махалля', labels)
        self.assertIn('🔒 Закрытая школа', labels)

    def test_closed_points_not_offered_in_hide_mode(self):
        obj = MapSettings.get_solo()
        obj.closed_points_mode = MapSettings.MODE_HIDE
        obj.save()
        self.assertEqual(self._labels(), ['Открытая махалля'])
