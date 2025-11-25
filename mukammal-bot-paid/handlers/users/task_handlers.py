"""
Task submission handlers: task sending, topic selection, file upload
Single group with approval link (50 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text, Command
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# General channel/group ID is configured in data.config


@dp.message_handler(Text(equals="📝 Test yuborish"))
async def send_test(message: types.Message, state: FSMContext):
    await state.update_data(task_type="test")
    await _send_task_common(message, state, "📝 Test")

@dp.message_handler(Text(equals="📋 Maxsus topshiriq yuborish"))
async def send_assignment(message: types.Message, state: FSMContext):
    await state.update_data(task_type="assignment")
    await _send_task_common(message, state, "📋 Maxsus topshiriq")

async def _send_task_common(message: types.Message, state: FSMContext, task_name: str):
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
            
        # Guruh ma'lumotlarini olish
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
            
        group_obj = next((g for g in groups if g["id"] == group_id), None)
        
        # Guruhga qo'shilganligini tekshirish
        # Faqat "member", "administrator" yoki "creator" bo'lsa vazifa yuborishi mumkin
        group_not_joined = True  # Default: qo'shilmagan
        
        # Guruhga qo'shilganmi tekshirish
        if group_obj and group_obj.get("telegram_group_id"):
            try:
                # Avval botning o'zi admin ekanligini tekshiramiz
                bot_info = await bot.get_me()
                bot_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), bot_info.id)
                
                # Bot admin bo'lsa, user statusini tekshiramiz
                if bot_member.status in ["administrator", "creator"]:
                    group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                    
                    # Faqat member, administrator yoki creator bo'lsa qo'shilgan hisoblanadi
                    if group_member.status in ["member", "administrator", "creator"]:
                        group_not_joined = False
                    # left, kicked, restricted - qo'shilmagan (lekin link beramiz)
                    else:
                        group_not_joined = True
                else:
                    # Bot admin bo'lmasa ham, user qo'shilmagan deb hisoblaymiz
                    group_not_joined = True
            except Exception as e:
                # Exception bo'lsa, xatolik haqida ma'lumot beramiz
                print(f"❌ Guruh membership tekshiruvida xatolik: {e}")
                # Exception bo'lsa ham, user qo'shilmagan deb hisoblaymiz (xavfsizlik uchun)
                group_not_joined = True
        else:
            group_not_joined = True
        
        # Agar qo'shilmagan bo'lsa, link beramiz (kicked bo'lsa ham qayta qo'shilishi mumkin)
        if group_not_joined:
            msg = "❌ Siz guruhga qo'shilmagansiz!\n\n"
            
            # Guruh linki - kicked bo'lsa adminlarga xabar beramiz
            if group_obj and group_obj.get("telegram_group_id"):
                # Avval user statusini aniqlaymiz
                user_status = None
                try:
                    bot_info = await bot.get_me()
                    bot_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), bot_info.id)
                    
                    if bot_member.status in ["administrator", "creator"]:
                        user_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                        user_status = user_member.status
                except Exception as e:
                    pass
                
                # Agar kicked bo'lsa, adminlarga xabar beramiz
                if user_status == "kicked":
                    msg += "⚠️ Siz guruhdan chiqarilgansiz.\n"
                    msg += "📞 Admin bilan bog'lanib, qayta qo'shilishni so'rang.\n\n"
                    
                    # Adminlarga xabar
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
                    # Left yoki boshqa status - oddiy link beramiz
                    if group_obj.get("invite_link"):
                        msg += f"🔗 Guruh: {group_obj.get('invite_link')}\n"
                        msg += f"   (Qo'shilish uchun bosing)\n\n"
            
            msg += "⚠️ Guruhga qo'shilgandan keyin vazifa yuborishingiz mumkin.\n"
            
            await message.answer(msg)
            return

    async with aiohttp.ClientSession() as session:
        # 1️⃣ Barcha active mavzular
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()
        
        # Faqat active mavzularni olamiz
        active_topics = [t for t in topics if t.get("is_active", False)]
        
        if not active_topics:
            await message.answer("❌ Hozirda active mavzu yo'q!")
            return

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()
    
    # Hozirgi vazifa turini olamiz
    data = await state.get_data()
    current_task_type = data.get("task_type", "test")

    # 3️⃣ Faqat shu task_type uchun yuborilgan mavzularni filter qilamiz
    submitted_topic_ids = {
        task["topic"]["id"] 
        for task in submitted_tasks 
        if task.get("task_type") == current_task_type
    }

    # 4️⃣ Faqat yubormagan active mavzularni filter qilamiz
    available_topics = [t for t in active_topics if t["id"] not in submitted_topic_ids]

    if not available_topics:
        await message.answer(f"✅ Siz barcha active mavzular uchun {task_name} yuborgansiz!")
        return

    kb = types.InlineKeyboardMarkup()
    for t in available_topics:
        kb.add(types.InlineKeyboardButton(
            text=t["title"], callback_data=f"topic_{t['id']}"
        ))

    await message.answer(f"📚 {task_name} uchun mavzuni tanlang:", reply_markup=kb)
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
            "Format: test_kodi separator javoblar\n\n"
            "Separator: - yoki + yoki *\n\n"
            "Misol:\n"
            "• 1-abc (defis bilan)\n"
            "• 1+1a2c3b (plus bilan)\n"
            "• 1*abc (yulduzcha bilan)\n"
            "• A-1a2b3c\n\n"
            "Test kodi: 1, 2, A, B va boshqalar"
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
    # Separator: - yoki + yoki *
    test_code = None
    test_answers = None
    separator = None
    
    for sep in ['-', '+', '*']:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2:
                test_code = parts[0].strip()
                test_answers = parts[1].strip()
                separator = sep
                break
    
    if not test_code or not test_answers:
        await message.answer(
            "❌ Noto'g'ri format!\n\n"
            "To'g'ri format: test_kodi separator javoblar\n"
            "Separator: - yoki + yoki *\n\n"
            "Misol:\n"
            "• 1-abc\n"
            "• 1+1a2c3b\n"
            "• 1*abc"
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
    
    # Test javoblarini tekshirish
    if correct_answers and test_code in correct_answers:
        correct = correct_answers[test_code].lower()
        user_answer = test_answers.lower()
        
        # Uzunlik tekshirish
        if len(user_answer) != len(correct):
            await message.answer(
                f"❌ Javoblar soni noto'g'ri!\n\n"
                f"Kerakli javoblar soni: {len(correct)}\n"
                f"Sizning javoblaringiz: {len(user_answer)}\n\n"
                f"Iltimos, to'g'ri formatda qayta yuboring.",
                reply_markup=vazifa_key
            )
            await state.finish()
            return
        
        # Har bir harf uchun tekshirish
        result_text = "📊 Test natijalari:\n\n"
        correct_count = 0
        total_count = len(correct)
        
        for i, (c_char, u_char) in enumerate(zip(correct, user_answer), 1):
            if c_char == u_char:
                result_text += f"{i}. ✅ {u_char.upper()}\n"
                correct_count += 1
            else:
                result_text += f"{i}. ❌ {u_char.upper()} (To'g'ri: {c_char.upper()})\n"
        
        # Foiz va baho
        percentage = (correct_count / total_count * 100) if total_count > 0 else 0
        grade = int(percentage / 20)  # 5 ball tizimi
        
        result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)\n"
        result_text += f"⭐ Baho: {grade}"
        
        await message.answer(result_text, reply_markup=vazifa_key)
        
        # DBga saqlash - natija bilan
        payload = {
            "student_id": message.from_user.id,
            "topic_id": topic_id,
            "task_type": "test",
            "test_code": test_code,
            "test_answers": test_answers,
            "grade": grade
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
                await message.answer("❌ Test javoblarini saqlashda xatolik!")
    
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

    
                if file_type == "document":
                    await bot.send_document(ADMINS[0], file_id, caption=caption, reply_markup=kb)
                else:
                    await bot.send_photo(ADMINS[0], file_id, caption=caption, reply_markup=kb)

            else:
                await message.answer("❌ Vazifa yuborishda xatolik bo'ldi.")

    try:
        await state.finish()
    except:
        pass


# --- ADMIN TEST QO'SHISH ---
@dp.message_handler(Command("addtest"), user_id=ADMINS)
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

@dp.message_handler(state="addtest_code", user_id=ADMINS)
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
        "To'g'ri javobni kiriting.\n"
        "\n"
        "Formatlar:\n"
        "1) Harflar ketma-ketligi: abcd\n"
        "   (Masalan: abcd - 4 ta savolga 4 ta harf)\n"
        "\n"
        "2) Raqam-harf juftligi: 1a2b3c4d\n"
        "   (Masalan: 1a2b3c4d - har bir savol raqam bilan, javobi harf bilan)\n"
        "\n"
        "Ikkala formatdan birini tanlab, to'g'ri javoblarni kiriting."
    )
    await state.set_state("addtest_answer")

@dp.message_handler(state="addtest_answer", user_id=ADMINS)
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
