import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_genre_language'),
        ('locations', '0002_location_latitude_location_longitude'),
        ('organizations', '0002_locationworker'),
        ('readers', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='reader',
            name='affiliated_location',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='affiliated_readers',
                to='locations.location',
                verbose_name='Прикреплённая точка',
            ),
        ),
        migrations.CreateModel(
            name='Loan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('issued_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата выдачи')),
                ('returned_at', models.DateTimeField(blank=True, null=True, verbose_name='Дата возврата')),
                ('is_returned', models.BooleanField(default=False, verbose_name='Возвращена')),
                ('book', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='loans',
                    to='catalog.book',
                    verbose_name='Книга',
                )),
                ('issued_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='issued_loans',
                    to='organizations.locationworker',
                    verbose_name='Выдал работник',
                )),
                ('location', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='loans',
                    to='locations.location',
                    verbose_name='Точка',
                )),
                ('reader', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='loans',
                    to='readers.reader',
                    verbose_name='Читатель',
                )),
            ],
            options={
                'verbose_name': 'Выдача',
                'verbose_name_plural': 'Выдачи',
                'ordering': ['-issued_at'],
            },
        ),
    ]
