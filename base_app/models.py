from django.db import models
import uuid


class Group(models.Model):
    COURSE_CHOICES = [
        ('milliy_sert', 'Milliy sertifikat'),
        ('attestatsiya', 'Attestatsiya'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    course_type = models.CharField(
        max_length=20, 
        choices=COURSE_CHOICES, 
        default='milliy_sert',
        help_text="Guruh qaysi kurs uchun"
    )
    telegram_group_id = models.CharField(
        max_length=50, unique=True, null=True, blank=True, default=None)
    invite_link = models.URLField(max_length=255, null=True, blank=True, default=None)
    is_full = models.BooleanField(
        default=True, 
        help_text="Guruh to'lganmi (50/50)"
    )

    def __str__(self):
        return f"{self.name} ({self.get_course_type_display()})"


class Student(models.Model):
    telegram_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="students", null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.group.name})"


class Topic(models.Model):
    COURSE_CHOICES = [
        ('milliy_sert', 'Milliy sertifikat'),
        ('attestatsiya', 'Attestatsiya'),
    ]
    
    title = models.CharField(max_length=255, unique=True)
    course_type = models.CharField(
        max_length=20, 
        choices=COURSE_CHOICES, 
        default='milliy_sert',
        help_text="Mavzu qaysi kurs uchun"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    
    # Test uchun to'g'ri javoblar (JSON format: {"1": "abc", "2": "bcd", ...})
    correct_answers = models.JSONField(null=True, blank=True, default=dict)

    def __str__(self):
        return f"{self.title} ({self.get_course_type_display()})"


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ('test', 'Test'),
        ('assignment', 'Maxsus topshiriq'),
    ]
    
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="tasks")
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="tasks")
    task_type = models.CharField(
        max_length=20, choices=TASK_TYPE_CHOICES, default='test')
    
    # Maxsus topshiriq uchun - fayl
    file_link = models.TextField(null=True, blank=True)
    
    # Test uchun - test kodi va javoblar
    test_code = models.CharField(max_length=50, null=True, blank=True)  # Masalan: "+", "*", "A"
    test_answers = models.CharField(max_length=255, null=True, blank=True)  # Masalan: "abc", "1a2c3b"
    
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True)  # Baho (3,4,5)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # bitta student bitta mavzuga har xil turdagi vazifa topshira oladi
        unique_together = ("student", "topic", "task_type")

    def __str__(self):
        return f"{self.student.full_name} → {self.topic.title} ({self.get_task_type_display()}) ({self.grade or 'Baholanmagan'})"


class InviteCode(models.Model):
    code = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    created_by = models.CharField(max_length=50)  # Admin telegram_id
    is_used = models.BooleanField(default=False)
    used_by = models.CharField(max_length=50, null=True, blank=True)  # Student telegram_id
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.code} - {'Ishlatilgan' if self.is_used else 'Yangi'}"
