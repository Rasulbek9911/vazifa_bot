"""
Mock data generator - 10 ta student, 20 ta mavzu, random tasklar
"""
from django.core.management.base import BaseCommand
from base_app.models import Group, Student, Topic, Task
import random


class Command(BaseCommand):
    help = 'Generate mock data: 10 students, 20 topics with random tasks'

    def handle(self, *args, **options):
        self.stdout.write('🚀 Mock data yaratilmoqda...\n')
        
        # Faqat Attestatsiya guruhi
        group_attest, created = Group.objects.get_or_create(
            name='Test Guruh Attestatsiya B1',
            defaults={
                'course_type': 'attestatsiya',
                'is_full': False
            }
        )
        if created:
            self.stdout.write(f'✅ Guruh yaratildi: {group_attest.name}')
        else:
            self.stdout.write(f'📦 Mavjud guruh: {group_attest.name}')
        
        # 20 ta student Attestatsiya guruhida
        all_names = [
            'Aliyev Jasur',
            'Boboyeva Nilufar',
            'Valijonov Sardor',
            'Gulmirova Dilnoza',
            'Do\'stov Kamol',
            'Ergasheva Malika',
            'Ziyodullayev Akbar',
            'Ismoilova Sevara',
            'Karimov Timur',
            'Lutfullayeva Nigora',
            'Abdullayev Otabek',
            'Bekmurodova Madina',
            'Valiyev Nodir',
            'Gulyamova Zarina',
            'Davronov Eldor',
            'Eshonova Feruza',
            'Zokirov Sherzod',
            'Ibragimova Yulduz',
            'Kamolov Umid',
            'Latipova Shahzoda',
        ]
        
        attest_students = []
        for i, name in enumerate(all_names):
            student, created = Student.objects.get_or_create(
                telegram_id=f'mock_attest_{200000 + i}',
                defaults={
                    'full_name': name,
                    'group': group_attest
                }
            )
            attest_students.append(student)
            if created:
                self.stdout.write(f'  ✓ Attestatsiya Student: {name}')
        
        self.stdout.write(f'\n✅ Attestatsiya guruhida: {len(attest_students)} ta student\n')
        
        # 20 ta mavzu faqat Attestatsiya uchun
        attest_topics = []
        
        for i in range(1, 21):
            # Har 5 ta mavzudan biri "Maxsus topshiriq", qolganlari "Test"
            is_test = (i % 5) != 0
            
            # Attestatsiya mavzulari
            topic_attest, created = Topic.objects.get_or_create(
                title=f'{i}-mavzu Attestatsiya ({i}-dek)',
                defaults={
                    'course_type': 'attestatsiya',
                    'is_active': True,
                    'correct_answers': {'+': 'a' * 30} if is_test else None
                }
            )
            attest_topics.append(topic_attest)
            
            topic_type = '📝Test' if is_test else '📋Maxsus'
            if created:
                self.stdout.write(f'  ✓ Mavzu: {i}-mavzu {topic_type}')
        
        self.stdout.write(f'\n✅ Attestatsiya: {len(attest_topics)} ta mavzu\n')
        
        # Har bir student uchun random tasklar yaratish
        attest_task_count = 0
        
        # Attestatsiya studentlar uchun
        for student in attest_students:
            for topic in attest_topics:
                if random.random() < 0.75:  # 75% ehtimol
                    task_type = 'test' if topic.correct_answers else 'assignment'
                    grade = random.randint(15, 35)  # 15-35 oralig'ida
                    
                    task, created = Task.objects.get_or_create(
                        student=student,
                        topic=topic,
                        task_type=task_type,
                        defaults={
                            'course_type': 'attestatsiya',
                            'grade': grade,
                            'test_code': '+' if task_type == 'test' else None,
                            'test_answers': 'abc' * 10 if task_type == 'test' else None,
                            'file_link': 'https://t.me/test_file' if task_type == 'assignment' else None,
                        }
                    )
                    if created:
                        attest_task_count += 1
        
        self.stdout.write(f'✅ Attestatsiya: {attest_task_count} ta task\n')
        
        # Statistika
        self.stdout.write(self.style.SUCCESS('\n📊 Mock data tayyor:'))
        self.stdout.write('\n📜 ATTESTATSIYA:')
        self.stdout.write(f'  • Guruh: {group_attest.name}')
        self.stdout.write(f'  • Studentlar: {len(attest_students)} ta')
        self.stdout.write(f'  • Mavzular: {len(attest_topics)} ta')
        self.stdout.write(f'  • Tasklar: {attest_task_count} ta')
        self.stdout.write(f'  • PDF: http://localhost:8000/api/reports/{group_attest.id}/weekly/pdf/')
        self.stdout.write('\n')
