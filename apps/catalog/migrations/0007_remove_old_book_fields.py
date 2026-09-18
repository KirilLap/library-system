import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_migrate_booktitle_data'),
    ]

    operations = [
        migrations.RemoveField(model_name='book', name='title'),
        migrations.RemoveField(model_name='book', name='author'),
        migrations.RemoveField(model_name='book', name='year'),
        migrations.RemoveField(model_name='book', name='publisher'),
        migrations.RemoveField(model_name='book', name='genre'),
        migrations.RemoveField(model_name='book', name='language'),
        migrations.RemoveField(model_name='book', name='description'),
        migrations.RemoveField(model_name='book', name='isbn'),
        migrations.RemoveField(model_name='book', name='marc_data'),
        migrations.RemoveField(model_name='book', name='cover'),
        migrations.AlterField(
            model_name='book',
            name='book_title',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='copies', to='catalog.booktitle', verbose_name='Название',
            ),
        ),
        migrations.AlterModelOptions(
            name='book',
            options={'ordering': ['inventory_number'], 'verbose_name': 'Экземпляр книги', 'verbose_name_plural': 'Экземпляры книг'},
        ),
    ]
