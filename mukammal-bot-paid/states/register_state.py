from aiogram.dispatcher.filters.state import State, StatesGroup

class RegisterState(StatesGroup):
    """User registration states - only full_name needed (no invite code)"""
    full_name = State()
    group = State()  # Optional - for future use
    change_name = State()  # For profile name change

