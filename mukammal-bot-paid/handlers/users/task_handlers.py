"""
Task submission handlers: task sending, topic selection, file upload
Both channels now use approval links (no one-time links)
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL, GENERAL_CHANNEL_ID, GENERAL_CHANNEL_INVITE_LINK
from loader import dp, bot
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# General channel/group ID is configured in data.config


@dp.message_handler(Text(equals="📤 Vazifa yuborish"))
async def send_task(message: types.Message):
    telegram_id = message.from_user.id

    # Studentni tekshirish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{telegram_id}/") as resp:
            if resp.status != 200:
                await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            student_data = await resp.json()
            group_id = student_data.get("group", {}).get("id")
            
        # Guruh ma'lumotlarini olish
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
            
        group_obj = next((g for g in groups if g["id"] == group_id), None)
        
        # Kanallarga qo'shilganligini tekshirish
        # Bot kanal adminida bo'lsa, statusni tekshiramiz
        # Bot admin bo'lmasa, vazifa yuborishga ruxsat beramiz (foydalanuvchi o'zi javobgar)
        group_not_joined = False
        general_not_joined = False
        
        # O'z kanaliga qo'shilganmi tekshirish
        if group_obj and group_obj.get("telegram_group_id"):
            try:
                # Avval botning o'zi admin ekanligini tekshiramiz
                bot_info = await bot.get_me()
                bot_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), bot_info.id)
                
                # Bot admin bo'lsa, user statusini tekshiramiz
                if bot_member.status in ["administrator", "creator"]:
                    group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                    print(f"[DEBUG] O'z kanal status: {group_member.status}")
                    # Faqat left statusida qo'shilmagan deb hisoblaymiz
                    # kicked statusini ham inobatga olmaymiz (ba'zan xato status qaytaradi)
                    if group_member.status == "left":
                        group_not_joined = True
                else:
                    print(f"[DEBUG] Bot o'z kanalda admin emas, tekshirmaslik")
            except Exception as e:
                print(f"[DEBUG] O'z kanal exception: {e}")
                # Exception bo'lsa, vazifa yuborishga ruxsat beramiz
                group_not_joined = False
        else:
            group_not_joined = False
            
        # Umumiy kanalga qo'shilganmi
        try:
            # Avval botning o'zi admin ekanligini tekshiramiz
            bot_info = await bot.get_me()
            bot_member = await bot.get_chat_member(GENERAL_CHANNEL_ID, bot_info.id)
            
            # Bot admin bo'lsa, user statusini tekshiramiz
            if bot_member.status in ["administrator", "creator"]:
                general_member = await bot.get_chat_member(GENERAL_CHANNEL_ID, telegram_id)
                print(f"[DEBUG] Umumiy kanal status: {general_member.status}")
                # Faqat left statusida qo'shilmagan deb hisoblaymiz
                # kicked statusini ham inobatga olmaymiz (ba'zan xato status qaytaradi)
                if general_member.status == "left":
                    general_not_joined = True
            else:
                print(f"[DEBUG] Bot umumiy kanalda admin emas, tekshirmaslik")
        except Exception as e:
            print(f"[DEBUG] Umumiy kanal exception: {e}")
            # Exception bo'lsa, vazifa yuborishga ruxsat beramiz
            general_not_joined = False
        
        print(f"[DEBUG] group_not_joined={group_not_joined}, general_not_joined={general_not_joined}")
        
        # Agar qo'shilmagan bo'lsa, approval linklar beramiz
        if group_not_joined or general_not_joined:
            msg = "❌ Siz quyidagi kanallarga qo'shilmagansiz:\n\n"
            
            # O'z kanali linki
            if group_not_joined and group_obj and group_obj.get("invite_link"):
                msg += f"🔹 O'z kanalingiz: {group_obj.get('invite_link')}\n"
                msg += f"   (So'rov yuboring, admin tasdiqlaydi)\n"
            
            # Umumiy kanal linki
            if general_not_joined:
                msg += f"🔹 Umumiy kanal: {GENERAL_CHANNEL_INVITE_LINK}\n"
                msg += f"   (So'rov yuboring, admin tasdiqlaydi)\n"
            
            msg += "\n⚠️ Iltimos, kanallarga qo'shiling va qayta urinib ko'ring."
            
            await message.answer(msg)
            return

    async with aiohttp.ClientSession() as session:
        # 1️⃣ Barcha mavzular
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()

    submitted_topic_ids = {task["topic"]["id"] for task in submitted_tasks}

    # 3️⃣ Faqat yubormagan mavzularni filter qilamiz
    available_topics = [t for t in topics if t["id"] not in submitted_topic_ids]

    if not available_topics:
        await message.answer("✅ Siz barcha mavzular uchun vazifa yuborgansiz!")
        return

    kb = types.InlineKeyboardMarkup()
    for t in available_topics:
        kb.add(types.InlineKeyboardButton(
            text=t["title"], callback_data=f"topic_{t['id']}"
        ))

    await message.answer("📚 Mavzuni tanlang:", reply_markup=kb)
    await TaskState.topic.set()
    

@dp.callback_query_handler(lambda c: c.data.startswith("topic_"), state=TaskState.topic)
async def process_topic(callback: types.CallbackQuery, state: FSMContext):
    topic_id = int(callback.data.split("_")[1])
    await state.update_data(topic_id=topic_id)
    await callback.message.answer("📎 Endi faylni yuboring (rasm yoki hujjat).")
    await TaskState.file.set()
    await callback.answer()


@dp.message_handler(content_types=["document", "photo"], state=TaskState.file)
async def process_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    topic_id = data["topic_id"]

    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        file_id = message.photo[-1].file_id
        file_type = "photo"

    payload = {
        "student_id": message.from_user.id,  # telegram_id
        "topic_id": topic_id,
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
                await message.answer("✅ Vazifangiz yuborildi!", reply_markup=vazifa_key)

                # ✅ Admin uchun inline keyboard
                kb = InlineKeyboardMarkup(row_width=3)
                kb.add(
                    InlineKeyboardButton("3️⃣", callback_data=f"grade_{task_id}_3"),
                    InlineKeyboardButton("4️⃣", callback_data=f"grade_{task_id}_4"),
                    InlineKeyboardButton("5️⃣", callback_data=f"grade_{task_id}_5"),
                )

                caption = (
                    f"📥 Yangi vazifa!\n\n"
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
