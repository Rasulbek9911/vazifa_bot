"""
Scheduled tasks: weekly reports, unsubmitted task warnings
"""
import aiohttp
from data.config import ADMINS, API_BASE_URL
from loader import bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message


# --- Haftalik report ---
async def send_weekly_reports():
    """Har hafta guruh bo'yicha PDF report yuborish (faqat active mavzu bo'lsa)"""
    async with aiohttp.ClientSession() as session:
        # Guruhlarni olib kelamiz
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
        
        for g in groups:
            chat_id = g.get("telegram_group_id")
            group_id = g["id"]

            if not chat_id:
                continue  # telegram_group_id yo'q bo'lsa tashlab ketamiz

            # PDF reportni olib kelamiz
            # Server o'zi active mavzularni tekshiradi va 404 qaytaradi
            async with session.get(f"{API_BASE_URL}/reports/{group_id}/weekly/pdf/") as resp:
                if resp.status == 200:
                    pdf_bytes = await resp.read()
                    await bot.send_document(
                        chat_id,
                        ("weekly_report.pdf", pdf_bytes),
                        caption=f"📊 {g['name']} guruhining haftalik hisobot"
                    )
                # 404 yoki xatolik bo'lsa, guruhga hech narsa yubormaymiz
                    

# --- Vazifa topshirmaganlarga eslatma ---
async def send_unsubmitted_warnings():
    """Active mavzular bo'yicha vazifa topshirmagan studentlarga eslatma yuborish"""
    from base_app.models import Student, Topic, Task
    students = await sync_to_async(list)(Student.objects.all())

    for student in students:
        # ✨ YANGI: Studentning guruh course_type'ini aniqlaymiz
        student_group = await sync_to_async(lambda: student.group)()
        if not student_group:
            continue
        
        student_course_type = student_group.course_type
        
        # Faqat student kursiga mos active mavzularni olamiz
        active_topics = await sync_to_async(list)(
            Topic.objects.filter(is_active=True, course_type=student_course_type)
        )
        
        # ✨ YANGI: Har bir mavzu uchun test YOKI maxsus topshiriq yuborilganini tekshiramiz
        unsubmitted = []
        for topic in active_topics:
            # Mavzu turini aniqlaymiz (correct_answers bor bo'lsa Test, yo'q bo'lsa Maxsus)
            expected_task_type = 'test' if topic.correct_answers else 'assignment'
            
            # Student o'sha mavzu va task_type uchun vazifa yuborgan-yubormaganini tekshiramiz
            task_exists = await sync_to_async(
                Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=expected_task_type,
                    course_type=student_course_type
                ).exists
            )()
            
            if not task_exists:
                unsubmitted.append(topic)

        if unsubmitted:
            msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo'yicha vazifa topshirmagansiz!\n"
            msg += "\n".join([f"- {t.title}" for t in unsubmitted])
            await safe_send_message(student.telegram_id, msg)

            if len(unsubmitted) >= 3:
                admin_msg = f"🚨 {student.full_name} {len(unsubmitted)} ta vazifa topshirmagan."
                admin_msg += f"\nTelegram ID: <code>{student.telegram_id}</code>"
                admin_msg += f"\nMavzular:\n" + "\n".join([f"- {t.title}" for t in unsubmitted])

                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(
                    text="Chatga o'tish",
                    url=f"tg://user?id={student.telegram_id}"
                ))

                await bot.send_message(
                    ADMINS[0],
                    admin_msg,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
