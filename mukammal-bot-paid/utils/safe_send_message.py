from aiogram.utils.exceptions import BotBlocked, ChatNotFound, Unauthorized, RetryAfter
import asyncio
from data.config import ADMINS
from loader import bot
# --- xavfsiz xabar yuborish helper ---
async def safe_send_message(user_id: int, text: str):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    try:
        await bot.send_message(user_id, text)
    except BotBlocked:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            text="Chatga o'tish",
            url=f"tg://user?id={user_id}"
        ))
        await bot.send_message(ADMINS[0], f"⚠️ Student botni blok qildi.", reply_markup=kb)
    except ChatNotFound:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            text="Chatga o'tish",
            url=f"tg://user?id={user_id}"
        ))
        await bot.send_message(ADMINS[0], f"⚠️ Student uchun chat topilmadi.", reply_markup=kb)
    except Unauthorized:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            text="Chatga o'tish",
            url=f"tg://user?id={user_id}"
        ))
        await bot.send_message(ADMINS[0], f"⚠️ Student botni stop qildi.", reply_markup=kb)
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        await safe_send_message(user_id, text)
    except Exception as e:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(
            text="Chatga o'tish",
            url=f"tg://user?id={user_id}"
        ))
        await bot.send_message(ADMINS[0], f"❌ Studentga xabar yuborilmadi: {e}", reply_markup=kb)
