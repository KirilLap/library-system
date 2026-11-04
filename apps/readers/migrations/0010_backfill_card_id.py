import secrets

from django.db import migrations


def backfill_card_ids(apps, schema_editor):
    """Выдаёт случайный 10-значный ID читателям, у которых его ещё нет."""
    Reader = apps.get_model('readers', 'Reader')
    User = apps.get_model('auth', 'User')
    for reader in Reader.objects.filter(card_id__isnull=True):
        while True:
            value = str(secrets.randbelow(9 * 10 ** 9) + 10 ** 9)
            if not Reader.objects.filter(card_id=value).exists() \
                    and not User.objects.filter(username=value).exists():
                break
        reader.card_id = value
        reader.save(update_fields=['card_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('readers', '0009_reader_card_id_birth_year_nearest_location_password_flag'),
    ]

    operations = [
        migrations.RunPython(backfill_card_ids, migrations.RunPython.noop),
    ]
