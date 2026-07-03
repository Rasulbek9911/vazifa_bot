from aiogram.dispatcher.filters.state import State, StatesGroup


class GrpTestState(StatesGroup):
    selecting_topics = State()
    selecting_month = State()
