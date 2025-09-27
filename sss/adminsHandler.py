import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from datetime import datetime
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from main import dp  # Dispatcher ob'ektini main.py dan import qilamiz

# Admin ID’lar ro‘yxati
ADMIN_IDS = [1062271566]  # bu yerga adminlarning Telegram IDlarini yozing


# === Mavzu qo'shish komandasini faqat admin ishlata oladi ===
@dp.message(Command("addtopic"))
async def add_topic_command(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("❌ Sizda bu huquq yo‘q.")
        return

    await message.answer("✍️ Yangi mavzuni kiriting:")
    await state.set_state("adding_topic")


@dp.message(F.text, state="adding_topic")
async def save_new_topic(message: types.Message, state: FSMContext):
    topic = message.text.strip()

    try:
        worksheet = spreadsheet.worksheet("StudentVazifalar")

        # 1-qatorni o‘qib kelamiz (sarlavha)
        headers = worksheet.row_values(1)

        # Mavzu allaqachon mavjudmi?
        if topic in headers:
            await message.answer("❌ Bu mavzu allaqachon mavjud.")
            await state.clear()
            return

        # Qo‘shiladigan ustun indexi (oxiriga qo‘shamiz)
        col_index = len(headers) + 1

        # 1-qatorga yangi mavzuni qo‘shamiz
        worksheet.update_cell(1, col_index, topic)

        await message.answer(f"✅ '{topic}' mavzusi qo‘shildi.")
    except Exception as e:
        await message.answer("❌ Mavzu qo‘shishda xatolik: " + str(e))

    await state.clear()
