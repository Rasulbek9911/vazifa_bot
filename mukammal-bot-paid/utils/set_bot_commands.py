from aiogram import types
from data.config import ADMINS


async def set_default_commands(dp):
    # Oddiy userlar uchun (commandlar ko'rinmaydi)
    await dp.bot.set_my_commands([])
    
    # Adminlar uchun
    admin_commands = [
        types.BotCommand("topics", "O'tilgan mavzuni belgilash"),
        types.BotCommand("addtest", "Mavzuga test qo'shish"),
        # types.BotCommand("help", "Yordam"),
    ]
    
    for admin_id in ADMINS:
        try:
            await dp.bot.set_my_commands(
                admin_commands,
                scope=types.BotCommandScopeChat(chat_id=int(admin_id))
            )
        except Exception:
            pass

