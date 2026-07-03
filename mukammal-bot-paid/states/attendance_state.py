from aiogram.dispatcher.filters.state import State, StatesGroup


class AttendanceSessionState(StatesGroup):
    waiting_for_code = State()      # Admin: davomat kodini kiritadi
    waiting_for_duration = State()  # Admin: necha soat amal qilishini kiritadi


class AttendanceMarkState(StatesGroup):
    waiting_for_code = State()      # Talaba: dars kodini kiritadi
