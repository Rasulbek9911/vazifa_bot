from aiogram.dispatcher.filters.state import State, StatesGroup

class AddTopicState(StatesGroup):
    """Yangi mavzu qo'shish uchun state"""
    waiting_for_course = State()  # Kurs tanlash (milliy_sert yoki attestatsiya)
    waiting_for_title = State()  # Mavzu nomini kutish
    waiting_for_deadline = State()  # Deadline ni kutish
