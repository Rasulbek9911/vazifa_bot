from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

vazifa_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='📝 Test yuborish'),
            KeyboardButton(text='📋 Maxsus topshiriq yuborish'),
        ],
        [
            KeyboardButton(text='👤 Profil'),
        ],
        [
            KeyboardButton(text='📊 Natijalarim'),
        ],
    ],
    resize_keyboard=True
)

admin_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='🔧 Test javoblarini o\'zgartirish'),
            KeyboardButton(text = "➕ Mavzu qo'shish"),
        ],
        [
            KeyboardButton(text='📢 Broadcast'),
        ]
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