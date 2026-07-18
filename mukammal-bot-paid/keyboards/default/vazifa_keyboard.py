from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from asgiref.sync import sync_to_async

vazifa_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='📝 Test yuborish'),
            KeyboardButton(text='🗓 Davomat'),
        ],
        [
            KeyboardButton(text='👤 Profil'),
            KeyboardButton(text='🏆 Reyting'),
        ],
        [
            KeyboardButton(text='📊 Natijalarim'),
            KeyboardButton(text='🪙 Tangalarim'),
        ],
    ],
    resize_keyboard=True
)


@sync_to_async
def _student_has_assignment_course(telegram_id) -> bool:
    """Student a'zo bo'lgan faol kurslardan birortasida has_assignments=True bo'lsa True"""
    from base_app.models import Student

    try:
        student = Student.objects.get(telegram_id=str(telegram_id))
    except Student.DoesNotExist:
        return False

    return student.groups.filter(
        course__is_active=True, course__has_assignments=True
    ).exists()


async def build_vazifa_keyboard(telegram_id) -> ReplyKeyboardMarkup:
    """Studentning kurslariga qarab 'Maxsus topshiriq yuborish' tugmasini shartli qo'shadi"""
    show_assignment = await _student_has_assignment_course(telegram_id)

    first_row = [KeyboardButton(text='📝 Test yuborish')]
    if show_assignment:
        first_row.append(KeyboardButton(text='📋 Maxsus topshiriq yuborish'))
    first_row.append(KeyboardButton(text='🗓 Davomat'))

    return ReplyKeyboardMarkup(
        keyboard=[
            first_row,
            [
                KeyboardButton(text='👤 Profil'),
                KeyboardButton(text='🏆 Reyting'),
            ],
            [
                KeyboardButton(text='📊 Natijalarim'),
                KeyboardButton(text='🪙 Tangalarim'),
            ],
        ],
        resize_keyboard=True
    )

admin_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='🔧 Test javoblarini o\'zgartirish'),
            KeyboardButton(text="➕ Mavzu qo'shish"),
        ],
        [
            KeyboardButton(text='📢 Broadcast'),
            KeyboardButton(text='📅 Davomat sessiyasi'),
        ],
        [
            KeyboardButton(text="➕ Kurs qo'shish"),
            KeyboardButton(text="📚 Kurslarni boshqarish"),
        ],
    ],
    resize_keyboard=True
)

cancel_key = ReplyKeyboardMarkup(
    keyboard = [
        [
            KeyboardButton(text='❌ Bekor qilish'),
        ],
    ],
    resize_keyboard=True
)