from aiogram.utils.exceptions import BotBlocked, ChatNotFound, Unauthorized, RetryAfter
import asyncio
from data.config import ADMINS
from loader import bot
# --- xavfsiz xabar yuborish helper ---
async def safe_send_message(user_id: int, text: str):
    try:
        await bot.send_message(user_id, text)
    except BotBlocked:
        await bot.send_message(ADMINS[0], f"⚠️ Student {user_id} botni blok qildi.")
    except ChatNotFound:
        await bot.send_message(ADMINS[0], f"⚠️ Student {user_id} uchun chat topilmadi.")
    except Unauthorized:
        await bot.send_message(ADMINS[0], f"⚠️ Student {user_id} botni stop qildi.")
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        await safe_send_message(user_id, text)
    except Exception as e:
        await bot.send_message(ADMINS[0], f"❌ Student {user_id} ga xabar yuborilmadi: {e}")
