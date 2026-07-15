from aiogram.dispatcher.filters.state import State, StatesGroup


class SettingsState(StatesGroup):
    waiting_for_days_selection = State()
    waiting_for_time_input = State()
