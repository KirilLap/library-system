from django.db import migrations, models


def populate_genres_languages(apps, schema_editor):
    Genre = apps.get_model('catalog', 'Genre')
    Language = apps.get_model('catalog', 'Language')

    genres = [
        ('FICTION',     'Художественная'),
        ('CHILDREN',    'Детская'),
        ('EDUCATIONAL', 'Учебная'),
        ('POETRY',      'Поэзия'),
        ('NONFICTION',  'Документальная'),
        ('OTHER',       'Другое'),
    ]
    languages = [
        ('RU',    'Русский'),
        ('UZ',    'Узбекский'),
        ('EN',    'Английский'),
        ('OTHER', 'Другой'),
    ]

    for code, name in genres:
        Genre.objects.get_or_create(code=code, defaults={'name': name})
    for code, name in languages:
        Language.objects.get_or_create(code=code, defaults={'name': name})


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_book_cover'),
    ]

    operations = [
        migrations.CreateModel(
            name='Genre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=30, unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=100, verbose_name='Название')),
            ],
            options={
                'verbose_name': 'Жанр',
                'verbose_name_plural': 'Жанры',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='Language',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=20, unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=100, verbose_name='Название')),
            ],
            options={
                'verbose_name': 'Язык',
                'verbose_name_plural': 'Языки',
                'ordering': ['name'],
            },
        ),
        migrations.AlterField(
            model_name='book',
            name='genre',
            field=models.CharField(default='OTHER', max_length=30, verbose_name='Жанр'),
        ),
        migrations.AlterField(
            model_name='book',
            name='language',
            field=models.CharField(default='RU', max_length=20, verbose_name='Язык'),
        ),
        migrations.RunPython(populate_genres_languages, migrations.RunPython.noop),
    ]
