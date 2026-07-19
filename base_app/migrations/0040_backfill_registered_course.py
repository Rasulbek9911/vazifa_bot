from django.db import migrations


def backfill_registered_course(apps, schema_editor):
    Student = apps.get_model('base_app', 'Student')

    qs = Student.objects.filter(registered_course__isnull=True).prefetch_related('groups__course')
    to_update = []
    for student in qs:
        group = student.groups.order_by('id').first()
        if group is not None:
            student.registered_course_id = group.course_id
            to_update.append(student)

    Student.objects.bulk_update(to_update, ['registered_course_id'], batch_size=500)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('base_app', '0039_course_registration_strategy_group_target_role_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_registered_course, noop_reverse),
    ]
