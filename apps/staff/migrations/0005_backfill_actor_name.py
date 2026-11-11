from django.db import migrations


def fill_names(apps, schema_editor):
    """Старым записям журнала записываем имя сотрудника, чтобы оно не потерялось при удалении учётной записи."""
    ActionLog = apps.get_model('staff', 'ActionLog')
    for entry in ActionLog.objects.filter(actor__isnull=False, actor_name='').select_related('actor'):
        # В миграциях у модели нет методов (get_full_name), поэтому имя собираем сами
        full_name = f'{entry.actor.first_name} {entry.actor.last_name}'.strip()
        entry.actor_name = (full_name or entry.actor.username)[:150]
        entry.save(update_fields=['actor_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('staff', '0004_actionlog_actor_name'),
    ]

    operations = [
        migrations.RunPython(fill_names, migrations.RunPython.noop),
    ]
