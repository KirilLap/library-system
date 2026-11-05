from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Book, BookTitle


class CatalogPagingTests(TestCase):
    """Каталог: постраничный вывод, выбор числа книг на странице и сортировка."""

    @classmethod
    def setUpTestData(cls):
        for i in range(60):
            title = BookTitle.objects.create(title=f'Книга {i:02d}', author=f'Автор {60 - i:02d}', year=1950 + i)
            Book.objects.create(book_title=title, inventory_number=f'PAGE-{i}')

    def _get(self, **params):
        return self.client.get(reverse('catalog:index'), params)

    def test_default_page_size(self):
        response = self._get()
        self.assertEqual(len(response.context['books']), 24)
        self.assertEqual(response.context['total_count'], 60)

    def test_page_size_choice_and_second_page(self):
        response = self._get(per_page=12, page=2)
        self.assertEqual(len(response.context['books']), 12)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_invalid_page_size_falls_back_to_default(self):
        self.assertEqual(len(self._get(per_page=999).context['books']), 24)
        self.assertEqual(len(self._get(per_page='abc').context['books']), 24)

    def test_out_of_range_page_returns_last_page(self):
        response = self._get(per_page=48, page=99)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_sort_by_author(self):
        books = list(self._get(sort='author', per_page=12).context['books'])
        self.assertEqual(books[0].book_title.author, 'Автор 01')

    def test_sort_newest_first(self):
        books = list(self._get(sort='year_new', per_page=12).context['books'])
        self.assertEqual(books[0].book_title.year, 2009)

    def test_page_links_keep_filters(self):
        response = self._get(sort='author', per_page=12)
        self.assertContains(response, 'sort=author&amp;per_page=12&amp;page=2')
