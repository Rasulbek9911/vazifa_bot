from aiogram.dispatcher.filters.state import State, StatesGroup


class RegisterState(StatesGroup):
    full_name  = State()
    viloyat    = State()
    tuman      = State()
    phone      = State()
    math_score = State()
    change_name = State()
