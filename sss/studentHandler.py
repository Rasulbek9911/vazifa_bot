import asyncio
import gspread
from google.oauth2.service_account import Credentials
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from defoultKeyboard import main_kb

from googlesheet import spreadsheet, get_groups
from config import API_TOKEN
from main import dp


# ====== STATES ======
class RegisterState(StatesGroup):
    fish = State()
    group = State()


class TaskState(StatesGroup):
    choose_topic = State()
    upload_file = State()


# ====== START ======
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)

    # 🔍 Barcha guruhlarni tekshiramiz
    for ws in spreadsheet.worksheets():
        try:
            existing_ids = [c for c in ws.col_values(1) if c]
            if user_id in existing_ids:
                await message.answer(
                    "✅ Siz allaqachon ro‘yxatdan o‘tgansiz.\n"
                    "Endi vazifalarni jo‘natishingiz mumkin 👇",
                    reply_markup=main_kb,
                )
                return
        except Exception:
            continue

    # Agar ro‘yxatda bo‘lmasa → F.I.Sh kiritishni so‘raymiz
    await state.set_state(RegisterState.fish)
    await message.answer("Assalomu alaykum! Ro‘yxatdan o‘tish uchun F.I.Sh kiriting:")


# ====== F.I.Sh qabul qilish ======
@dp.message(RegisterState.fish)
async def get_fish(message: types.Message, state: FSMContext):
    fish = message.text.strip()
    await state.update_data(fish=fish)

    # Guruhlarni Google Sheetsdan o‘qib kelamiz
    groups = get_groups()
    if not groups:
        await message.answer("❌ Hozircha guruhlar ro‘yxati yo‘q.")
        return

    # Guruhlarni inline tugmalarda chiqarish
    builder = InlineKeyboardBuilder()
    for g in groups:
        builder.button(text=g, callback_data=f"group_{g}")
    builder.adjust(2)

    await state.set_state(RegisterState.group)
    await message.answer(
        "Iltimos, guruhingizni tanlang:", reply_markup=builder.as_markup()
    )


# ====== Guruh tanlash ======
@dp.callback_query(RegisterState.group, F.data.startswith("group_"))
async def group_chosen(callback: types.CallbackQuery, state: FSMContext):
    user_id = str(callback.from_user.id)
    group = callback.data.split("_", 1)[1]

    data = await state.get_data()
    fish = data.get("fish")

    # 🔍 Barcha guruhlarni tekshiramiz
    for ws in spreadsheet.worksheets():
        existing_ids = [c for c in ws.col_values(1) if c]
        if user_id in existing_ids:
            await callback.message.answer(
                "❌ Siz allaqachon boshqa guruhda ro'yxatdan o'tgansiz.\n"
                "Endi vazifalarni jo'natishingiz mumkin!",
                reply_markup=main_kb,
            )
            await state.clear()
            await callback.answer()
            return

    # Worksheet topamiz yoki yangisini ochamiz
    try:
        worksheet = spreadsheet.worksheet(group)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=group, rows="100", cols="20")
        worksheet.append_row(["Telegram ID", "F.I.Sh"])

    worksheet.append_row([user_id, fish])

    await callback.message.answer(
        f"✅ Siz ro‘yxatdan o‘tdingiz!\n"
        f"F.I.Sh: {fish}\n"
        f"Guruh: {group}\n"
        f"Endi vazifalarni jo'natishingiz mumkin.",
        reply_markup=main_kb,
    )
    await state.clear()
    await callback.answer()


# ====== Vazifa yuborish ======
@dp.message(F.text == "📤 Vazifa yuborish")
async def send_task(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)

    # Avval ro'yxatdan o'tganligini tekshiramiz
    registered = False
    for ws in spreadsheet.worksheets():
        if user_id in ws.col_values(1):
            registered = True
            break

    if not registered:
        await message.answer("❌ Avval ro‘yxatdan o‘ting (/start).")
        return

    # Google Sheets'dan mavzularni olish
    try:
        worksheet = spreadsheet.worksheet("StudentVazifalar")
        topics = worksheet.row_values(1)[0:]  # 5-ustundan boshlab
        print("Mavzular:", topics)

    except Exception as e:
        await message.answer("❌ Mavzularni olishda xatolik: " + str(e))
        return

    if not topics:
        await message.answer("❌ Hozircha mavzular mavjud emas.")
        return

    # InlineKeyboard bilan mavzular chiqarish
    builder = InlineKeyboardBuilder()
    for t in topics:
        builder.button(text=t, callback_data=f"topic_{t}")
    builder.adjust(2)

    await state.set_state(TaskState.choose_topic)
    await message.answer("📚 Mavzuni tanlang:", reply_markup=builder.as_markup())


# ====== Mavzu tanlandi ======
@dp.callback_query(TaskState.choose_topic, F.data.startswith("topic_"))
async def topic_chosen(callback: types.CallbackQuery, state: FSMContext):
    topic = callback.data.split("_", 1)[1]
    await state.update_data(topic=topic)

    await state.set_state(TaskState.upload_file)
    await callback.message.answer(
        f"📌 Mavzu tanlandi: {topic}\nEndi faylni (rasm yoki hujjat) yuboring:"
    )
    await callback.answer()


# ====== Fayl qabul qilish ======
@dp.message(TaskState.upload_file, F.content_type.in_({"photo", "document"}))
async def upload_file(message: types.Message, state: FSMContext):
    user_id = str(message.from_user.id)
    data = await state.get_data()
    topic = data.get("topic")

    file_id = None
    if message.photo:
        file_id = message.photo[-1].file_id
    elif message.document:
        file_id = message.document.file_id

    await message.answer(f"✅ Vazifa qabul qilindi!\nMavzu: {topic}\nFile ID: {file_id}")
    await state.clear()

    # ❗ Bu yerda siz faylni o‘qituvchiga yuborishingiz mumkin
    # va Google Sheets'ga saqlashni qo‘shasiz
