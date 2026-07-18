from aiogram.dispatcher.filters.state import State, StatesGroup

class ManageCourseState(StatesGroup):
    """Kursni tahrirlash (nomini o'zgartirish) uchun state"""
    waiting_for_new_name = State()
