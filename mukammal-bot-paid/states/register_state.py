from aiogram.dispatcher.filters.state import State, StatesGroup


class RegisterState(StatesGroup):
    full_name  = State()
    course     = State()
    viloyat    = State()
    tuman      = State()
    phone      = State()
    role       = State()
    math_score = State()
    change_name = State()
