from aiogram import types

from loader import dp


# Echo command only, to avoid catching all messages
@dp.message_handler(commands=["echo"], state="*")
async def bot_echo(message: types.Message):
    # Reply with the text after the command, or echo the whole message if none
    text = message.get_args() if hasattr(message, "get_args") else None
    await message.answer(text or message.text)
