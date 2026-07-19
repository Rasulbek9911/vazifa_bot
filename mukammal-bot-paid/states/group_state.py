from aiogram.dispatcher.filters.state import State, StatesGroup


class AddGroupState(StatesGroup):
    """Yangi guruh yaratish uchun state"""
    waiting_for_name = State()
    waiting_for_telegram_id = State()
    waiting_for_score_min = State()
    waiting_for_score_max = State()
    waiting_for_max_students = State()
    waiting_for_target_role = State()


class EditGroupState(StatesGroup):
    """Mavjud guruhni tahrirlash uchun state"""
    waiting_for_new_name = State()
    waiting_for_new_telegram_id = State()
    waiting_for_new_score_min = State()
    waiting_for_new_score_max = State()
    waiting_for_new_max_students = State()
