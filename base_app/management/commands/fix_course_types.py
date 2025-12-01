from django.core.management.base import BaseCommand
from base_app.models import Group, Topic, Task


class Command(BaseCommand):
    help = 'Barcha mavjud datani attestatsiya kurs turiga o\'zgartirish'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('O\'zgarishlar boshlanmoqda...'))
        
        # Groups
        groups_updated = Group.objects.filter(course_type='milliy_sert').update(course_type='attestatsiya')
        self.stdout.write(self.style.SUCCESS(f'✅ {groups_updated} ta guruh attestatsiya ga o\'zgartirildi'))
        
        # Topics
        topics_updated = Topic.objects.filter(course_type='milliy_sert').update(course_type='attestatsiya')
        self.stdout.write(self.style.SUCCESS(f'✅ {topics_updated} ta mavzu attestatsiya ga o\'zgartirildi'))
        
        # Tasks
        tasks_updated = Task.objects.filter(course_type='milliy_sert').update(course_type='attestatsiya')
        self.stdout.write(self.style.SUCCESS(f'✅ {tasks_updated} ta task attestatsiya ga o\'zgartirildi'))
        
        self.stdout.write(self.style.SUCCESS('\n🎉 Barcha o\'zgarishlar muvaffaqiyatli amalga oshirildi!'))
        
        # Natijalarni ko'rsatish
        self.stdout.write(self.style.WARNING('\n📊 Hozirgi holat:'))
        self.stdout.write(f'Guruhlar: {Group.objects.filter(course_type="attestatsiya").count()} ta attestatsiya')
        self.stdout.write(f'Mavzular: {Topic.objects.filter(course_type="attestatsiya").count()} ta attestatsiya')
        self.stdout.write(f'Tasklar: {Task.objects.filter(course_type="attestatsiya").count()} ta attestatsiya')
