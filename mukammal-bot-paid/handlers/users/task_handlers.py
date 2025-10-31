"""
Task submission handlers: task sending, topic selection, file upload
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL, GENERAL_GROUP_ID, GENERAL_GROUP_INVITE_LINK
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
        
        # Guruhlarga qo'shilganligini tekshirish
        group_not_joined = False
        general_not_joined = False
        
        # O'z guruhiga qo'shilganmi tekshirish
        if group_obj and group_obj.get("telegram_group_id"):
            try:
                group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                if group_member.status in ["left", "kicked"]:
                    group_not_joined = True
            except:
                # Guruhni tekshira olmasa, link beramiz
                group_not_joined = bool(group_obj.get("invite_link"))
        else:
            group_not_joined = False
            
        # Umumiy guruhga qo'shilganmi
        try:
            general_member = await bot.get_chat_member(GENERAL_GROUP_ID, telegram_id)
            if general_member.status in ["left", "kicked"]:
                general_not_joined = True
        except:
            general_not_joined = True
        
        # Agar qo'shilmagan bo'lsa, yangi 1 martalik linklar yaratamiz
        if group_not_joined or general_not_joined:
            msg = "❌ Siz quyidagi guruhlarga qo'shilmagansiz:\n\n"
            
            if group_not_joined and group_obj and group_obj.get("telegram_group_id"):
                try:
                    # Yangi 1 martalik link
                    group_invite = await bot.create_chat_invite_link(
                        chat_id=group_obj.get("telegram_group_id"),
                        member_limit=1
                    )
                    msg += f"🔹 O'z guruhingiz: {group_invite.invite_link}\n"
                except:
                    if group_obj.get("invite_link"):
                        msg += f"🔹 O'z guruhingiz: {group_obj.get('invite_link')}\n"
            elif group_not_joined and group_obj:
                if group_obj.get("invite_link"):
                    msg += f"🔹 O'z guruhingiz: {group_obj.get('invite_link')}\n"
            
            if general_not_joined:
                try:
                    # Kanal yoki guruh
                    is_channel = False
                    try:
                        chat_info = await bot.get_chat(GENERAL_GROUP_ID)
                        is_channel = chat_info.type == "channel"
                    except:
                        pass

                    if is_channel:
                        # Kanal - primary link
                        try:
                            primary_link = await bot.export_chat_invite_link(chat_id=GENERAL_GROUP_ID)
                            msg += f"🔹 Umumiy kanal: {primary_link}\n"
                        except:
                            # Fallback
                            msg += f"🔹 Umumiy kanal: {GENERAL_GROUP_INVITE_LINK}\n"
                    else:
                        # Supergroup - 1 martalik
                        general_invite = await bot.create_chat_invite_link(
                            chat_id=GENERAL_GROUP_ID,
                            member_limit=1
                        )
                        msg += f"🔹 Umumiy guruh: {general_invite.invite_link}\n"
                except:
                    msg += f"🔹 Umumiy kanal: {GENERAL_GROUP_INVITE_LINK}\n"
            
            msg += "\n⚠️ Iltimos, guruhlarga qo'shiling va qayta urinib ko'ring."
            
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
