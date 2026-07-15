from django.db import migrations

DEFAULTS = [
    {'job_key': 'weekly_report', 'weekdays': 'wed,sun', 'hour': 13, 'minute': 0},
    {'job_key': 'unsubmitted_warnings', 'weekdays': 'mon,thu', 'hour': 21, 'minute': 0},
    {'job_key': 'deadline_results', 'weekdays': '', 'hour': 21, 'minute': 0},
    {'job_key': 'attendance_csv', 'weekdays': 'sun', 'hour': 7, 'minute': 0},
    {'job_key': 'followup_reminders', 'weekdays': 'tue,fri', 'hour': 21, 'minute': 0},
]


def seed_defaults(apps, schema_editor):
    ScheduleConfig = apps.get_model('base_app', 'ScheduleConfig')
    for d in DEFAULTS:
        ScheduleConfig.objects.get_or_create(
            job_key=d['job_key'],
            defaults={'enabled': True, 'weekdays': d['weekdays'], 'hour': d['hour'], 'minute': d['minute']},
        )

    WeeklyReportSetting = apps.get_model('base_app', 'WeeklyReportSetting')
    if not WeeklyReportSetting.objects.exists():
        WeeklyReportSetting.objects.create(mode='last10')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0035_scheduleconfig_weeklyreportsetting'),
    ]

    operations = [
        migrations.RunPython(seed_defaults, noop),
    ]
