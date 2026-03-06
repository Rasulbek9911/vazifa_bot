from aiogram.dispatcher.filters.state import State, StatesGroup

class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_group_selection = State()
