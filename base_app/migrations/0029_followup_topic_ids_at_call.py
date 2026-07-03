from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0028_followup'),
    ]

    operations = [
        migrations.AddField(
            model_name='followup',
            name='topic_ids_at_call',
            field=models.JSONField(
                blank=True, null=True, default=None,
                help_text="Qo'ng'iroq vaqtidagi topshirilmagan mavzular ID ro'yxati",
            ),
        ),
    ]
