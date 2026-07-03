from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0025_remove_group_course_type'),
    ]

    operations = [
        migrations.CreateModel(
            name='CoinWallet',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('total_coins', models.PositiveIntegerField(default=0)),
                ('current_streak', models.PositiveIntegerField(default=0)),
                ('longest_streak', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('course', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coin_wallets', to='base_app.course')),
                ('last_topic', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base_app.topic')),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coin_wallets', to='base_app.student')),
            ],
            options={
                'verbose_name': 'Tanga hamyoni',
                'verbose_name_plural': 'Tanga hamyonlari',
                'ordering': ['-total_coins'],
            },
        ),
        migrations.AddConstraint(
            model_name='coinwallet',
            constraint=models.UniqueConstraint(fields=['student', 'course'], name='unique_student_course_wallet'),
        ),
        migrations.CreateModel(
            name='CoinTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('task_type', models.CharField(default='test', max_length=20)),
                ('result_coins', models.PositiveIntegerField(default=0)),
                ('streak_coins', models.PositiveIntegerField(default=0)),
                ('total_coins', models.PositiveIntegerField(default=0)),
                ('streak_after', models.PositiveIntegerField(default=0)),
                ('deadline_penalty', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('topic', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='coin_transactions', to='base_app.topic')),
                ('wallet', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transactions', to='base_app.coinwallet')),
            ],
            options={
                'verbose_name': 'Tanga tranzaksiyasi',
                'verbose_name_plural': 'Tanga tranzaksiyalari',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddConstraint(
            model_name='cointransaction',
            constraint=models.UniqueConstraint(fields=['wallet', 'topic', 'task_type'], name='unique_wallet_topic_tasktype'),
        ),
    ]
