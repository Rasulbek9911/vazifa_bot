from django.db import models


class Group(models.Model):
    name = models.CharField(max_length=100, unique=True)
    telegram_group_id = models.CharField(
        max_length=50, unique=True, null=True, blank=True, default=None)
    invite_link = models.URLField(max_length=255, null=True, blank=True, default=None)

    def __str__(self):
        return self.name


class Student(models.Model):
    telegram_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    group = models.ForeignKey(
        Group, on_delete=models.CASCADE, related_name="students", null=True, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.group.name})"


class Topic(models.Model):
    title = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False,null=True, blank=True)

    def __str__(self):
        return self.title


class Task(models.Model):
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="tasks")
    topic = models.ForeignKey(
        Topic, on_delete=models.CASCADE, related_name="tasks")
    # Telegram file_id yoki URL
    file_link = models.TextField(null=True, blank=True)
    grade = models.PositiveSmallIntegerField(
        null=True, blank=True)  # Baho (3,4,5)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # bitta student bitta mavzuga faqat bitta vazifa topshira oladi
        unique_together = ("student", "topic")

    def __str__(self):
        return f"{self.student.full_name} → {self.topic.title} ({self.grade or 'Baholanmagan'})"
