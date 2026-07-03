from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

vazifa_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='📝 Test yuborish'),
            # KeyboardButton(text='📋 Maxsus topshiriq yuborish'),
            KeyboardButton(text='🗓 Davomat'),
        ],
        [
            KeyboardButton(text='👤 Profil'),
            KeyboardButton(text='🏆 Reyting'),
        ],
        [
            KeyboardButton(text='📊 Natijalarim'),
            KeyboardButton(text='🪙 Tangalarim'),
        ],
    ],
    resize_keyboard=True
)

admin_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='🔧 Test javoblarini o\'zgartirish'),
            KeyboardButton(text="➕ Mavzu qo'shish"),
        ],
        [
            KeyboardButton(text='📢 Broadcast'),
            KeyboardButton(text='📅 Davomat sessiyasi'),
        ],
    ],
    resize_keyboard=True
)

cancel_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='❌ Bekor qilish'),
        ],
    ],
    resize_keyboard=True
)