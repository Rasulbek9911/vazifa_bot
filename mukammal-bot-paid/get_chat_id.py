"""
Guruh/kanal ID'sini olish uchun yordamchi skript
Bot'ni guruhga qo'shing va bu skriptni ishga tushiring
"""
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from data.config import BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=['chatid', 'id'])
async def get_chat_id(message: types.Message):
    """Guruh/kanal ID'sini ko'rsatadi"""
    chat_id = message.chat.id
    chat_type = message.chat.type
    chat_title = message.chat.title or "Private chat"
    
    info = f"""
📋 **Guruh Ma'lumotlari:**

🆔 Chat ID: `{chat_id}`
📁 Chat Type: `{chat_type}`
📝 Title: {chat_title}
    """
    
    await message.answer(info)
    print(f"\n{'='*50}")
    print(f"Chat ID: {chat_id}")
    print(f"Type: {chat_type}")
    print(f"Title: {chat_title}")
    print(f"{'='*50}\n")

if __name__ == '__main__':
    print("Bot ishga tushdi! Guruhga /chatid yuboring")
    executor.start_polling(dp, skip_updates=True)
