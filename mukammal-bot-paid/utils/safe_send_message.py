from aiogram.utils.exceptions import BotBlocked, ChatNotFound, Unauthorized, RetryAfter
import asyncio
from data.config import ADMINS
from loader import bot

async def safe_send_message(user_id: int, text: str, parse_mode: str = None):
    try:
        await bot.send_message(user_id, text, parse_mode=parse_mode)
    except BotBlocked:
        try:
            await bot.send_message(ADMINS[0], f"⚠️ {user_id} student botni blok qildi.")
        except Exception:
            pass
    except ChatNotFound:
        try:
            await bot.send_message(ADMINS[0], f"⚠️ {user_id} student uchun chat topilmadi.")
        except Exception:
            pass
    except Unauthorized:
        try:
            await bot.send_message(ADMINS[0], f"⚠️ {user_id} student botni stop qildi.")
        except Exception:
            pass
    except RetryAfter as e:
        await asyncio.sleep(e.timeout)
        await safe_send_message(user_id, text, parse_mode=parse_mode)
    except Exception:
        pass
