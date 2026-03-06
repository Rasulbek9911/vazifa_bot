"""
Scheduled tasks: weekly reports, unsubmitted task warnings
"""
import aiohttp
import logging
from data.config import ADMINS, API_BASE_URL
from loader import bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message

# Logger setup
logger = logging.getLogger(__name__)


# --- Haftalik report ---
async def send_weekly_reports():
    """Har hafta guruh bo'yicha PDF report yuborish (faqat active mavzu bo'lsa)"""
    logger.info("📊 Haftalik report yuborish jarayoni boshlandi")
    try:
        timeout = aiohttp.ClientTimeout(total=60)  # 60 sekund timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Guruhlarni olib kelamiz
            try:
                async with session.get(f"{API_BASE_URL}/groups/") as resp:
                    if resp.status != 200:
                        logger.error(f"❌ API dan guruhlarni olishda xatolik: status={resp.status}")
                        return
                    groups = await resp.json()
                    logger.info(f"✅ {len(groups)} ta guruh topildi")
            except Exception as e:
                logger.error(f"❌ API ga ulanishda xatolik: {e}")
                return
            
            success_count = 0
            fail_count = 0
            
            for g in groups:
                chat_id = g.get("telegram_group_id")
                group_id = g["id"]
                group_name = g.get("name", "Noma'lum")

                if not chat_id:
                    logger.warning(f"⚠️ Guruh {group_name} (ID: {group_id}) uchun telegram_group_id yo'q")
                    continue

                try:
                    # PDF reportni olib kelamiz (oxirgi 10 ta topic + umumiy o'rtacha)
                    async with session.get(f"{API_BASE_URL}/reports/{group_id}/weekly/pdf/") as resp:
                        if resp.status == 200:
                            pdf_bytes = await resp.read()
                            await bot.send_document(
                                chat_id,
                                ("weekly_report.pdf", pdf_bytes),
                                caption=f"📊 {group_name} guruhining haftalik hisobot"
                            )
                            success_count += 1
                            logger.info(f"✅ Guruh {group_name} uchun PDF yuborildi")
                        elif resp.status == 404:
                            logger.warning(f"⚠️ Guruh {group_name} uchun PDF topilmadi (404)")
                        else:
                            logger.error(f"❌ Guruh {group_name} uchun PDF olishda xatolik: status={resp.status}")
                            fail_count += 1
                except Exception as e:
                    logger.error(f"❌ Guruh {group_name} uchun PDF yuborishda xatolik: {e}", exc_info=True)
                    fail_count += 1
                    continue
                    
            logger.info(f"📊 Haftalik report yakunlandi: {success_count} muvaffaqiyatli, {fail_count} xatolik")
    except Exception as e:
        logger.error(f"❌ Haftalik report yuborishda critical xatolik: {e}", exc_info=True)
                    

# --- Vazifa topshirmaganlarga eslatma ---
async def send_unsubmitted_warnings():
    """Active mavzular bo'yicha vazifa topshirmagan studentlarga eslatma yuborish"""
    logger.info("⚠️ Vazifa topshirmaganlarga eslatma yuborish jarayoni boshlandi")
    try:
        from base_app.models import Student, Topic, Task
        from django.utils import timezone
        from django.db import close_old_connections
        import asyncio

        close_old_connections()

        # ⚡ OPTIMIZATSIYA: Barcha ma'lumotlarni bitta querysetda prefetch qilamiz
        students = await sync_to_async(list)(
            Student.objects.all()
            .prefetch_related('groups__course')
            .only('id', 'telegram_id', 'full_name')
        )
        
        # Active topiclarni bir marta olamiz (har student uchun qayta-qayta emas)
        active_topics = await sync_to_async(list)(
            Topic.objects.filter(is_active=True)
            .select_related('course')
            .only('id', 'title', 'deadline', 'correct_answers', 'course')
        )
        
        # Har bir topic uchun course ma'lumotlarini oldindan olamiz
        topic_course_map = {}
        for t in active_topics:
            course = t.course
            if course:
                topic_course_map[t.id] = course.code
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
                    # Timezone ni local vaqtga o'tkazish
                    import pytz
                    local_tz = pytz.timezone('Asia/Tashkent')
                    
                    unsubmitted_info = [
                        {
                            'title': t.title,
                            'deadline': t.deadline.astimezone(local_tz) if t.deadline else None
                        }
                        for t in unsubmitted
                    ]
                    
                    msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo'yicha vazifa topshirmagansiz!\n"
                    msg += "\n".join([
                        f"- {info['title']}" + (f" (Deadline: {info['deadline'].strftime('%d.%m.%Y %H:%M')})" if info['deadline'] else "")
                        for info in unsubmitted_info
                    ])
                    await safe_send_message(student_tg_id, msg)
                    logger.info(f"✅ Student {student_full_name} ({student_tg_id}) ga eslatma yuborildi")
                    
                    # 3 tadan ko'p bo'lsa, admin uchun yig'ma hisobotga qo'shamiz
                    if len(unsubmitted) >= 3:
                        students_with_unsubmitted.append({
                            'full_name': student_full_name,
                            'telegram_id': student_tg_id,
                            'unsubmitted_count': len(unsubmitted),
                            'unsubmitted_info': unsubmitted_info
                        })
            except Exception as e:
                logger.error(f"⚠️ Student {student.telegram_id} uchun eslatma yuborishda xatolik: {e}", exc_info=True)
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
                        # Admin ID ni integer ga o'tkazish
                        admin_id_int = int(admin_id)
                        await bot.send_message(admin_id_int, msg, parse_mode="HTML", disable_web_page_preview=True)
                        logger.info(f"✅ Admin {admin_id} ga yig'ma hisobot yuborildi")
                    except Exception as e:
                        logger.error(f"⚠️ Admin {admin_id} ga yig'ma hisobot yuborishda xatolik: {e}", exc_info=True)
        
        logger.info(f"⚠️ Vazifa topshirmaganlarga eslatma yakunlandi: {len(students_with_unsubmitted)} student uchun hisobot yuborildi")
    except Exception as e:
        logger.error(f"❌ Eslatma yuborishda critical xatolik: {e}", exc_info=True)


# --- Deadline tugaganda batafsil javoblarni yuborish ---
async def send_deadline_results():
    """Deadline tugagan mavzular uchun test yechgan talabalar batafsil natijalarni oladi"""
    logger.info("📊 Deadline tugagan mavzular uchun batafsil natijalar yuborish boshlandi")
    try:
        from base_app.models import Topic, Task
        from django.utils import timezone
        from django.db import close_old_connections
        from datetime import datetime, timedelta
        import re
        import pytz

        close_old_connections()
        
        # Bugunning boshidan oxirigacha deadline tugagan topiclarni topamiz
        local_tz = pytz.timezone('Asia/Tashkent')
        now_local = timezone.now().astimezone(local_tz)
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        # Deadline bugun tugagan mavzularni olamiz
        expired_topics = await sync_to_async(list)(
            Topic.objects.filter(
                deadline__gte=today_start,
                deadline__lte=today_end,
                correct_answers__isnull=False  # Faqat test mavzulari
            ).exclude(correct_answers={})
        )
        
        if not expired_topics:
            logger.info("ℹ️ Bugun deadline tugagan mavzular yo'q")
            return
        
        logger.info(f"📋 {len(expired_topics)} ta mavzuda deadline bugun tugadi")
        
        total_sent = 0
        total_errors = 0
        
        for topic in expired_topics:
            topic_id = topic.id
            topic_title = topic.title
            correct_answers = topic.correct_answers
            
            logger.info(f"🔍 {topic_title} mavzusi uchun natijalarni yuborish...")
            
            # Bu mavzu bo'yicha test javoblarini yuborgan studentlarni topamiz 
            # FAQAT deadline tugamasidan oldin yuborgan talabalar uchun
            # (deadline dan keyin yechganlar allaqachon batafsil javoblarni ko'rgan)
            tasks = await sync_to_async(list)(
                Task.objects.filter(
                    topic_id=topic_id,
                    task_type='test',
                    test_answers__isnull=False,
                    submitted_at__lte=topic.deadline  # Faqat deadline dan oldin yuborgan
                ).exclude(test_answers='')
                .select_related('student')
                .only('id', 'test_code', 'test_answers', 'student__telegram_id', 'student__full_name', 'submitted_at')
            )
            
            if not tasks:
                logger.info(f"  ℹ️ {topic_title} uchun test javoblari topilmadi")
                continue
            
            logger.info(f"  📤 {len(tasks)} ta talabaga natija yuborilmoqda...")
            
            for task in tasks:
                try:
                    student_telegram_id = task.student.telegram_id
                    test_code = task.test_code
                    user_answer = task.test_answers
                    submitted_at = task.submitted_at
                    
                    # To'g'ri javoblarni topamiz
                    if test_code not in correct_answers:
                        logger.warning(f"  ⚠️ Test kod {test_code} uchun to'g'ri javob topilmadi")
                        continue
                    
                    correct = correct_answers[test_code].lower().strip()
                    user_answer = user_answer.lower().strip()
                    
                    # Parse admin correct answers
                    correct_answers_list = []
                    has_numbers = bool(re.search(r'\d', correct))
                    
                    if has_numbers:
                        for match in re.finditer(r'\d+([a-zx]+)', correct):
                            answers = match.group(1)
                            if answers == 'x':
                                correct_answers_list.append(['x'])
                            else:
                                correct_answers_list.append(list(answers))
                    elif re.match(r'^[a-zx]+$', correct):
                        correct_answers_list = [[ch] for ch in correct]
                    else:
                        filtered = ''.join(ch for ch in correct if ch.isalpha() or ch == 'x')
                        correct_answers_list = [[ch] for ch in filtered]
                    
                    # Parse student answers
                    student_answers_list = []
                    has_numbers_student = bool(re.search(r'\d', user_answer))
                    
                    if has_numbers_student:
                        for match in re.finditer(r'\d+([a-zx])', user_answer):
                            student_answers_list.append(match.group(1))
                    elif re.match(r'^[a-zx]+$', user_answer):
                        student_answers_list = list(user_answer)
                    else:
                        filtered = ''.join(ch for ch in user_answer if ch.isalpha() or ch == 'x')
                        student_answers_list = list(filtered)
                    
                    if len(correct_answers_list) != len(student_answers_list):
                        logger.warning(f"  ⚠️ Javoblar soni mos kelmaydi: {test_code}")
                        continue
                    
                    # Batafsil natijalarni tayyorlash
                    correct_count = 0
                    total_count = len(correct_answers_list)
                    result_text = f"📊 {topic_title} - Batafsil natijalar:\n\n"
                    result_text += f"🗓 <b>Deadline tugadi!</b> Sizning natijalaringiz:\n\n"
                    
                    for i in range(total_count):
                        student_ans = student_answers_list[i]
                        correct_ans_list = correct_answers_list[i]
                        
                        if student_ans in correct_ans_list:
                            result_text += f"{i+1}. ✅ {student_ans.upper()}\n"
                            correct_count += 1
                        else:
                            valid_answers = '/'.join([a.upper() for a in correct_ans_list])
                            result_text += f"{i+1}. ❌ {student_ans.upper()} (To'g'ri: {valid_answers})\n"
                    
                    percentage = (correct_count / total_count * 100) if total_count > 0 else 0
                    result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)"
                    
                    # Deadline dan oldin topshirgan (chunki filter qilganimiz)
                    result_text += f"\n⏰ Siz testni deadline tugamasidan oldin topshirgansiz."
                    final_grade = correct_count
                    result_text += f"\n🎯 Ball: {final_grade}/{total_count}"
                    
                    # Userga yuborish
                    await safe_send_message(student_telegram_id, result_text, parse_mode="HTML")
                    total_sent += 1
                    
                except Exception as e:
                    logger.error(f"  ❌ Student {student_telegram_id} ga natija yuborishda xatolik: {e}", exc_info=True)
                    total_errors += 1
                    continue
            
            logger.info(f"  ✅ {topic_title} uchun natijalar yuborildi")
        
        logger.info(f"📊 Deadline natijalarini yuborish yakunlandi: {total_sent} yuborildi, {total_errors} xato")
        
        # Adminga hisobot
        if total_sent > 0:
            report_msg = (
                f"📊 <b>Deadline natijalar hisobot</b>\n\n"
                f"📤 Yuborilgan: {total_sent}\n"
                f"❌ Xatolar: {total_errors}\n"
                f"📋 Mavzular: {len(expired_topics)}"
            )
            for admin_id in ADMINS:
                try:
                    await bot.send_message(int(admin_id), report_msg, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"⚠️ Admin {admin_id} ga hisobot yuborishda xatolik: {e}")
        
    except Exception as e:
        logger.error(f"❌ Deadline natijalarini yuborishda critical xatolik: {e}", exc_info=True)
