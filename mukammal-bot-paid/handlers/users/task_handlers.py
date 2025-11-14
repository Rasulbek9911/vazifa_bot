"""
Task submission handlers: task sending, topic selection, file upload
Single group with approval link (50 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# General channel/group ID is configured in data.config


@dp.message_handler(Text(equals="📤 Vazifa yuborish"))
async def send_task(message: types.Message):
    telegram_id = message.from_user.id
    
    # Adminlarni tekshirish - adminlar vazifa yubormaydi
    if str(telegram_id) in ADMINS:
        await message.answer("ℹ️ Adminlar vazifa yubora olmaydi.")
        return

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
