from aiogram.dispatcher.filters.state import State, StatesGroup

class AddCourseState(StatesGroup):
    """Yangi kurs yaratish uchun state"""
    waiting_for_name = State()  # Kurs nomini kutish
    waiting_for_task_type = State()  # Vazifa turini kutish (test/assignment)
