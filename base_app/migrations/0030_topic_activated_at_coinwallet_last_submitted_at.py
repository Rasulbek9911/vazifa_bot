from django.db import migrations, models


def set_activated_at_for_existing(apps, schema_editor):
    """Mavjud active topiclar uchun activated_at = created_at"""
    Topic = apps.get_model('base_app', 'Topic')
    Topic.objects.filter(is_active=True, activated_at__isnull=True).update(
        activated_at=models.F('created_at')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0029_followup_topic_ids_at_call'),
    ]

    operations = [
        migrations.AddField(
            model_name='topic',
            name='activated_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="is_active=True bo'lgan vaqt (streak hisoblash uchun)",
            ),
        ),
        migrations.AddField(
            model_name='coinwallet',
            name='last_submitted_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Foydalanuvchi oxirgi topshirgan vaqt (streak batch aniqlash uchun)",
            ),
        ),
        migrations.RunPython(set_activated_at_for_existing, migrations.RunPython.noop),
    ]
