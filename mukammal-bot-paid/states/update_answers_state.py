from aiogram.dispatcher.filters.state import State, StatesGroup

class UpdateAnswersState(StatesGroup):
    """Test javoblarini o'zgartirish uchun state"""
    waiting_for_topic = State()  # Topic tanlash
    waiting_for_new_answers = State()  # Yangi javoblarni kutish
