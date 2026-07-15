"""
Bot butun umri davomida yagona AsyncIOScheduler obyekti.
app.py uni ishga tushiradi, admin_handlers.py esa Sozlamalar orqali
runtime'da vazifalarni qayta rejalashtirish (reschedule) uchun ishlatadi.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

JOB_FUNC_NAMES = {
    'weekly_report': 'send_weekly_reports',
    'unsubmitted_warnings': 'send_unsubmitted_warnings',
    'deadline_results': 'send_deadline_results',
    'attendance_csv': 'send_attendance_csv',
    'followup_reminders': 'send_followup_reminders',
}


def _get_job_func(job_key: str):
    # Lazy import — modul yuklanish vaqtida handlers.users bilan circular importga tushmaslik uchun
    from handlers.users import scheduled_tasks
    return getattr(scheduled_tasks, JOB_FUNC_NAMES[job_key])

JOB_LABELS = {
    'weekly_report': "📊 Haftalik report",
    'unsubmitted_warnings': "⚠️ Vazifa eslatmasi",
    'deadline_results': "⏰ Deadline natijalari",
    'attendance_csv': "📋 Davomat CSV",
    'followup_reminders': "📞 Followup eslatma",
}

DAY_LABELS = {
    'mon': 'Dushanba', 'tue': 'Seshanba', 'wed': 'Chorshanba',
    'thu': 'Payshanba', 'fri': 'Juma', 'sat': 'Shanba', 'sun': 'Yakshanba',
}
DAY_ORDER = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

DEFAULT_SCHEDULE = {
    'weekly_report': {'weekdays': 'wed,sun', 'hour': 13, 'minute': 0},
    'unsubmitted_warnings': {'weekdays': 'mon,thu', 'hour': 21, 'minute': 0},
    'deadline_results': {'weekdays': '', 'hour': 21, 'minute': 0},
    'attendance_csv': {'weekdays': 'sun', 'hour': 7, 'minute': 0},
    'followup_reminders': {'weekdays': 'tue,fri', 'hour': 21, 'minute': 0},
}


def days_str_to_label(weekdays: str) -> str:
    if not weekdays:
        return "Har kuni"
    codes = [c.strip() for c in weekdays.split(',') if c.strip()]
    if set(codes) == set(DAY_ORDER):
        return "Har kuni"
    return ", ".join(DAY_LABELS.get(c, c) for c in codes)


def apply_job(job_key: str, weekdays: str, hour: int, minute: int):
    """Jobni (qayta) rejalashtiradi. weekdays='' bo'lsa har kuni ishlaydi."""
    func = _get_job_func(job_key)
    dow = weekdays if weekdays else '*'
    scheduler.add_job(
        func, "cron", day_of_week=dow, hour=hour, minute=minute,
        id=job_key, replace_existing=True,
    )


def remove_job(job_key: str):
    try:
        scheduler.remove_job(job_key)
    except Exception:
        pass
