from aiogram.dispatcher.filters.state import State, StatesGroup

class RegisterState(StatesGroup):
    invite_code = State()
    full_name = State()
    group = State()

