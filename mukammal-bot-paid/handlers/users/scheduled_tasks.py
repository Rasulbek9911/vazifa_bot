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
    try:
        async with aiohttp.ClientSession() as session:
            # Guruhlarni olib kelamiz
            async with session.get(f"{API_BASE_URL}/groups/") as resp:
                groups = await resp.json()
            
            for g in groups:
                chat_id = g.get("telegram_group_id")
                group_id = g["id"]

                if not chat_id:
                    continue  # telegram_group_id yo'q bo'lsa tashlab ketamiz

                try:
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
                except Exception as e:
                    print(f"⚠️ Guruh {g['name']} uchun PDF yuborishda xatolik: {e}")
                    continue
    except Exception as e:
        print(f"❌ Haftalik report yuborishda xatolik: {e}")
                    

# --- Vazifa topshirmaganlarga eslatma ---
async def send_unsubmitted_warnings():
    """Active mavzular bo'yicha vazifa topshirmagan studentlarga eslatma yuborish"""
    try:
        from base_app.models import Student, Topic, Task
        from django.utils import timezone
        
        students = await sync_to_async(list)(Student.objects.all())

        for student in students:
            try:
                # ✨ Studentning barcha guruhlarini va kurslarini aniqlaymiz
                all_groups = await sync_to_async(student.get_all_groups)()
                if not all_groups:
                    continue
                
                # Barcha kurs kodlarini yig'amiz
                student_courses = set()
                for grp in all_groups:
                    if grp.course:
                        student_courses.add(grp.course.code)
                    elif grp.course_type:
                        student_courses.add(grp.course_type)
                
                student_courses = list(student_courses)
                
                if not student_courses:
                    continue
                
                # Faqat student kurslariga mos active mavzularni olamiz
                active_topics = await sync_to_async(list)(
                    Topic.objects.filter(is_active=True)
                )
                # Client-side filter (barcha kurslar uchun)
                active_topics = [
                    t for t in active_topics
                    if (t.course and t.course.code in student_courses) or 
                       (not t.course and t.course_type in student_courses)
                ]
                
                # ⚡ YANGI: Faqat deadline o'tgan yoki yaqinlashgan mavzularni tekshiramiz
                now = timezone.now()
                # Deadline 24 soat ichida bo'lsa yoki o'tgan bo'lsa eslatma yuboramiz
                topics_to_check = []
                for t in active_topics:
                    if t.deadline:
                        # Deadline o'tgan yoki 24 soat ichida
                        if t.deadline <= now or (t.deadline - now).total_seconds() <= 86400:
                            topics_to_check.append(t)
                    # Agar deadline yo'q bo'lsa, hamma vaqt tekshiramiz
                    else:
                        topics_to_check.append(t)
                
                # ✨ Har bir mavzu uchun test YOKI maxsus topshiriq yuborilganini tekshiramiz
                unsubmitted = []
                for topic in topics_to_check:
                    # Mavzu turini aniqlaymiz (correct_answers bor bo'lsa Test, yo'q bo'lsa Maxsus)
                    expected_task_type = 'test' if topic.correct_answers else 'assignment'
                    
                    # Student o'sha mavzu va task_type uchun vazifa yuborgan-yubormaganini tekshiramiz
                    # course_type'siz tekshiramiz chunki topic.course allaqachon to'g'ri
                    task_exists = await sync_to_async(
                        Task.objects.filter(
                            student=student,
                            topic=topic,
                            task_type=expected_task_type
                        ).exists
                    )()
                    
                    if not task_exists:
                        unsubmitted.append(topic)

                if unsubmitted:
                    msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo'yicha vazifa topshirmagansiz!\n"
                    msg += "\n".join([
                        f"- {t.title}" + (f" (Deadline: {t.deadline.strftime('%d.%m.%Y %H:%M')})" if t.deadline else "")
                        for t in unsubmitted
                    ])
                    await safe_send_message(student.telegram_id, msg)

                    if len(unsubmitted) >= 3:
                        admin_msg = f"🚨 <b>{student.full_name}</b> {len(unsubmitted)} ta vazifa topshirmagan."
                        admin_msg += f"\nTelegram ID: <code>{student.telegram_id}</code>"
                        admin_msg += f"\n\n📋 <b>Mavzular:</b>\n" + "\n".join([
                            f"- {t.title}" + (f" (⏰ <i>Deadline: {t.deadline.strftime('%d.%m.%Y %H:%M')}</i>)" if t.deadline else "")
                            for t in unsubmitted
                        ])

                        kb = InlineKeyboardMarkup()
                        kb.add(InlineKeyboardButton(
                            text="Chatga o'tish",
                            url=f"tg://user?id={student.telegram_id}"
                        ))
                        
                        # Studentning barcha kurs adminlarini aniqlaymiz
                        course_admin_ids = set()
                        for grp in all_groups:
                            if grp.course and grp.course.admin_telegram_id:
                                course_admin_ids.add(grp.course.admin_telegram_id)
                        
                        # Course adminlari va barcha ADMINlarga yuboramiz
                        admins_to_notify = list(ADMINS) + list(course_admin_ids)
                        admins_to_notify = list(set(admins_to_notify))  # Dublikatlarni olib tashlash
                        
                        for admin_id in admins_to_notify:
                            try:
                                await bot.send_message(
                                    admin_id,
                                    admin_msg,
                                    reply_markup=kb,
                                    parse_mode="HTML"
                                )
                            except Exception as admin_err:
                                print(f"⚠️ Admin {admin_id} ga xabar yuborishda xatolik: {admin_err}")
            except Exception as e:
                print(f"⚠️ Student {student.telegram_id} uchun eslatma yuborishda xatolik: {e}")
                continue
    except Exception as e:
        print(f"❌ Eslatma yuborishda xatolik: {e}")
