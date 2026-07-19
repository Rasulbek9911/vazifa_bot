"""
Tizim darajasidagi tekshiruv: hech qanday faol kurs (yoki studenti) bo'lmasa,
davomat va vazifa (test/maxsus topshiriq) oqimlari ishga tushmasligi kerak.
"""
from asgiref.sync import sync_to_async


@sync_to_async
def _check_system_state():
    from base_app.models import Course

    active_courses = Course.objects.filter(is_active=True)
    if not active_courses.exists():
        return "no_course"

    has_students = active_courses.filter(groups__enrolled_students__isnull=False).exists()
    if not has_students:
        return "no_student"

    return None


async def course_guard_message():
    """
    Agar tizim tayyor bo'lmasa (faol kurs yo'q yoki faol kurslarda student yo'q),
    userga ko'rsatiladigan xabarni qaytaradi. Hammasi joyida bo'lsa None qaytaradi.
    """
    reason = await _check_system_state()

    if reason == "no_course":
        return "❌ Hozircha faol kurs mavjud emas.\n\nAdmin bilan bog'laning."

    if reason == "no_student":
        return "❌ Hozircha faol kurslarda studentlar mavjud emas.\n\nAdmin bilan bog'laning."

    return None
