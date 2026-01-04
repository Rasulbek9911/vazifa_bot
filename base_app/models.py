from django.db import models
import uuid


class Course(models.Model):
    """Kurs turlari (dinamik boshqarish)"""
    name = models.CharField(
        max_length=100, 
        unique=True, 
        help_text="Kurs nomi (Milliy sertifikat, Attestatsiya, ...)"
    )
    code = models.CharField(
        max_length=50, 
        unique=True, 
        help_text="Kurs kodi (milliy_sert, attestatsiya, ...)"
    )
    task_type = models.CharField(
        max_length=20,
        choices=[('test', 'Test'), ('assignment', 'Maxsus topshiriq')],
        default='test',
        help_text="Bu kursda qanday vazifa topshiriladi"
    )
    is_active = models.BooleanField(
        default=True, 
        help_text="Kurs faolmi"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Kurs"
        verbose_name_plural = "Kurslar"
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"


class Group(models.Model):
    # DEPRECATED: Eski maydon (migration uchun saqlanadi)
    COURSE_CHOICES = [
        ('milliy_sert', 'Milliy sertifikat'),
        ('attestatsiya', 'Attestatsiya'),
    ]
    course_type = models.CharField(
        max_length=20, 
        choices=COURSE_CHOICES, 
        null=True,
        blank=True,
        help_text="DEPRECATED: Iltimos 'course' dan foydalaning"
    )
    
    # YANGI maydon: Dinamik course
    course = models.ForeignKey(
        Course, 
        on_delete=models.PROTECT, 
        related_name="groups",
        null=True,
        blank=True,
        help_text="Guruh qaysi kursga tegishli"
    )
    
    name = models.CharField(max_length=100, unique=True)
    telegram_group_id = models.CharField(
        max_length=50, unique=True, null=True, blank=True, default=None)
    invite_link = models.URLField(max_length=255, null=True, blank=True, default=None)
    is_full = models.BooleanField(
        default=True, 
        help_text="Guruh to'lganmi (50/50)"
    )

    def __str__(self):
        if self.course:
            return f"{self.name} ({self.course.name})"
        elif self.course_type:
            return f"{self.name} ({self.get_course_type_display()})"
        return self.name


class Student(models.Model):
    telegram_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="students", null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.group.name})"


class Topic(models.Model):
    # DEPRECATED: Eski maydon
    COURSE_CHOICES = [
        ('milliy_sert', 'Milliy sertifikat'),
        ('attestatsiya', 'Attestatsiya'),
    ]
    course_type = models.CharField(
        max_length=20, 
        choices=COURSE_CHOICES,
        null=True,
        blank=True,
        help_text="DEPRECATED: Iltimos 'course' dan foydalaning"
    )
    
    # YANGI maydon: Dinamik course
    course = models.ForeignKey(
        Course,
        on_delete=models.PROTECT,
        related_name="topics",
        null=True,
        blank=True,
        help_text="Mavzu qaysi kursga tegishli"
    )
    
    title = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False, null=True, blank=True)
    deadline = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Deadline dan keyin topshirilsa 80% ball beriladi"
    )
    
    # Test uchun to'g'ri javoblar (JSON format: {"test_code": "+", "answers": "abc"})
    correct_answers = models.JSONField(null=True, blank=True, default=dict)

    def __str__(self):
        if self.course:
            return f"{self.title} ({self.course.name})"
        elif self.course_type:
            return f"{self.title} ({self.get_course_type_display()})"
        return self.title


class Task(models.Model):
    TASK_TYPE_CHOICES = [
        ('test', 'Test'),
        ('assignment', 'Maxsus topshiriq'),
    ]
    
    # DEPRECATED: Eski maydon (migration uchun saqlanadi)
    COURSE_CHOICES = [
        ('milliy_sert', 'Milliy Sertifikat'),
        ('attestatsiya', 'Attestatsiya'),
    ]
    course_type = models.CharField(
        max_length=20, 
        choices=COURSE_CHOICES,
        null=True,
        blank=True,
        help_text="DEPRECATED: topic.course dan olinadi"
    )
    
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="tasks")
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="tasks")
    task_type = models.CharField(
        max_length=20, choices=TASK_TYPE_CHOICES, default='test')
    
    # Maxsus topshiriq uchun - fayl
    file_link = models.TextField(null=True, blank=True)
    
    # Test uchun - test kodi va javoblar
    test_code = models.CharField(max_length=50, null=True, blank=True)
    test_answers = models.CharField(max_length=255, null=True, blank=True)
    
    # Baho: 0-55 gacha (test to'g'ri javoblar soni yoki maxsus topshiriq bahosi)
    grade = models.PositiveSmallIntegerField(
        null=True, 
        blank=True,
        help_text="Test uchun: to'g'ri javoblar soni (0-55). Vazifa uchun: admin bahosi (0-55)"
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
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
