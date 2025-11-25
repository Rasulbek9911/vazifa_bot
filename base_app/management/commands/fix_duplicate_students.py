"""
Management command: takroriy studentlarni o'chirish va faqat eng yangi ro'yxatdan o'tganni saqlash
"""
from django.core.management.base import BaseCommand
from base_app.models import Student
from django.db.models import Count


class Command(BaseCommand):
    help = "Takroriy telegram_id li studentlarni o'chirish (eng so'nggisi saqlanadi)"

    def handle(self, *args, **options):
        # Takroriy telegram_id larni topish
        duplicates = (
            Student.objects
            .values('telegram_id')
            .annotate(count=Count('id'))
            .filter(count__gt=1)
        )

        total_deleted = 0

        for dup in duplicates:
            telegram_id = dup['telegram_id']
            # Shu telegram_id li barcha studentlarni olish (eng yangi birinchi)
            students = Student.objects.filter(
                telegram_id=telegram_id
            ).order_by('-id')  # Eng yangi birinchi

            # Birinchisini (eng yangi) saqlash, qolganini o'chirish
            keep_student = students.first()
            delete_students = students[1:]

            deleted_count = delete_students.count()
            delete_students.delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ telegram_id: {telegram_id} - "
                    f"Saqlandi: {keep_student.full_name} (ID: {keep_student.id}), "
                    f"O'chirildi: {deleted_count} ta"
                )
            )

            total_deleted += deleted_count

        if total_deleted == 0:
            self.stdout.write(
                self.style.WARNING("ℹ️ Takroriy studentlar topilmadi")
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✅ Jami o'chirildi: {total_deleted} ta takroriy student"
                )
            )
