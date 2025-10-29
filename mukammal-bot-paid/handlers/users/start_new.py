from aiogram import types
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp,bot
from aiogram.dispatcher.filters import Text
from aiogram.utils import executor
from states.register_state import RegisterState
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message



# --- START ---
@dp.message_handler(commands=["start"], state="*")
async def cmd_start_all_states(message: types.Message, state: FSMContext):
    """Student allaqachon ro'yxatdan o'tganmi tekshiramiz"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro‘yxatdan o‘tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return

    # Agar topilmasa ro‘yxatdan o‘tadi
    await message.answer("Assalomu alaykum! Ro‘yxatdan o‘tish uchun F.I.Sh kiriting:")
    await RegisterState.full_name.set()

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    """Student allaqachon ro'yxatdan o'tganmi tekshiramiz"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro‘yxatdan o‘tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return

    # Agar topilmasa ro‘yxatdan o‘tadi
    await message.answer("Assalomu alaykum! Ro‘yxatdan o‘tish uchun F.I.Sh kiriting:")
    await RegisterState.full_name.set()

# F.I.Sh qabul qilish
@dp.message_handler(state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)

    # Guruhlarni va ularning a'zolar sonini olish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()

        # Har bir guruh uchun a'zolar sonini tekshiramiz
        selected_group = None
        for g in groups:
            group_id = g["id"]
            async with session.get(f"{API_BASE_URL}/students/?group_id={group_id}") as resp2:
                students_in_group = await resp2.json()
                if len(students_in_group) < 50:
                    selected_group = group_id
                    break

    if selected_group is None:
        await message.answer("❌ Hech bir guruhda bo'sh joy yo'q. Admin bilan bog'laning.")
        try:
            await state.finish()
        except Exception as e:
            pass
        return

    # Avtomatik tanlangan guruhga ro'yxatdan o'tkazamiz
    data = await state.get_data()
    full_name = data["full_name"]
    payload = {
        "telegram_id": str(message.from_user.id),
        "full_name": full_name,
        "group_id": selected_group
    }

    # Guruh linkini olish (guruh obyektidan)
    group_obj = next((g for g in groups if g["id"] == selected_group), None)
    group_link = group_obj.get("invite_link") if group_obj else None
    umumiy_link = "https://t.me/+yIsZnSKlj9lmMTEy"  # umumiy guruh linki
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro‘yxatdan o‘tdingiz! Sizning guruh - {group_name}. Guruhga qo'shilib oling. Endi vazifalarni yuborishingiz mumkin 👇"
                if group_link:
                    msg += f"\n\nGuruhga qo'shilish uchun link: {group_link}"
                    msg += f"\n\nUmumiy guruhga qo'shilish uchun link: {umumiy_link}"
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro‘yxatdan o‘tishda xatolik bo‘ldi.")
    try:
        await state.finish()
    except Exception as e:
        pass


# Guruh tanlash
@dp.callback_query_handler(lambda c: c.data.startswith("group_"), state=RegisterState.group)
async def process_group(callback: types.CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    full_name = data["full_name"]

    payload = {
        "telegram_id": str(callback.from_user.id),
        "full_name": full_name,
        "group_id": group_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                await callback.message.answer(
                    "✅ Ro‘yxatdan o‘tdingiz!\nEndi vazifalarni yuborishingiz mumkin 👇",
                    reply_markup=vazifa_key
                )
            else:
                await callback.message.answer("❌ Ro‘yxatdan o‘tishda xatolik bo‘ldi.")
    await state.finish()
    await callback.answer()


# --- Vazifa yuborish ---
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
        group_link = group_obj.get("invite_link") if group_obj else None
        umumiy_link = "https://t.me/+yIsZnSKlj9lmMTEy"
        
        # Guruhlarga qo'shilganligini tekshirish
        try:
            # O'z guruhiga qo'shilganmi
            group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
            if group_member.status in ["left", "kicked"]:
                await message.answer(
                    f"❌ Siz o'z guruhingizga qo'shilmagansiz!\n\n"
                    f"Guruhga qo'shilish uchun: {group_link}"
                )
                return
        except Exception as e:
            # Guruh ID mavjud emas yoki boshqa xatolik
            pass
            
        try:
            # Umumiy guruhga qo'shilganmi (bu yerda umumiy guruh chat_id ni qo'ying)
            GENERAL_GROUP_ID = "-1002319099734"  # Umumiy guruh ID sini bu yerga qo'ying
            general_member = await bot.get_chat_member(GENERAL_GROUP_ID, telegram_id)
            if general_member.status in ["left", "kicked"]:
                await message.answer(
                    f"❌ Siz umumiy guruhga qo'shilmagansiz!\n\n"
                    f"Umumiy guruhga qo'shilish uchun: {umumiy_link}"
                )
                return
        except Exception as e:
            # Umumiy guruhga qo'shilmagan
            await message.answer(
                f"❌ Siz umumiy guruhga qo'shilmagansiz!\n\n"
                f"Umumiy guruhga qo'shilish uchun: {umumiy_link}"
            )
            return

    async with aiohttp.ClientSession() as session:
        # 1️⃣ Barcha mavzular
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()

    submitted_topic_ids = {task["topic"]["id"] for task in submitted_tasks}
