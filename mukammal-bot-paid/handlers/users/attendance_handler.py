"""
Davomat tizimi handlerlari — admin va talaba
"""
import logging
from datetime import datetime, timedelta

import aiohttp
import pytz
from aiogram import types
from aiogram.dispatcher import FSMContext

from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.attendance_state import AttendanceSessionState, AttendanceMarkState
from utils.safe_send_message import safe_send_message
from utils.course_guard import course_guard_message

logger = logging.getLogger(__name__)

TZ = pytz.timezone("Asia/Tashkent")


# ─── Admin: sessiya ochish ────────────────────────────────────────────────────

async def _open_attendance_session(chat_id: int):
    """Sessiya ochish so'rovini yuboradi va state ni set qiladi (ikki joydan chaqiriladi)"""
    from loader import dp

    guard_msg = await course_guard_message()
    if guard_msg:
        await bot.send_message(chat_id, guard_msg)
        return

    await bot.send_message(
        chat_id,
        "📝 Davomat kodini kiriting (masalan: 3847):",
    )
    await dp.current_state(chat=chat_id, user=chat_id).set_state(AttendanceSessionState.waiting_for_code)


@dp.message_handler(lambda m: m.text == "📅 Davomat sessiyasi" and str(m.from_user.id) in ADMINS)
async def attendance_session_start(message: types.Message):
    await _open_attendance_session(message.chat.id)


@dp.message_handler(state=AttendanceSessionState.waiting_for_code)
async def attendance_session_code(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("Bekor qilindi.")
        return

    code = message.text.strip()
    if not code:
        await message.answer("❌ Kod bo'sh bo'lmasin. Qaytadan kiriting:")
        return

    await state.update_data(code=code)
    await message.answer(
        "⏱ Sessiya qancha muddat amal qilsin?\n\n"
        "• <b>2</b> yoki <b>2soat</b> — 2 soat\n"
        "• <b>1hafta</b> yoki <b>1w</b> — 1 hafta",
        parse_mode="HTML",
    )
    await AttendanceSessionState.waiting_for_duration.set()


@dp.message_handler(state=AttendanceSessionState.waiting_for_duration)
async def attendance_session_duration(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("Bekor qilindi.")
        return

    text = message.text.strip().lower().replace(",", ".")

    # "2h", "2 soat", "2soat" → soat; "1w", "1 hafta", "1hafta" → hafta
    hours = None
    label = ""
    try:
        if text.endswith("w") or "hafta" in text:
            weeks = float(text.replace("hafta", "").replace("w", "").strip())
            if weeks <= 0 or weeks > 52:
                raise ValueError
            hours = weeks * 24 * 7
            label = f"{weeks:.0f} hafta" if weeks == int(weeks) else f"{weeks} hafta"
        else:
            val = float(text.replace("h", "").replace("soat", "").strip())
            if val <= 0 or val > 8760:
                raise ValueError
            hours = val
            label = f"{val:.0f} soat" if val == int(val) else f"{val} soat"
    except ValueError:
        await message.answer(
            "❌ Noto'g'ri qiymat. Misollar:\n"
            "• <b>2</b> yoki <b>2soat</b> — 2 soat\n"
            "• <b>1hafta</b> yoki <b>1w</b> — 1 hafta",
            parse_mode="HTML",
        )
        return

    data = await state.get_data()
    code = data["code"]

    now_local = datetime.now(TZ)
    expires_at = now_local + timedelta(hours=hours)
    expires_at_iso = expires_at.isoformat()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/attendance/session/",
            json={
                "code": code,
                "expires_at": expires_at_iso,
                "created_by": str(message.from_user.id),
            },
        ) as resp:
            if resp.status == 201:
                await message.answer(
                    f"✅ Davomat sessiyasi ochildi!\n\n"
                    f"🔑 Kod: <b>{code}</b>\n"
                    f"⏱ Tugaydi: <b>{expires_at.strftime('%d.%m.%Y %H:%M')}</b> ({label})",
                    parse_mode="HTML",
                )
                logger.info(f"Admin {message.from_user.id} sessiya ochdi: kod={code}, {label}")
            else:
                body = await resp.text()
                logger.error(f"Sessiya ochishda xatolik: status={resp.status}, body={body[:200]}")
                await message.answer("❌ Sessiya ochishda xatolik yuz berdi. Qayta urinib ko'ring.")

    await state.finish()


# ─── Talaba: davomat qo'yish ──────────────────────────────────────────────────

@dp.message_handler(lambda m: m.text == "🗓 Davomat")
async def attendance_mark_start(message: types.Message):
    guard_msg = await course_guard_message()
    if guard_msg:
        await message.answer(guard_msg)
        return
    await message.answer("🔑 Bugungi dars kodini kiriting:")
    await AttendanceMarkState.waiting_for_code.set()


@dp.message_handler(state=AttendanceMarkState.waiting_for_code)
async def attendance_mark_code(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("Bekor qilindi.")
        return

    code = message.text.strip()
    telegram_id = str(message.from_user.id)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{API_BASE_URL}/attendance/mark/",
            json={"telegram_id": telegram_id, "code": code},
        ) as resp:
            if resp.status == 201:
                data = await resp.json()
                await message.answer(
                    f"✅ Davomat qo'yildi!\n📅 Sana: {data.get('session_date', '')}"
                )
            elif resp.status == 409:
                await message.answer("ℹ️ Siz bugungi darsda allaqachon davomat qo'ygansiz.")
            elif resp.status == 404:
                await message.answer("❌ Siz ro'yxatdan o'tmagansiz.")
            else:
                await message.answer("❌ Kod noto'g'ri yoki muddati tugagan.")

    await state.finish()
