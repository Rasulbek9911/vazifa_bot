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
    admin_telegram_id = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Bu kurs uchun mas'ul admin Telegram ID"
    )
    has_assignments = models.BooleanField(
        default=False,
        help_text="Bu kursda 'Maxsus topshiriq' (fayl/rasm) yuborish ham mumkinmi"
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
    max_students = models.PositiveIntegerField(
        default=30,
        help_text="Guruh maksimal talabalar soni"
    )
    score_min = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Bu guruhga kiradigan minimal math_score (masalan: 1, 23, 28)"
    )
    score_max = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Bu guruhga kiradigan maksimal math_score (masalan: 22, 27, 35)"
    )
    is_full = models.BooleanField(
        default=False,
        help_text="Guruh to'lganmi (avtomatik hisoblanadi)"
    )

    def __str__(self):
        if self.course:
            return f"{self.name} ({self.course.name})"
        return self.name


class Student(models.Model):
    telegram_id = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=255)
    viloyat = models.CharField(max_length=100, blank=True, default='')
    tuman = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    math_score = models.PositiveSmallIntegerField(null=True, blank=True)
    is_blocked = models.BooleanField(
        default=False,
        help_text="True bo'lsa student botda vazifa yubora olmaydi"
    )

    # Ko'p guruh (ko'p kurs) uchun
    groups = models.ManyToManyField(
        Group, related_name="enrolled_students", blank=True,
        help_text="Student qaysi guruhlarda o'qiydi (ko'p kurs)")

    def __str__(self):
        group_names = [g.name for g in self.groups.all()[:2]]
        if group_names:
            groups_str = ", ".join(group_names)
            if self.groups.count() > 2:
                groups_str += f" +{self.groups.count() - 2}"
            return f"{self.full_name} ({groups_str})"
        return self.full_name
    
    def get_all_groups(self):
        """Barcha guruhlarni qaytarish"""
        return list(self.groups.all())
    
    def get_all_courses(self):
        courses = set()
        for grp in self.groups.all():
            if grp.course:
                courses.add(grp.course.code)
        return list(courses)


class Topic(models.Model):
   
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
    
    # Test natijalarini batafsil ko'rsatish (har bir savol to'g'ri/noto'g'ri)
    show_detailed_results = models.BooleanField(
        default=False,
        help_text="True bo'lsa - har bir savol to'g'ri/noto'g'ri ko'rinadi. False bo'lsa - faqat umumiy natija"
    )
    activated_at = models.DateTimeField(
        null=True, blank=True,
        help_text="is_active=True bo'lgan vaqt (streak hisoblash uchun)"
    )

    def save(self, *args, **kwargs):
        if self.is_active and self.activated_at is None:
            from django.utils import timezone
            self.activated_at = timezone.now()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.course:
            return f"{self.title} ({self.course.name})"
        return self.title


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
    
    # Maxsus topshiriq uchun - fayl (eski, bitta fayl uchun, backward compat)
    file_link = models.TextField(null=True, blank=True)

    # Maxsus topshiriq uchun - bir nechta fayl: [{"file_id": ..., "type": "photo"/"document"}, ...]
    files = models.JSONField(null=True, blank=True, default=list)

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


class AttendanceSession(models.Model):
    """Admin har dars uchun ochgan davomat sessiyasi"""
    code = models.CharField(max_length=20)
    created_by = models.CharField(max_length=50, help_text="Admin telegram_id")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(help_text="Sessiya tugash vaqti")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Davomat sessiyasi"
        verbose_name_plural = "Davomat sessiyalari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sessiya {self.code} ({self.created_at.strftime('%d.%m.%Y %H:%M')})"


class Attendance(models.Model):
    """Talabaning davomat yozuvi"""
    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, related_name="attendances"
    )
    session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="attendances"
    )
    marked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("student", "session")
        verbose_name = "Davomat"
        verbose_name_plural = "Davomatlar"
        ordering = ["-marked_at"]

    def __str__(self):
        return f"{self.student.full_name} — {self.session.code} ({self.marked_at.strftime('%d.%m.%Y %H:%M')})"


class InviteCode(models.Model):
    code = models.CharField(max_length=50, unique=True, default=uuid.uuid4)
    created_by = models.CharField(max_length=50)  # Admin telegram_id
    is_used = models.BooleanField(default=False)
    used_by = models.CharField(max_length=50, null=True, blank=True)  # Student telegram_id
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.code} - {'Ishlatilgan' if self.is_used else 'Yangi'}"


class FollowUp(models.Model):
    """Admin qo'ng'iroq qilgan talabalar ro'yxati"""
    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='followup')
    called_at = models.DateTimeField(null=True, blank=True)
    called_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='followup_calls', help_text="Oxirgi qo'ng'iroq qilgan operator"
    )
    locked_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='followup_locks', help_text="Hozir ishlayotgan operator"
    )
    locked_until = models.DateTimeField(null=True, blank=True, help_text="Blok tugash vaqti")
    note = models.TextField(blank=True, default='')
    topic_ids_at_call = models.JSONField(null=True, blank=True, default=None,
        help_text="Qo'ng'iroq vaqtidagi topshirilmagan mavzular ID ro'yxati")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Ogohlantirish"
        verbose_name_plural = "Ogohlantirishlar"
        ordering = ['-called_at']

    def is_locked(self):
        from django.utils import timezone
        return self.locked_by_id and self.locked_until and self.locked_until > timezone.now()

    def __str__(self):
        status = f"qo'ng'iroq qilindi ({self.called_at.strftime('%d.%m.%Y')})" if self.called_at else "qo'ng'iroq qilinmagan"
        return f"{self.student.full_name} — {status}"


class CallHistory(models.Model):
    """Har bir qo'ng'iroq urinishi tarixi"""
    RESULT_CHOICES = [
        ('answered', 'Javob berdi'),
        ('not_answered', 'Ko\'tarmadi'),
        ('callback', 'Keyinroq qo\'ng\'iroq qiladi'),
        ('other', 'Boshqa'),
    ]
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='call_history')
    operator = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, related_name='call_history'
    )
    called_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, default='')
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='answered')

    class Meta:
        verbose_name = "Qo'ng'iroq tarixi"
        verbose_name_plural = "Qo'ng'iroq tarixi"
        ordering = ['-called_at']

    def __str__(self):
        op = self.operator.get_full_name() or self.operator.username if self.operator else '?'
        return f"{self.student.full_name} ← {op} ({self.called_at.strftime('%d.%m.%Y %H:%M')})"


class CoinWallet(models.Model):
    """Student uchun kurs bo'yicha tanga hamyoni"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="coin_wallets")
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="coin_wallets")
    total_coins = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)
    last_topic = models.ForeignKey(
        Topic, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    last_submitted_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Foydalanuvchi oxirgi topshirgan vaqt (streak batch aniqlash uchun)"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("student", "course")
        verbose_name = "Tanga hamyoni"
        verbose_name_plural = "Tanga hamyonlari"
        ordering = ["-total_coins"]

    def __str__(self):
        return f"{self.student.full_name} — {self.course.name}: {self.total_coins} tanga"


class CoinTransaction(models.Model):
    """Har bir tanga berilganda log"""
    wallet = models.ForeignKey(CoinWallet, on_delete=models.CASCADE, related_name="transactions")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="coin_transactions")
    task_type = models.CharField(max_length=20, default='test')
    result_coins = models.PositiveIntegerField(default=0)
    streak_coins = models.PositiveIntegerField(default=0)
    total_coins = models.PositiveIntegerField(default=0)
    streak_after = models.PositiveIntegerField(default=0)
    deadline_penalty = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("wallet", "topic", "task_type")
        verbose_name = "Tanga tranzaksiyasi"
        verbose_name_plural = "Tanga tranzaksiyalari"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.wallet.student.full_name} +{self.total_coins} tanga ({self.topic.title})"


class PaymentPlan(models.Model):
    """Har bir student uchun kurs bo'yicha jami to'lashi kerak summa"""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payment_plans')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payment_plans')
    total_amount = models.PositiveIntegerField(help_text="Jami to'lashi kerak summa (so'm)")
    note = models.TextField(blank=True, default='', help_text="Izoh (chegirma, maxsus narx va h.k.)")
    created_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, related_name='created_plans'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course')
        verbose_name = "To'lov rejasi"
        verbose_name_plural = "To'lov rejalari"
        ordering = ['-created_at']

    def paid_total(self):
        return sum(p.amount for p in self.payments.all())

    def remaining(self):
        return max(0, self.total_amount - self.paid_total())

    def is_complete(self):
        return self.paid_total() >= self.total_amount

    def status(self):
        paid = self.paid_total()
        if paid == 0:
            return 'unpaid'
        if paid >= self.total_amount:
            return 'complete'
        return 'partial'

    def __str__(self):
        return f"{self.student.full_name} — {self.course.name}: {self.total_amount:,} so'm"


class Payment(models.Model):
    """Har bir to'lov yozuvi"""
    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE, related_name='payments')
    amount = models.PositiveIntegerField(help_text="To'langan summa (so'm)")
    paid_at = models.DateField(help_text="To'lov sanasi")
    note = models.TextField(blank=True, default='')
    entered_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, related_name='entered_payments'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        ordering = ['-paid_at', '-created_at']

    def __str__(self):
        return f"{self.plan.student.full_name}: {self.amount:,} so'm ({self.paid_at})"


class OperatorProfile(models.Model):
    """Operator uchun qo'shimcha profil — biriktirilgan guruhlar"""
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='operator_profile'
    )
    assigned_groups = models.ManyToManyField(
        Group, blank=True, related_name='operators',
        verbose_name='Biriktirilgan guruhlar'
    )

    class Meta:
        verbose_name = "Operator profili"
        verbose_name_plural = "Operator profillari"

    def __str__(self):
        return f"{self.user.username} — operator profili"


class ScheduleConfig(models.Model):
    """Bot'dagi rejalashtirilgan (cron) vazifalar uchun sozlama — admin panel orqali boshqariladi"""
    job_key = models.CharField(max_length=50, unique=True)
    enabled = models.BooleanField(default=True)
    weekdays = models.CharField(
        max_length=30, blank=True, default='',
        help_text="vergul bilan: mon,tue,wed,thu,fri,sat,sun. Bo'sh = har kuni"
    )
    hour = models.PositiveSmallIntegerField(default=21)
    minute = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Schedule sozlamasi"
        verbose_name_plural = "Schedule sozlamalari"

    def __str__(self):
        return f"{self.job_key} ({'on' if self.enabled else 'off'})"


class WeeklyReportSetting(models.Model):
    """Haftalik PDF hisobot uchun qaysi mavzular ko'rsatilishi (oxirgi 10 ta yoki aniq oy)"""
    mode = models.CharField(max_length=10, default='last10')  # 'last10' | 'month'
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    month = models.PositiveSmallIntegerField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Haftalik PDF sozlamasi"
        verbose_name_plural = "Haftalik PDF sozlamalari"

    def __str__(self):
        return f"{self.mode} {self.year or ''}-{self.month or ''}"


class MonthlyStreakSetting(models.Model):
    """
    Belgilangan (year, month) uchun 'oylik streak rejimi'ni yoqadi.
    Yoqilgan bo'lsa — Tangalarim/reyting/PDF'da o'sha oy bo'yicha streak
    va tanga hisob-kitobi shu oyning birinchi mavzusidan 1 deb qayta
    (on-the-fly, DB'ga yozmasdan) hisoblanadi — oldingi oylardagi uzviylik
    hisobga olinmaydi. O'chirilgan bo'lsa — global (butun davr) streak ishlatiladi.
    """
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    enabled = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Oylik streak sozlamasi"
        verbose_name_plural = "Oylik streak sozlamalari"
        unique_together = ('year', 'month')

    def __str__(self):
        return f"{self.year}-{self.month:02d} ({'on' if self.enabled else 'off'})"
