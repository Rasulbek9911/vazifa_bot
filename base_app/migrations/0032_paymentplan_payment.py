from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0031_followup_operator_callhistory'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('total_amount', models.PositiveIntegerField(help_text="Jami to'lashi kerak summa (so'm)")),
                ('note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_plans', to='base_app.student')),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_plans', to='base_app.course')),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_plans', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': "To'lov rejasi", 'verbose_name_plural': "To'lov rejalari", 'ordering': ['-created_at']},
        ),
        migrations.AddConstraint(
            model_name='paymentplan',
            constraint=models.UniqueConstraint(fields=['student', 'course'], name='unique_student_course_plan'),
        ),
        migrations.CreateModel(
            name='Payment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('amount', models.PositiveIntegerField(help_text="To'langan summa (so'm)")),
                ('paid_at', models.DateField(help_text="To'lov sanasi")),
                ('note', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('plan', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='base_app.paymentplan')),
                ('entered_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='entered_payments', to=settings.AUTH_USER_MODEL)),
            ],
            options={'verbose_name': "To'lov", 'verbose_name_plural': "To'lovlar", 'ordering': ['-paid_at', '-created_at']},
        ),
    ]
