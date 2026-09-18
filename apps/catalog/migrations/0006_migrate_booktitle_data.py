from django.db import migrations


def migrate_data(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    BookTitle = apps.get_model('catalog', 'BookTitle')

    titles_by_key = {}
    for book in Book.objects.order_by('pk'):
        key = (book.title, book.author, book.year, book.publisher)
        book_title = titles_by_key.get(key)
        if book_title is None:
            book_title = BookTitle.objects.create(
                title=book.title,
                author=book.author,
                year=book.year,
                publisher=book.publisher,
                genre=book.genre,
                language=book.language,
                description=book.description,
                isbn=book.isbn,
                marc_data=book.marc_data,
                cover=book.cover,
            )
            titles_by_key[key] = book_title
        book.book_title = book_title
        book.save(update_fields=['book_title'])


def reverse_migrate_data(apps, schema_editor):
    Book = apps.get_model('catalog', 'Book')
    Book.objects.update(book_title=None)
    apps.get_model('catalog', 'BookTitle').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_add_booktitle'),
    ]

    operations = [
        migrations.RunPython(migrate_data, reverse_migrate_data),
    ]
