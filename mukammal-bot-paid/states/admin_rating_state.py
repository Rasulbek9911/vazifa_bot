from aiogram.dispatcher.filters.state import State, StatesGroup


class AdminRatingState(StatesGroup):
    waiting_period = State()
