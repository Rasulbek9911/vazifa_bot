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
                    # PDF reportni olib kelamiz (oxirgi 10 ta topic + umumiy o'rtacha)
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
        import asyncio
        
        # ⚡ OPTIMIZATSIYA: Barcha ma'lumotlarni bitta querysetda prefetch qilamiz
        students = await sync_to_async(list)(
            Student.objects.all()
            .prefetch_related('groups__course', 'group__course')
            .only('id', 'telegram_id', 'full_name')
        )
        
        # Active topiclarni bir marta olamiz (har student uchun qayta-qayta emas)
        active_topics = await sync_to_async(list)(
            Topic.objects.filter(is_active=True)
            .select_related('course')
            .only('id', 'title', 'deadline', 'correct_answers', 'course_type', 'course')
        )
        
        # Har bir topic uchun course ma'lumotlarini oldindan olamiz
        topic_course_map = {}
        for t in active_topics:
            course = t.course
            if course:
                topic_course_map[t.id] = course.code
            elif t.course_type:
                topic_course_map[t.id] = t.course_type
            else:
                topic_course_map[t.id] = None
        
        # Admin uchun yig'ma hisobot
        students_with_unsubmitted = []

        for student in students:
            try:
                # Studentning barcha guruhlarini olamiz (prefetch_related ishlatganimiz uchun tez)
                all_groups = student.get_all_groups()
                if not all_groups:
                    continue
                
                # Student kurslarini yig'amiz
                student_courses = set()
                for grp in all_groups:
                    if grp.course:
                        student_courses.add(grp.course.code)
                    elif grp.course_type:
                        student_courses.add(grp.course_type)
                
                if not student_courses:
                    continue
                
                # Student kurslariga mos topiclarni filter qilamiz (client-side, chunki allaqachon cached)
                filtered_topics = [
                    t for t in active_topics
                    if topic_course_map.get(t.id) in student_courses
                ]
                
                # Har bir mavzu uchun vazifa yuborilganini tekshiramiz
                unsubmitted = []
                for topic in filtered_topics:
                    expected_task_type = 'test' if topic.correct_answers else 'assignment'
                    
                    # Task mavjudligini tekshiramiz
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
                    # Student ma'lumotlari allaqachon prefetch_related orqali olindi
                    student_tg_id = student.telegram_id
                    student_full_name = student.full_name
                    
                    # Xabar uchun ma'lumotlarni to'plamiz (prefetch_related ishlatganimiz uchun tez)
                    unsubmitted_info = [
                        {
                            'title': t.title,
                            'deadline': t.deadline
                        }
                        for t in unsubmitted
                    ]
                    
                    msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo'yicha vazifa topshirmagansiz!\n"
                    msg += "\n".join([
                        f"- {info['title']}" + (f" (Deadline: {info['deadline'].strftime('%d.%m.%Y %H:%M')})" if info['deadline'] else "")
                        for info in unsubmitted_info
                    ])
                    await safe_send_message(student_tg_id, msg)
                    
                    # 3 tadan ko'p bo'lsa, admin uchun yig'ma hisobotga qo'shamiz
                    if len(unsubmitted) >= 3:
                        students_with_unsubmitted.append({
                            'full_name': student_full_name,
                            'telegram_id': student_tg_id,
                            'unsubmitted_count': len(unsubmitted),
                            'unsubmitted_info': unsubmitted_info
                        })
            except Exception as e:
                print(f"⚠️ Student {student.telegram_id} uchun eslatma yuborishda xatolik: {e}")
                continue
        
        # ✨ YANGI: Barcha studentlar uchun yig'ma hisobot adminlarga yuborish
        # Admin uchun yig'ma hisobotni yuborish (har 20 student)
        if students_with_unsubmitted:
            batch_size = 20
            for i in range(0, len(students_with_unsubmitted), batch_size):
                batch = students_with_unsubmitted[i:i+batch_size]
                msg = f"🚨 <b>Vazifa topshirmaganlar hisobot (batch {i//batch_size+1})</b>\n\n"
                for s in batch:
                    msg += f"<b>{s['full_name']}</b> (<code>{s['telegram_id']}</code>) - <b>{s['unsubmitted_count']}</b> ta\n"
                    for info in s['unsubmitted_info']:
                        msg += f"  • {info['title']}"
                        if info['deadline']:
                            msg += f" (Deadline: {info['deadline'].strftime('%d.%m.%Y %H:%M')})"
                        msg += "\n"
                    # Chatga o'tish tugmasi
                    msg += f"<a href='tg://user?id={s['telegram_id']}'>Chatga o'tish</a>\n\n"
                # Inline tugma emas, HTML link
                for admin_id in ADMINS:
                    try:
                        await bot.send_message(admin_id, msg, parse_mode="HTML", disable_web_page_preview=True)
                    except Exception as e:
                        print(f"⚠️ Admin {admin_id} ga yig'ma hisobot yuborishda xatolik: {e}")
        
    except Exception as e:
        print(f"❌ Eslatma yuborishda xatolik: {e}")
