from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0033_operatorprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='student',
            name='is_blocked',
            field=models.BooleanField(default=False, help_text="True bo'lsa student botda vazifa yubora olmaydi"),
        ),
    ]
