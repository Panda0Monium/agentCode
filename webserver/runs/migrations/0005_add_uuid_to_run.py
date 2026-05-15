import uuid
from django.db import migrations, models


def populate_uuids(apps, schema_editor):
    Run = apps.get_model('runs', 'Run')
    for run in Run.objects.filter(uuid__isnull=True).iterator():
        run.uuid = uuid.uuid4()
        run.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('runs', '0004_run_started_at'),
    ]

    operations = [
        # Step 1: add the column as nullable with no default so SQLite doesn't
        # evaluate uuid4() once and reuse the same value for every existing row
        migrations.AddField(
            model_name='run',
            name='uuid',
            field=models.UUIDField(editable=False, null=True),
        ),
        # Step 2: fill existing rows with unique values
        migrations.RunPython(populate_uuids, migrations.RunPython.noop),
        # Step 3: make the column non-null and unique
        migrations.AlterField(
            model_name='run',
            name='uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
