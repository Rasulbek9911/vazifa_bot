from aiogram.dispatcher.filters.state import State, StatesGroup

class TaskState(StatesGroup):
    course_type = State()
    topic = State()
    file = State()