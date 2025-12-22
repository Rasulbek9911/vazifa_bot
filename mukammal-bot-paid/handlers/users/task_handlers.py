"""
Task submission handlers: task sending, topic selection, file upload
Single group with approval link (200 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
import re
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
            group_id = student_data.get("group", {}).get("id")
            
            if not group_id:
                await message.answer(
                    "❌ Sizga guruh biriktirilmagan!\n\n"
                    "📝 /start ni bosib qayta ro'yxatdan o'ting."
                )
                return
        
        # Guruh ma'lumotlarini olish va course_type aniqla
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
            
        group_obj = next((g for g in groups if g["id"] == group_id), None)
        student_course_type = group_obj.get("course_type") if group_obj else None
        
        if not student_course_type:
            await message.answer("❌ Sizning kurs turi aniqlanmadi!")
            return
    
    # Course type ma'lumotini saqla va davom et
    await state.update_data(
        student_data=student_data,
        student_course_type=student_course_type,
        group_obj=group_obj
    )
    
    # Guruhga qo'shilganligini tekshirish
    await _check_group_and_send_topics(message, state, task_name)

async def _check_group_and_send_topics(message: types.Message, state: FSMContext, task_name: str):
    """Guruhga qo'shilganligini tekshir va mavzularni yuborish"""
    telegram_id = message.from_user.id
    data = await state.get_data()
    
    student_data = data.get("student_data", {})
    group_id = student_data.get("group", {}).get("id")
    group_obj = data.get("group_obj", {})
    student_course_type = data.get("student_course_type", "attestatsiya")
    
    # Guruhga qo'shilganligini tekshirish
    group_not_joined = True
    
    if group_obj and group_obj.get("telegram_group_id"):
        try:
            bot_info = await bot.get_me()
            bot_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), bot_info.id)
            
            if bot_member.status in ["administrator", "creator"]:
                group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                if group_member.status in ["member", "administrator", "creator"]:
                    group_not_joined = False
        except Exception as e:
            print(f"❌ Guruh membership tekshiruvida xatolik: {e}")
    
    if group_not_joined:
        msg = "❌ Siz guruhga qo'shilmagansiz!\n\n"
        
        if group_obj and group_obj.get("telegram_group_id"):
            user_status = None
            try:
                bot_info = await bot.get_me()
                bot_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), bot_info.id)
                
                if bot_member.status in ["administrator", "creator"]:
                    user_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                    user_status = user_member.status
            except Exception:
                pass
            
            if user_status == "kicked":
                msg += "⚠️ Siz guruhdan chiqarilgansiz.\n"
                msg += "📞 Admin bilan bog'lanib, qayta qo'shilishni so'rang.\n\n"
                
                admin_msg = (
                    f"🔔 Kicked user qayta guruhga qo'shilmoqchi:\n\n"
                    f"👤 User: {message.from_user.full_name}\n"
                    f"🆔 ID: {telegram_id}\n"
                    f"📱 Username: @{message.from_user.username or 'N/A'}\n\n"
                    f"🔗 Guruh: {group_obj['name']}\n\n"
                    f"⚠️ Iltimos, userni guruhga qayta qo'shing (unban + invite)."
                )
                for admin_id in ADMINS:
                    try:
                        await bot.send_message(int(admin_id), admin_msg)
                    except Exception:
                        pass
            else:
                if group_obj.get("invite_link"):
                    msg += f"🔗 Guruh: {group_obj.get('invite_link')}\n"
                    msg += f"   (Qo'shilish uchun bosing)\n\n"
        
        msg += "⚠️ Guruhga qo'shilgandan keyin vazifa yuborishingiz mumkin.\n"
        await message.answer(msg)
        return
    
    # 1️⃣ Mavzularni olish va filterlash
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()
        
        # Faqat active va studentning kurs uchun bo'lgan mavzularni olamiz
        active_topics = [
            t for t in topics 
            if t.get("is_active", False) and t.get("course_type") == student_course_type
        ]
        
        if not active_topics:
            await message.answer(f"❌ Hozirda sizning kurs uchun active mavzu yo'q!")
            return

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()
    
    # Hozirgi vazifa turini olamiz
    task_type = data.get("task_type", "test")

    # 3️⃣ Faqat shu task_type va kurs uchun yuborilgan mavzularni filter qilamiz
    submitted_topic_ids = {
        task["topic"]["id"] 
        for task in submitted_tasks 
        if task.get("task_type") == task_type and task.get("course_type") == student_course_type
    }

    # 4️⃣ Faqat yubormagan active mavzularni filter qilamiz
    available_topics = [t for t in active_topics if t["id"] not in submitted_topic_ids]

    if not available_topics:
        course_name = "Milliy Sertifikat" if student_course_type == "milliy_sert" else "Attestatsiya"
        task_name_lower = "test" if task_type == "test" else "maxsus topshiriq"
        await message.answer(f"✅ Siz {course_name} uchun barcha active mavzular uchun {task_name_lower} yuborgansiz!")
        return

    kb = types.InlineKeyboardMarkup()
    for t in available_topics:
        kb.add(types.InlineKeyboardButton(
            text=t["title"], callback_data=f"topic_{t['id']}"
        ))

    await message.answer(f"📚 {task_type} uchun mavzuni tanlang:", reply_markup=kb)
    await TaskState.topic.set()
    

@dp.callback_query_handler(lambda c: c.data.startswith("topic_"), state=TaskState.topic)
async def process_topic(callback: types.CallbackQuery, state: FSMContext):
    topic_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    task_type = data.get("task_type", "test")
    
    # Topic dan correct_answers borligini tekshirish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            if resp.status != 200:
                await callback.message.answer("❌ Xatolik yuz berdi!")
                await callback.answer()
                return
            
            topics = await resp.json()
            topic = next((t for t in topics if t['id'] == topic_id), None)
            
            if not topic:
                await callback.message.answer("❌ Mavzu topilmadi!")
                await callback.answer()
                return
            
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
        async with session.get(f"{API_BASE_URL}/topics/") as resp_topics:
            if resp_topics.status != 200:
                await message.answer("❌ Xatolik yuz berdi!")
                return
            
            topics_list = await resp_topics.json()
            current_topic = next((t for t in topics_list if t['id'] == topic_id), None)
            
            if not current_topic:
                await message.answer("❌ Mavzu topilmadi!")
                return
            
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
        
        correct = correct_answers[test_code].lower()
        user_answer = test_answers.lower()
        
        # Parse admin correct answers (supports multi-correct: 1ab2x3abcd)
        correct_answers_list = []
        if re.match(r'^[abcdx]+$', correct):
            # Format 1: abc -> [[a], [b], [c]]
            correct_answers_list = [[ch] for ch in correct]
        else:
            # Format 2: 1a2b3c or 1ab2x3abcd -> [[a], [b], [c]] or [[a,b], [x], [a,b,c,d]]
            for match in re.finditer(r'\d+([abcdx]+)', correct):
                answers = match.group(1)
                if answers == 'x':
                    correct_answers_list.append(['x'])
                else:
                    correct_answers_list.append(list(answers))
        
        # Parse student answers (single answer per question)
        student_answers_list = []
        if re.match(r'^[abcdx]+$', user_answer):
            # Format 1: abc -> [a, b, c]
            student_answers_list = list(user_answer)
        else:
            # Format 2: 1a2b3c -> [a, b, c]
            for match in re.finditer(r'\d+([abcdx])', user_answer):
                student_answers_list.append(match.group(1))
        
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
        result_text = "📊 Test natijalari:\n\n"
        correct_count = 0
        total_count = len(correct_answers_list)
        
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
        
        # Foiz hisoblab userga ko'rsatish (baho ko'rsatmaslik)
        percentage = (correct_count / total_count * 100) if total_count > 0 else 0
        
        result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)"
        
        await message.answer(result_text, reply_markup=vazifa_key)
        
        # Topic'dan course_type ni olamiz (ishonchli)
        topic_course_type = current_topic.get("course_type", "attestatsiya")
        
        # DBga saqlash - grade qismiga to'g'ri javoblar soni
        payload = {
            "student_id": message.from_user.id,
            "topic_id": topic_id,
            "task_type": "test",
            "course_type": topic_course_type,
            "test_code": test_code,
            "test_answers": test_answers,
            "grade": correct_count  # To'g'ri javoblar soni
        }
    else:
        # To'g'ri javoblar mavjud emas - oddiy saqlash
        await message.answer("✅ 📝 Test javoblari yuborildi! Admin tekshiradi.", reply_markup=vazifa_key)
        
        # Topic'dan course_type ni olamiz (ishonchli)
        topic_course_type = current_topic.get("course_type", "attestatsiya")
        
        payload = {
            "student_id": message.from_user.id,
            "topic_id": topic_id,
            "task_type": "test",
            "course_type": topic_course_type,
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
                await message.answer(
                    f"❌ Test javoblarini saqlashda xatolik!\n\n"
                    f"Status: {resp.status}\n"
                    f"Iltimos, admin bilan bog'laning."
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

    # Topic'dan course_type ni olamiz
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/topics/{topic_id}/") as resp_topic:
            if resp_topic.status == 200:
                topic_data = await resp_topic.json()
                topic_course_type = topic_data.get("course_type", "attestatsiya")
            else:
                topic_course_type = "attestatsiya"  # Default

    payload = {
        "student_id": message.from_user.id,  # telegram_id
        "topic_id": topic_id,
        "task_type": task_type,
        "course_type": topic_course_type,
        "file_link": file_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/tasks/submit/", json=payload) as resp:
            if resp.status == 201:
                data = await resp.json()
                task_id = data["id"]
                student_name = data["student"]["full_name"]
                group_name = data["student"]["group"]["name"]
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

                # ✨ Kurs turiga qarab to'g'ri adminga yuborish
                student_course_type = payload.get("course_type", "milliy_sert")
                target_admin = MILLIY_ADMIN if student_course_type == "milliy_sert" else ATTESTATSIYA_ADMIN
    
                if file_type == "document":
                    await bot.send_document(target_admin, file_id, caption=caption, reply_markup=kb)
                else:
                    await bot.send_photo(target_admin, file_id, caption=caption, reply_markup=kb)

            else:
                await message.answer("❌ Vazifa yuborishda xatolik bo'ldi.")

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
