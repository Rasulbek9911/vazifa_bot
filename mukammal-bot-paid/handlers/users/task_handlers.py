"""
Task submission handlers: task sending, topic selection, file upload
Single group with approval link (200 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
import re
import json
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from data.config import ADMINS, API_BASE_URL, MILLIY_ADMIN, ATTESTATSIYA_ADMIN
from loader import dp, bot
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from filters.is_private import IsPrivate


# General channel/group ID is configured in data.config


@dp.message_handler(IsPrivate(), Text(equals="📝 Test yuborish"))
async def send_test(message: types.Message, state: FSMContext):
    await state.update_data(task_type="test")
    # ✨ YANGI: Avvali course_type tanlash
    await _ask_course_type(message, state, "📝 Test")

@dp.message_handler(IsPrivate(), Text(equals="📋 Maxsus topshiriq yuborish"))
async def send_assignment(message: types.Message, state: FSMContext):
    await state.update_data(task_type="assignment")
    # ✨ YANGI: Avvali course_type tanlash
    await _ask_course_type(message, state, "📋 Maxsus topshiriq")

async def _ask_course_type(message: types.Message, state: FSMContext, task_name: str):
    """Course type (milliy_sert / attestatsiya) tanlash"""
    telegram_id = message.from_user.id
    
    # Adminlarni tekshirish - adminlar vazifa yubormaydi
    if str(telegram_id) in ADMINS:
        await message.answer("ℹ️ Adminlar vazifa yubora olmaydi.")
        return

    # Studentni tekshirish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{telegram_id}/") as resp:
            if resp.status != 200:
                await message.answer(
                    "❌ Siz ro'yxatdan o'tmagansiz!\n\n"
                    "📝 /start ni bosib ro'yxatdan o'ting."
                )
                return
            student_data = await resp.json()
            
            # ✨ YANGI: Studentning barcha guruhlarini olamiz
            from base_app.models import Student
            from asgiref.sync import sync_to_async
            
            @sync_to_async
            def get_student_groups_and_courses(telegram_id):
                """Student guruh va kurslarini olish (async-safe)"""
                student_obj = Student.objects.get(telegram_id=telegram_id)
                all_groups = student_obj.get_all_groups()
                
                if not all_groups:
                    return None, None
                
                student_courses = set()
                for grp in all_groups:
                    if grp.course:
                        student_courses.add(grp.course.code)
                    elif grp.course_type:
                        student_courses.add(grp.course_type)
                
                return list(all_groups), list(student_courses)
            
            all_groups, student_courses = await get_student_groups_and_courses(telegram_id)
            
            if all_groups is None:
                await message.answer(
                    "❌ Sizga guruh biriktirilmagan!\n\n"
                    "📝 /start ni bosib qayta ro'yxatdan o'ting."
                )
                return
            
            if not student_courses:
                await message.answer("❌ Sizning kurs turi aniqlanmadi!")
                return
    
    # Student ma'lumotlarini saqla va davom et
    await state.update_data(
        student_data=student_data,
        student_courses=student_courses,  # Ko'p kurs
        all_groups=all_groups
    )
    
    # Guruhga qo'shilganligini tekshirish
    await _check_group_and_send_topics(message, state, task_name)

async def _check_group_and_send_topics(message: types.Message, state: FSMContext, task_name: str):
    """Guruhga qo'shilganligini tekshir va mavzularni yuborish"""
    telegram_id = message.from_user.id
    data = await state.get_data()
    
    student_data = data.get("student_data", {})
    all_groups = data.get("all_groups", [])
    student_courses = data.get("student_courses", [])
    
    # ✨ YANGI: Har bir guruhga qo'shilganligini tekshirish
    not_joined_groups = []
    kicked_from_groups = []
    
    for group_obj in all_groups:
        if not group_obj.telegram_group_id:
            continue
            
        try:
            bot_info = await bot.get_me()
            bot_member = await bot.get_chat_member(group_obj.telegram_group_id, bot_info.id)
            
            if bot_member.status in ["administrator", "creator"]:
                group_member = await bot.get_chat_member(group_obj.telegram_group_id, telegram_id)
                
                if group_member.status == "kicked":
                    kicked_from_groups.append(group_obj)
                elif group_member.status not in ["member", "administrator", "creator"]:
                    not_joined_groups.append(group_obj)
            else:
                not_joined_groups.append(group_obj)
        except Exception as e:
            print(f"❌ Guruh {group_obj.name} membership tekshiruvida xatolik: {e}")
            not_joined_groups.append(group_obj)
    
    # Agar hech bo'lmasa bitta guruhga qo'shilmagan bo'lsa
    if not_joined_groups or kicked_from_groups:
        msg = "⚠️ Siz ba'zi guruhlarga qo'shilmagansiz:\n\n"
        
        for grp in not_joined_groups:
            msg += f"❌ {grp.name}"
            if grp.invite_link:
                msg += f"\n   🔗 {grp.invite_link}"
            msg += "\n"
        
        if kicked_from_groups:
            msg += "\n🚫 Quyidagi guruhlardan chiqarilgansiz:\n"
            for grp in kicked_from_groups:
                msg += f"   • {grp.name}\n"
            msg += "\n📞 Admin bilan bog'lanib, qayta qo'shilishni so'rang.\n"
            
            # Adminlarga xabar
            admin_msg = (
                f"🔔 Kicked user qayta guruhlarga qo'shilmoqchi:\n\n"
                f"👤 User: {message.from_user.full_name}\n"
                f"🆔 ID: {telegram_id}\n"
                f"📱 Username: @{message.from_user.username or 'N/A'}\n\n"
                f"🔗 Guruhlar:\n"
            )
            for grp in kicked_from_groups:
                admin_msg += f"   • {grp.name}\n"
            admin_msg += "\n⚠️ Iltimos, userni guruhlarga qayta qo'shing (unban + invite)."
            
            for admin_id in ADMINS:
                try:
                    await bot.send_message(int(admin_id), admin_msg)
                except Exception:
                    pass
        
        msg += "\n⚠️ Barcha guruhlarga qo'shilgandan keyin vazifa yuborishingiz mumkin.\n"
        await message.answer(msg)
        return
    
    # 1️⃣ Mavzularni olish (barcha kurslar uchun)
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/?student_id={telegram_id}") as resp:
            active_topics = await resp.json()
        if not active_topics:
            await message.answer(f"❌ Hozirda siz uchun active mavzu yo'q!")
            return

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()
    
    # Hozirgi vazifa turini olamiz
    task_type = data.get("task_type", "test")

    # 3️⃣ Faqat shu task_type uchun yuborilgan mavzularni filter qilamiz
    # ✨ YANGI: Barcha kurslar uchun
    submitted_topic_ids = {
        task["topic"]["id"] 
        for task in submitted_tasks 
        if task.get("task_type") == task_type
    }

    # 4️⃣ Faqat yubormagan active mavzularni filter qilamiz (barcha kurslar uchun)
    available_topics = []
    for t in active_topics:
        if t["id"] in submitted_topic_ids:
            continue
        
        # Mavzuning kursini aniqlaymiz
        topic_course_code = None
        if t.get("course"):
            topic_course_code = t["course"]["code"]
        elif t.get("course_type"):
            topic_course_code = t["course_type"]
        
        # Agar topic student kurslarida bo'lsa, qo'shamiz
        if topic_course_code in student_courses:
            available_topics.append(t)

    if not available_topics:
        task_name_lower = "test" if task_type == "test" else "maxsus topshiriq"
        await message.answer(f"✅ Siz barcha active mavzular uchun {task_name_lower} yuborgansiz!")
        return

    # ✨ YANGI: Kurs bo'yicha grouping qilamiz
    topics_by_course = {}
    for t in available_topics:
        course_code = t.get("course", {}).get("code") if t.get("course") else t.get("course_type", "attestatsiya")
        course_name = t.get("course", {}).get("name") if t.get("course") else ("Milliy Sertifikat" if course_code == "milliy_sert" else "Attestatsiya")
        
        if course_code not in topics_by_course:
            topics_by_course[course_code] = {
                "name": course_name,
                "topics": []
            }
        topics_by_course[course_code]["topics"].append(t)
    
    # Inline keyboard - kurs bo'yicha
    kb = types.InlineKeyboardMarkup()
    for course_code, course_data in topics_by_course.items():
        kb.add(types.InlineKeyboardButton(
            text=f"📚 {course_data['name']}",
            callback_data=f"dummy"  # Faqat label
        ))
        for t in course_data["topics"]:
            kb.add(types.InlineKeyboardButton(
                text=f"  • {t['title']}",
                callback_data=f"topic_{t['id']}"
            ))

    await message.answer(f"📚 {task_type} uchun mavzuni tanlang:", reply_markup=kb)
    await TaskState.topic.set()


# Dummy callback handler - kurs labellarini ignor qilish
@dp.callback_query_handler(lambda c: c.data == "dummy", state=TaskState.topic)
async def ignore_dummy_callback(callback: types.CallbackQuery):
    """Kurs label tugmalarini bosganda hech narsa qilmaslik"""
    await callback.answer("ℹ️ Iltimos, mavzu tanlang", show_alert=False)


@dp.callback_query_handler(lambda c: c.data.startswith("topic_"), state=TaskState.topic)
async def process_topic(callback: types.CallbackQuery, state: FSMContext):
    topic_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    task_type = data.get("task_type", "test")
    
    # Topic dan correct_answers borligini tekshirish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/{topic_id}/") as resp:
            if resp.status != 200:
                await callback.message.answer("❌ Mavzu topilmadi!")
                await callback.answer()
                return
            
            topic = await resp.json()
            
            # Mavzuning turi (correct_answers bor bo'lsa test, yo'q bo'lsa maxsus topshiriq)
            topic_has_answers = bool(topic.get('correct_answers'))
    
    # Agar user test yubormoqchi, lekin mavzu maxsus topshiriq uchun (correct_answers yo'q)
    if task_type == "test" and not topic_has_answers:
        await callback.message.answer(
            "❌ Bu mavzu test uchun emas!\n\n"
            "📋 Bu mavzu maxsus topshiriq uchun.\n"
            "Iltimos, '📋 Maxsus topshiriq yuborish' tugmasini bosing."
        )
        await state.finish()
        await callback.answer()
        return
    
    # Agar user maxsus topshiriq yubormoqchi, lekin mavzu test uchun (correct_answers bor)
    if task_type == "assignment" and topic_has_answers:
        await callback.message.answer(
            "❌ Bu mavzu maxsus topshiriq uchun emas!\n\n"
            "📝 Bu mavzu test uchun.\n"
            "Iltimos, '📝 Test yuborish' tugmasini bosing."
        )
        await state.finish()
        await callback.answer()
        return
    
    await state.update_data(topic_id=topic_id)
    
    if task_type == "test":
        await callback.message.answer(
            "📝 Test javoblarini quyidagi formatda yuboring:\n\n"
            "📌 Format: test_kodi separator javoblar\n\n"
            "🔹 Test kodi: 1, 2, A, B, + va boshqalar\n"
            "🔹 Separator: - yoki + yoki *\n"
            "🔹 Javoblar: abc yoki 1a2b3c\n\n"
            "💡 Misol:\n"
            "• 1-abc (har bir harf ketma-ket savol)\n"
            "• 1+1a2b3c (raqam-harf formati)\n"
            "• A*1a2c3b4d (istalgan separator)\n\n"
            "⚠️ Agar bir savolda bir nechta to'g'ri javob bo'lsa,\n"
            "   birontasini yuboring. Misol: 1ab → 1a yoki 1b"
        )
    else:
        await callback.message.answer("📎 Endi faylni yuboring (rasm yoki hujjat).")
    
    await TaskState.file.set()
    await callback.answer()


# Test javoblarini qabul qilish
@dp.message_handler(state=TaskState.file, content_types=types.ContentTypes.TEXT)
async def process_test_answers(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type", "test")
    
    # Agar maxsus topshiriq bo'lsa, text qabul qilmaymiz
    if task_type != "test":
        await message.answer("❌ Maxsus topshiriq uchun fayl yuboring!")
        return
    
    topic_id = data["topic_id"]
    text = message.text.strip()
    
    # Text formatini tekshirish: "test_code separator javoblar"
    # Separator: -, + yoki *
    test_code = None
    test_answers = None
    
    for sep in ['-', '+', '*']:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                test_code = parts[0].strip()
                test_answers = parts[1].strip()
                break
    
    if not test_code or not test_answers:
        await message.answer(
            "❌ Noto'g'ri format!\n\n"
            "📌 To'g'ri format: test_kodi separator javoblar\n"
            "Separator: - yoki + yoki *\n\n"
            "💡 Misol:\n"
            "• 1-abc\n"
            "• 1+1a2c3b\n"
            "• A*abcd\n\n"
            "⚠️ Uchala separatordan birini ishlating!"
        )
        return
    
    # Topic dan to'g'ri javoblarni olish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/{topic_id}/") as resp_topics:
            if resp_topics.status != 200:
                await message.answer("❌ Mavzu topilmadi!")
                return
            
            current_topic = await resp_topics.json()
            correct_answers = current_topic.get('correct_answers') or {}
    
    # ✨ YANGI: Agar correct_answers mavjud bo'lsa, test kodi tekshiriladi
    if correct_answers:
        if test_code not in correct_answers:
            # Mavzuning barcha test kodlarini ko'rsatish
            topic_title = current_topic.get('title', 'Mavzu')
            all_test_codes = ", ".join(sorted(correct_answers.keys()))
            first_test_code = list(correct_answers.keys())[0] if correct_answers else "N/A"
            await message.answer(
                f"❌ Test kodi xato!\n\n"
                f"📚 Siz tanlagan mavzu: {topic_title}\n"
                f"✅ Test kodlari: {all_test_codes}\n\n"
                f"Format: test_kodi-javoblar\n"
                f"Misol: {first_test_code}-abc\n\n"
                f"Iltimos, to'g'ri formatda qayta yuboring:"
            )
            # State'da qolamiz - user qayta kiritishi mumkin
            return
    
    # Test javoblarini tekshirish
    if correct_answers and test_code in correct_answers:
        import re
        
        correct = correct_answers[test_code].lower().strip()
        user_answer = test_answers.lower().strip()
        
        # Parse admin correct answers (supports multi-correct: 1ab2x3abcd)
        correct_answers_list = []
        
        # Raqam bor-yo'qligini tekshirish
        has_numbers = bool(re.search(r'\d', correct))
        
        if has_numbers:
            # Format 2: 1a2b3c or 1ab2x3abcd -> [[a], [b], [c]] or [[a,b], [x], [a,b,c,d]]
            for match in re.finditer(r'\d+([a-zx]+)', correct):
                answers = match.group(1)
                if answers == 'x':
                    correct_answers_list.append(['x'])
                else:
                    correct_answers_list.append(list(answers))
        elif re.match(r'^[a-zx]+$', correct):
            # Format 1: abc -> [[a], [b], [c]]
            correct_answers_list = [[ch] for ch in correct]
        else:
            # Noma'lum format - barcha kichik harflarni olamiz
            filtered = ''.join(ch for ch in correct if ch.isalpha() or ch == 'x')
            correct_answers_list = [[ch] for ch in filtered]
        
        # Parse student answers (single answer per question)
        student_answers_list = []
        
        # Raqam bor-yo'qligini tekshirish
        has_numbers_student = bool(re.search(r'\d', user_answer))
        
        if has_numbers_student:
            # Format 2: 1a2b3c -> [a, b, c]
            # Raqamlar bor - formatli parse qilamiz: 1a2b3c
            for match in re.finditer(r'\d+([a-zx])', user_answer):
                student_answers_list.append(match.group(1))
        elif re.match(r'^[a-zx]+$', user_answer):
            # Format 1: abc -> [a, b, c]
            student_answers_list = list(user_answer)
        else:
            # Noma'lum format - barcha kichik harflarni olamiz
            filtered = ''.join(ch for ch in user_answer if ch.isalpha() or ch == 'x')
            student_answers_list = list(filtered)
        
        # Savol sonini tekshirish
        if len(correct_answers_list) != len(student_answers_list):
            await message.answer(
                f"❌ Javoblar soni noto'g'ri!\n\n"
                f"Kerakli javoblar soni: {len(correct_answers_list)}\n"
                f"Sizning javoblaringiz: {len(student_answers_list)}\n\n"
                f"Iltimos, to'g'ri formatda qayta yuboring.",
                reply_markup=vazifa_key
            )
            await state.finish()
            return
        
        # Har bir javobni tekshirish (multi-correct support)
        correct_count = 0
        total_count = len(correct_answers_list)
        
        # Deadline tekshiruvi va show_detailed_results maydonini tekshirish
        deadline_passed = False
        show_detailed = False  # Default: yashirin
        
        if current_topic.get('deadline'):
            from datetime import datetime
            deadline_str = current_topic['deadline']
            deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
            current_dt = datetime.now(deadline_dt.tzinfo)
            
            if current_dt > deadline_dt:
                deadline_passed = True
                show_detailed = True  # Deadline o'tgan - batafsil ko'rsatamiz
            else:
                show_detailed = False  # Deadline o'tmagan - javoblar yashirin
        else:
            # Deadline yo'q - show_detailed_results maydoniga qaraymiz
            show_detailed = current_topic.get('show_detailed_results', False)
        
        if show_detailed:
            # Batafsil natijalarni ko'rsatish (har bir savol uchun)
            result_text = "📊 Test natijalari:\n\n"
            
            for i in range(total_count):
                student_ans = student_answers_list[i]
                correct_ans_list = correct_answers_list[i]
                
                if student_ans in correct_ans_list:
                    result_text += f"{i+1}. ✅ {student_ans.upper()}\n"
                    correct_count += 1
                else:
                    # Show all valid answers
                    valid_answers = '/'.join([a.upper() for a in correct_ans_list])
                    result_text += f"{i+1}. ❌ {student_ans.upper()} (To'g'ri: {valid_answers})\n"
        else:
            # Faqat umumiy natijani ko'rsatish (batafsil emas)
            result_text = "📊 Test natijalari:\n\n"
            
            for i in range(total_count):
                student_ans = student_answers_list[i]
                correct_ans_list = correct_answers_list[i]
                
                if student_ans in correct_ans_list:
                    correct_count += 1
        
        # Foiz hisoblab userga ko'rsatish (baho ko'rsatmaslik)
        percentage = (correct_count / total_count * 100) if total_count > 0 else 0
        
        result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)"
        
        # Deadline dan keyin baho pasaytirish
        final_grade = correct_count
        
        if deadline_passed:
            # 80% ball berish
            final_grade = int(correct_count * 0.8)
            result_text += f"\n\n⏰ Deadline o'tgan! Ball 80% ga tushirildi: {final_grade}/{total_count}"
        
        await message.answer(result_text, reply_markup=vazifa_key)
        
        # DBga saqlash - grade qismiga to'g'ri javoblar soni (yoki 80% agar deadline o'tgan bo'lsa)
        # course_type ni yubormaymiz, backend topic.course dan oladi
        # ✅ IMPORTANT: test_answers faqat javoblar bo'lishi kerak (test_code-javoblar emas!)
        payload = {
            "student_id": message.from_user.id,
            "topic_id": topic_id,
            "task_type": "test",
            "test_code": test_code,
            "test_answers": test_answers,  # Faqat javoblar: "abc" yoki "dbcaa..."
            "grade": final_grade  # To'g'ri javoblar soni yoki 80% agar deadline o'tgan
        }
    else:
        # To'g'ri javoblar mavjud emas - oddiy saqlash
        await message.answer("✅ 📝 Test javoblari yuborildi! Admin tekshiradi.", reply_markup=vazifa_key)
        
        payload = {
            "student_id": message.from_user.id,
            "topic_id": topic_id,
            "task_type": "test",
            "test_code": test_code,
            "test_answers": test_answers
        }
    
    # DBga saqlash
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/tasks/submit/", json=payload) as resp:
            if resp.status != 201:
                error_text = await resp.text()
                print(f"❌ Test saqlashda xatolik. Status: {resp.status}, Error: {error_text}")
                print(f"Payload: {payload}")
                
                # Parse JSON error if possible
                try:
                    import json
                    error_data = json.loads(error_text)
                    error_detail = str(error_data)
                except:
                    error_detail = error_text[:200]
                
                await message.answer(
                    f"❌ Test javoblarini saqlashda xatolik!\n\n"
                    f"Status: {resp.status}\n"
                    f"Xato: {error_detail}\n\n"
                    f"Iltimos, admin bilan bog'laning.",
                    reply_markup=vazifa_key
                )
    
    await state.finish()


# Maxsus topshiriq uchun fayl qabul qilish
@dp.message_handler(content_types=["document", "photo"], state=TaskState.file)
async def process_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    task_type = data.get("task_type", "test")
    
    # Agar test bo'lsa, fayl qabul qilmaymiz
    if task_type == "test":
        await message.answer("❌ Test uchun matn yuboring, fayl emas!")
        return
    topic_id = data["topic_id"]
    task_type = data.get("task_type", "test")

    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        file_id = message.photo[-1].file_id
        file_type = "photo"

    # course_type ni yubormaymiz, backend topic.course dan oladi
    payload = {
        "student_id": message.from_user.id,  # telegram_id
        "topic_id": topic_id,
        "task_type": task_type,
        "file_link": file_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/tasks/submit/", json=payload) as resp:
            if resp.status == 201:
                data = await resp.json()
                task_id = data["id"]
                student_name = data["student"]["full_name"]
                
                # Birinchi guruhni olish
                all_groups = data["student"].get("all_groups", [])
                group_name = all_groups[0]["name"] if all_groups else "N/A"
                
                topic_title = data["topic"]["title"]

                # ✅ Studenta javob
                await message.answer(f"✅ 📋 Maxsus topshiriq yuborildi!", reply_markup=vazifa_key)

                # ✅ Admin uchun inline keyboard (faqat maxsus topshiriq uchun)
                kb = InlineKeyboardMarkup(row_width=3)
                kb.add(
                    InlineKeyboardButton("3️⃣", callback_data=f"grade_{task_id}_3"),
                    InlineKeyboardButton("4️⃣", callback_data=f"grade_{task_id}_4"),
                    InlineKeyboardButton("5️⃣", callback_data=f"grade_{task_id}_5"),
                )

                caption = (
                    f"📋 Yangi maxsus topshiriq!\n\n"
                    f"👤 Student: {student_name}\n"
                    f"👥 Guruh: {group_name}\n"
                    f"📚 Mavzu: {topic_title}\n"
                )

                # ✨ Topic'dan course ma'lumotlarini olamiz va course adminiga yuboramiz
                topic_data = data["topic"]
                course_admin_id = None
                
                # Agar topic.course mavjud bo'lsa, course adminini olamiz
                if topic_data.get("course"):
                    course_admin_id = topic_data["course"].get("admin_telegram_id")
                
                # Fallback: eski MILLIY_ADMIN va ATTESTATSIYA_ADMIN
                if not course_admin_id:
                    topic_course_type = topic_data.get("course_type", "milliy_sert")
                    course_admin_id = MILLIY_ADMIN if topic_course_type == "milliy_sert" else ATTESTATSIYA_ADMIN
                
                # Adminlarga ham yuboramiz (barcha adminlar ko'rishi uchun)
                admins_to_notify = [course_admin_id] + ADMINS
                admins_to_notify = list(set(admins_to_notify))  # Dublikatlarni olib tashlash
                
                for admin_id in admins_to_notify:
                    try:
                        if file_type == "document":
                            await bot.send_document(admin_id, file_id, caption=caption, reply_markup=kb)
                        else:
                            await bot.send_photo(admin_id, file_id, caption=caption, reply_markup=kb)
                    except Exception as e:
                        print(f"❌ Admin {admin_id} ga yuborishda xato: {e}")

            else:
                error_text = await resp.text()
                print(f"❌ Vazifa saqlashda xatolik. Status: {resp.status}, Error: {error_text}")
                print(f"Payload: {payload}")
                
                # Parse JSON error if possible
                try:
                    import json
                    error_data = json.loads(error_text)
                    error_detail = str(error_data)
                except:
                    error_detail = error_text[:200]
                
                await message.answer(
                    f"❌ Vazifa yuborishda xatolik bo'ldi!\n\n"
                    f"Status: {resp.status}\n"
                    f"Xato: {error_detail}\n\n"
                    f"Iltimos, admin bilan bog'laning.",
                    reply_markup=vazifa_key
                )

    try:
        await state.finish()
    except:
        pass


# --- ADMIN TEST QO'SHISH ---
@dp.message_handler(IsPrivate(), Command("addtest"), user_id=ADMINS)
async def admin_add_test_start(message: types.Message, state: FSMContext):
    # Faqat adminlar
    try:
        await state.finish()
    except Exception:
        pass
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()
    if not topics:
        await message.answer("❌ Mavzular topilmadi.")
        return
    kb = types.InlineKeyboardMarkup()
    for t in topics:
        kb.add(types.InlineKeyboardButton(text=t["title"], callback_data=f"addtest_topic_{t['id']}"))
    await message.answer("📝 Test qo'shmoqchi bo'lgan mavzuni tanlang:", reply_markup=kb)
    await state.set_state("addtest_topic")

@dp.callback_query_handler(lambda c: c.data.startswith("addtest_topic_"), state="addtest_topic")
async def admin_add_test_topic(callback: types.CallbackQuery, state: FSMContext):
    topic_id = int(callback.data.split("_")[-1])
    await state.update_data(topic_id=topic_id)
    await callback.message.answer("Test kodi (masalan: 1, A, +) ni kiriting:")
    await state.set_state("addtest_code")
    await callback.answer()

@dp.message_handler(IsPrivate(), state="addtest_code", user_id=ADMINS)
async def admin_add_test_code(message: types.Message, state: FSMContext):
    test_code = message.text.strip()
    data = await state.get_data()
    topic_id = data["topic_id"]
    
    # Avval mavzudan eski testlarni tekshiramiz
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/{topic_id}/") as resp:
            if resp.status != 200:
                await message.answer("❌ Mavzu topilmadi!")
                try:
                    await state.finish()
                except KeyError:
                    pass
                return
            topic = await resp.json()
        
        correct_answers = topic.get("correct_answers") or {}
        
        # Agar bu test kodi allaqachon mavjud bo'lsa, ogohlantirish
        if test_code in correct_answers:
            await state.update_data(test_code=test_code, overwrite_warning=True)
            await message.answer(
                f"⚠️ Diqqat! Bu mavzuda '{test_code}' test kodi allaqachon mavjud:\n"
                f"Eski javob: {correct_answers[test_code]}\n\n"
                f"Yangi javobni kiritishda davom etsangiz, eski test o'chiriladi va yangi test qo'shiladi.\n\n"
                f"Yangi javobni kiriting yoki /cancel ni bosib bekor qiling:"
            )
            await state.set_state("addtest_answer")
            return
    
    await state.update_data(test_code=test_code)
    await message.answer(
        "✅ To'g'ri javobni kiriting.\n"
        "\n"
        "📝 Formatlar:\n"
        "1️⃣ Oddiy format: abc\n"
        "   • Har bir harf ketma-ket savol\n"
        "   • Misol: abcdabcd (8 ta savol)\n"
        "\n"
        "2️⃣ Raqam-harf formati: 1a2b3c\n"
        "   • Raqam = savol, harf = javob\n"
        "   • Misol: 1a2c3b4d5a (5 ta savol)\n"
        "\n"
        "3️⃣ Ko'p to'g'ri javob: 1ab2x3abcd\n"
        "   • 1ab = 1-savolda a yoki b to'g'ri\n"
        "   • 2x = 2-savolda to'g'ri javob yo'q\n"
        "   • 3abcd = 3-savolda a/b/c/d to'g'ri\n"
        "\n"
        "⚠️ Studentlar bitta javob yuboradi:\n"
        "• Format: test_kodi-javoblar\n"
        "• Misol: 1-abc yoki 1-1a2b3c"
    )
    await state.set_state("addtest_answer")

@dp.message_handler(IsPrivate(), state="addtest_answer", user_id=ADMINS)
async def admin_add_test_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    topic_id = data["topic_id"]
    test_code = data["test_code"]
    correct_answer = message.text.strip()
    overwrite_warning = data.get("overwrite_warning", False)
    
    # API orqali correct_answers ni yangilash
    async with aiohttp.ClientSession() as session:
        # Avval eski correct_answers ni olish
        async with session.get(f"{API_BASE_URL}/topics/{topic_id}/") as resp:
            if resp.status != 200:
                await message.answer("❌ Mavzu topilmadi!")
                try:
                    await state.finish()
                except KeyError:
                    pass
                return
            topic = await resp.json()
        
        correct_answers = topic.get("correct_answers") or {}
        
        # Agar overwrite_warning bo'lsa, eski testni o'chiramiz
        if overwrite_warning:
            old_answer = correct_answers.get(test_code, "N/A")
            correct_answers[test_code] = correct_answer
            
            # PATCH request
            async with session.patch(f"{API_BASE_URL}/topics/{topic_id}/", json={"correct_answers": correct_answers}) as resp2:
                if resp2.status == 200:
                    await message.answer(
                        f"✅ Test yangilandi!\n\n"
                        f"Test kodi: {test_code}\n"
                        f"Eski javob: {old_answer}\n"
                        f"Yangi javob: {correct_answer}"
                    )
                else:
                    await message.answer("❌ Test qo'shishda xatolik!")
        else:
            # Oddiy qo'shish
            correct_answers[test_code] = correct_answer
            
            # PATCH request
            async with session.patch(f"{API_BASE_URL}/topics/{topic_id}/", json={"correct_answers": correct_answers}) as resp2:
                if resp2.status == 200:
                    await message.answer(f"✅ Test qo'shildi: {test_code} → {correct_answer}")
                else:
                    await message.answer("❌ Test qo'shishda xatolik!")
    
    try:
        await state.finish()
    except KeyError:
        pass


# --- DEADLINE TUGAGANDAN KEYIN AVVALGI USERLARGA BATAFSIL NATIJALARNI YUBORISH ---
@dp.message_handler(IsPrivate(), Command("send_past_results"), user_id=ADMINS)
async def admin_send_past_results(message: types.Message, state: FSMContext):
    """
    Deadline tugagan mavzular uchun avval test yechgan userlarga batafsil natijalarni yuborish
    /send_past_results
    """
    try:
        await state.finish()
    except Exception:
        pass
    
    await message.answer("⏳ Deadline tugagan mavzularni qidiryapman...")
    
    # Deadline tugagan mavzularni topish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            if resp.status != 200:
                await message.answer("❌ Mavzularni olishda xatolik!")
                return
            all_topics = await resp.json()
    
    from datetime import datetime
    import pytz
    
    sent_count = 0
    error_count = 0
    
    for topic in all_topics:
        if not topic.get('deadline') or not topic.get('correct_answers'):
            continue
        
        # Deadline tekshirish
        deadline_str = topic['deadline']
        deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
        current_dt = datetime.now(pytz.UTC)
        
        # Faqat deadline tugagan mavzular
        if current_dt <= deadline_dt:
            continue
        
        # Bu mavzu uchun deadline tugashidan oldin test yechgan userlarni topish
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/tasks/") as resp:
                if resp.status != 200:
                    continue
                all_tasks = await resp.json()
        
        # Bu mavzu uchun test task'larni filter
        topic_id = topic['id']
        topic_title = topic['title']
        correct_answers = topic['correct_answers']
        
        for task in all_tasks:
            if task['topic']['id'] != topic_id:
                continue
            if task['task_type'] != 'test':
                continue
            if not task.get('test_code') or not task.get('test_answers'):
                continue
            
            # Task deadline tugashidan oldin yuboriganligini tekshirish
            task_created = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00'))
            if task_created > deadline_dt:
                continue  # Deadline tugagandan keyin yuborilgan - avval batafsil ko'rgan
            
            # Userga batafsil natijalarni hisoblash
            student_telegram_id = task['student']['telegram_id']
            test_code = task['test_code']
            test_answers = task['test_answers']
            
            if test_code not in correct_answers:
                continue
            
            # Parse answers (oldingi koddan copy)
            correct = correct_answers[test_code].lower().strip()
            user_answer = test_answers.lower().strip()
            
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
                continue
            
            # Batafsil natijalarni tayyorlash
            correct_count = 0
            total_count = len(correct_answers_list)
            result_text = f"📊 {topic_title} - Batafsil natijalar:\n\n"
            result_text += f"🗓 Deadline tugadi. Sizning natijalaringiz:\n\n"
            
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
            final_grade = int(correct_count * 0.8)  # 80% ball
            
            result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)"
            result_text += f"\n⏰ Deadline tugagandan oldin topshirgan edingiz."
            result_text += f"\n🎯 Ball (80%): {final_grade}/{total_count}"
            
            # Userga yuborish
            try:
                await bot.send_message(int(student_telegram_id), result_text)
                sent_count += 1
            except Exception as e:
                print(f"❌ Userga yuborishda xatolik {student_telegram_id}: {e}")
                error_count += 1
    
    await message.answer(
        f"✅ Yuborildi!\n\n"
        f"📤 Yuborilgan xabarlar: {sent_count}\n"
        f"❌ Xatolar: {error_count}"
    )
