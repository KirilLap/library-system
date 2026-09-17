from django.db import migrations


TYPES = [
    ('MAHALLA', 'Махалля', True),
    ('SCHOOL', 'Школа', False),
    ('KINDERGARTEN', 'Детский сад', False),
    ('ORGANIZATION', 'Организация', False),
    ('OTHER', 'Другое', False),
]


def seed_types(apps, schema_editor):
    LocationType = apps.get_model('locations', 'LocationType')
    for code, name, is_open in TYPES:
        LocationType.objects.get_or_create(code=code, defaults={'name': name, 'is_open': is_open})


def unseed_types(apps, schema_editor):
    LocationType = apps.get_model('locations', 'LocationType')
    LocationType.objects.filter(code__in=[t[0] for t in TYPES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('locations', '0004_locationtype_location_is_public_alter_location_type'),
    ]

    operations = [
        migrations.RunPython(seed_types, unseed_types),
    ]
