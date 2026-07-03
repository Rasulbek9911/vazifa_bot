from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0030_topic_activated_at_coinwallet_last_submitted_at'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='followup',
            name='called_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='followup_calls', to=settings.AUTH_USER_MODEL,
                help_text="Oxirgi qo'ng'iroq qilgan operator",
            ),
        ),
        migrations.AddField(
            model_name='followup',
            name='locked_by',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='followup_locks', to=settings.AUTH_USER_MODEL,
                help_text="Hozir ishlayotgan operator",
            ),
        ),
        migrations.AddField(
            model_name='followup',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True, help_text="Blok tugash vaqti"),
        ),
        migrations.CreateModel(
            name='CallHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('called_at', models.DateTimeField(auto_now_add=True)),
                ('note', models.TextField(blank=True, default='')),
                ('result', models.CharField(
                    choices=[
                        ('answered', "Javob berdi"),
                        ('not_answered', "Ko'tarmadi"),
                        ('callback', "Keyinroq qo'ng'iroq qiladi"),
                        ('other', 'Boshqa'),
                    ],
                    default='answered', max_length=20,
                )),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='call_history', to='base_app.student',
                )),
                ('operator', models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='call_history', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': "Qo'ng'iroq tarixi",
                'verbose_name_plural': "Qo'ng'iroq tarixi",
                'ordering': ['-called_at'],
            },
        ),
    ]
