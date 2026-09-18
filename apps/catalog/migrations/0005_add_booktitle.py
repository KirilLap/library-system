import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_alter_book_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='BookTitle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cover', models.ImageField(blank=True, null=True, upload_to='covers/', verbose_name='Обложка')),
                ('title', models.CharField(max_length=500, verbose_name='Название')),
                ('author', models.CharField(max_length=300, verbose_name='Автор')),
                ('year', models.IntegerField(blank=True, null=True, verbose_name='Год')),
                ('publisher', models.CharField(blank=True, max_length=300, verbose_name='Издательство')),
                ('genre', models.CharField(default='OTHER', max_length=30, verbose_name='Жанр')),
                ('language', models.CharField(default='RU', max_length=20, verbose_name='Язык')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('isbn', models.CharField(blank=True, max_length=20, verbose_name='ISBN')),
                ('marc_data', models.JSONField(blank=True, null=True, verbose_name='MARC данные')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Книга (название)',
                'verbose_name_plural': 'Книги (названия)',
                'ordering': ['title'],
            },
        ),
        migrations.AddField(
            model_name='book',
            name='book_title',
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='copies', to='catalog.booktitle', verbose_name='Название',
            ),
        ),
    ]
