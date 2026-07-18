"""
Admin-specific handlers: topic management, grading
"""
from aiogram import types
import aiohttp
from django.db.models import F as models_F
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL, MILLIY_ADMIN, ATTESTATSIYA_ADMIN
from loader import dp, bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message
from states.broadcast_state import BroadcastState
from states.update_answers_state import UpdateAnswersState
from states.add_topic_state import AddTopicState
from states.add_course_state import AddCourseState
from states.manage_course_state import ManageCourseState
from states.grp_test_state import GrpTestState
from states.settings_state import SettingsState
from utils.scheduler_instance import (
    JOB_LABELS, DAY_LABELS, DAY_ORDER, DEFAULT_SCHEDULE,
    days_str_to_label, apply_job, remove_job,
)

MONTH_NAMES_UZ = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
    5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
    9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr",
}


async def _get_coin_months(course_id: int, student_ids=None):
    from base_app.models import CoinTransaction
    qs = CoinTransaction.objects.filter(wallet__course_id=course_id)
    if student_ids:
        qs = qs.filter(wallet__student_id__in=student_ids)
    return await sync_to_async(list)(qs.dates('topic__activated_at', 'month', order='DESC'))


async def _get_task_months(topic_ids: list, student_ids=None):
    from base_app.models import Task
    qs = Task.objects.filter(
        topic_id__in=topic_ids, task_type='test'
    ).exclude(test_answers='').exclude(test_answers__isnull=True)
    if student_ids:
        qs = qs.filter(student_id__in=student_ids)
    return await sync_to_async(list)(qs.dates('submitted_at', 'month', order='DESC'))


def _build_month_kb(months: list, gen_prefix: str, back_cb: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("📋 Barcha vaqt", callback_data=f"{gen_prefix}_0_0"))
    for d in months:
        kb.add(InlineKeyboardButton(
            f"📅 {MONTH_NAMES_UZ[d.month]} {d.year}",
            callback_data=f"{gen_prefix}_{d.year}_{d.month}"
        ))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data=back_cb))
    return kb
from filters.is_private import IsPrivate


# --- Baho qo'yish ---
@dp.callback_query_handler(lambda c: c.data.startswith("grade_"))
async def set_grade(callback: types.CallbackQuery):
    # Barcha adminlar va kurs adminlari baho qo'yishi mumkin
    # Kurs adminini tekshirish uchun taskni yuklaymiz
    _, task_id, grade = callback.data.split("_")
    
    # Taskni olish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/tasks/{task_id}/") as resp_task:
            if resp_task.status != 200:
                await callback.answer("❌ Task topilmadi!", show_alert=True)
                return
            task_data = await resp_task.json()
    
    # Kurs adminini tekshiramiz
    topic_data = task_data.get("topic", {})
    course_admin_id = None
    if topic_data.get("course"):
        course_admin_id = topic_data["course"].get("admin_telegram_id")
    
    # Ruxsat tekshiruvi: ADMINS, course admin, yoki eski MILLIY/ATTESTATSIYA adminlar
    user_id = str(callback.from_user.id)
    allowed_admins = ADMINS + [MILLIY_ADMIN, ATTESTATSIYA_ADMIN]
    if course_admin_id:
        allowed_admins.append(course_admin_id)
    
    if user_id not in allowed_admins:
        await callback.answer("❌ Sizda baho qo'yish huquqi yo'q.", show_alert=True)
        return
    
    payload = {"grade": int(grade)}

    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{API_BASE_URL}/tasks/{task_id}/", json=payload) as resp:
            if resp.status == 200:
                task = await resp.json()
                student_id = task["student"]["telegram_id"]
                student_name = task["student"]["full_name"]
                
                # Birinchi guruhni olish
                all_groups = task["student"].get("all_groups", [])
                group_name = all_groups[0]["name"] if all_groups else "N/A"
                
                topic_title = task["topic"]["title"]

                # ✅ Studentga yuborish
                await safe_send_message(
                    student_id,
                    f"📊 Sizning vazifangiz {grade} bahoga baholandi ✅"
                )

                # ✅ Admin tarafida captionni yangilash
                new_caption = (
                    f"📥 Vazifa baholandi!\n\n"
                    f"👤 Student: {student_name}\n"
                    f"👥 Guruh: {group_name}\n"
                    f"📚 Mavzu: {topic_title}\n"
                    f"📊 Baho: {grade} ✅"
                )

                try:
                    await callback.message.edit_caption(
                        caption=new_caption,
                        reply_markup=None  # baholash tugmalari olib tashlanadi
                    )
                except Exception as e:
                    print("❌ Caption o'zgartirishda xato:", e)

                await callback.answer("✅ Baho qo'yildi", show_alert=True)

            else:
                await callback.answer("❌ Xatolik yuz berdi", show_alert=True)


@dp.message_handler(IsPrivate(), commands=["topics"], user_id=ADMINS)
async def show_all_topics(message: types.Message):
    import html
    from base_app.models import Topic
    topics = await sync_to_async(list)(Topic.objects.all())

    if not topics:
        await message.answer("❌ Hozircha mavzular mavjud emas.")
        return

    def get_course_code(topic):
        return topic.course.code if topic.course else None
    
    # Kurslar bo'yicha guruhlash
    topics_by_course = {}
    for t in topics:
        course_code = get_course_code(t)
        if course_code not in topics_by_course:
            topics_by_course[course_code] = []
        topics_by_course[course_code].append(t)
    
    text = "📌 Barcha mavzular:\n\n"
    
    # Har bir kurs uchun chiqarish
    course_names = {
        'milliy_sert': 'Milliy Sertifikat',
        'attestatsiya': 'Attestatsiya'
    }
    
    for course_code, course_topics in topics_by_course.items():
        course_name = course_names.get(course_code, course_code.title())
        text += f"🔹 <b>{course_name}</b>:\n"
        for t in course_topics:
            status = "✅ Active" if t.is_active else "❌ Inactive"
            title = html.escape(t.title)
            text += f"  <b>{t.id}.</b> {title} — {status}\n"
        text += "\n"

    text += "🔹 Biror mavzuni active qilish uchun: <code>/activate &lt;id&gt;</code>"

    await message.answer(text, parse_mode="HTML")


@dp.message_handler(IsPrivate(), commands=["activate"], user_id=ADMINS)
async def activate_topic(message: types.Message):
    from base_app.models import Topic, Student, Group

    args = message.get_args()
    if not args.isdigit():
        await message.answer(
            "❌ Iltimos, mavzu ID sini kiriting. Masalan: <code>/activate 2</code>",
            parse_mode="HTML"
        )
        return

    topic_id = int(args)

    # Mavzuni topamiz
    try:
        topic = await sync_to_async(Topic.objects.select_related('course').get)(id=topic_id)
    except Topic.DoesNotExist:
        await message.answer("❌ Bunday ID li mavzu topilmadi.")
        return

    # Nofaol kurs mavzusini activate qilib bo'lmaydi
    if topic.course and not topic.course.is_active:
        await message.answer(
            f"❌ <b>{topic.course.name}</b> kursi yakunlangan.\n"
            f"Nofaol kurs mavzusini active qilib bo'lmaydi.",
            parse_mode="HTML"
        )
        return

    # Agar allaqachon active bo'lsa
    if topic.is_active:
        await message.answer(
            f"⚠️ <b>{topic.title}</b> mavzu allaqachon active!\n"
            f"Studentlarga qayta xabar yuborishni xohlaysizmi?",
            parse_mode="HTML"
        )
        # Davom etamiz - qayta xabar yuboriladi

    # ✅ is_active = True qilamiz
    topic.is_active = True
    await sync_to_async(topic.save)()

    # Topic kursini aniqlaymiz (backward compatibility)
    if not topic.course:
        await message.answer("❌ Bu mavzuga kurs biriktirilmagan. Admin paneldan kurs belgilang.")
        return

    topic_course_code = topic.course.code
    topic_course_name = topic.course.name

    await message.answer(
        f"✅ <b>{topic.title}</b> mavzu <b>Active</b> qilindi!\n"
        f"📚 Kurs: {topic_course_name}\n"
        f"👥 Faqat {topic_course_name} kursidagi studentlarga xabar yuboriladi.",
        parse_mode="HTML"
    )

    groups = await sync_to_async(list)(
        Group.objects.filter(course=topic.course).prefetch_related('enrolled_students')
    )
    
    # Unique studentlarni to'playmiz (bir student bir nechta guruhda bo'lishi mumkin)
    notified_students = set()
    notify_text = f"📚 Yangi mavzu active qilindi:\n<b>{topic.title}</b>\n\n" \
                  "📤 Vazifani yuborishingiz mumkin!"
    
    for group in groups:
        students = await sync_to_async(list)(group.enrolled_students.all())
        for student in students:
            # Agar bu studentga xabar yuborilmagan bo'lsa
            if student.telegram_id not in notified_students:
                await safe_send_message(student.telegram_id, notify_text)
                notified_students.add(student.telegram_id)
    
    await message.answer(f"✅ {len(notified_students)} ta studentga xabar yuborildi.", parse_mode="HTML")


# --- Barcha userlarga xabar yuborish ---
@dp.message_handler(IsPrivate(), commands=["broadcast"], user_id=ADMINS)
@dp.message_handler(IsPrivate(), lambda msg: msg.text == "📢 Broadcast", user_id=ADMINS)
async def start_broadcast(message: types.Message, state: FSMContext):
    """Admin broadcast jarayonini boshlaydi — avval auditoriya so'raladi"""
    await state.update_data(
        selected_groups=[],
        audience_mode=None,
        session_id=None,
    )

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton(text="👥 Hammaga (guruh tanlab)", callback_data="broadcast_audience_all"),
        InlineKeyboardButton(text="📵 Faqat davomat qilmaganlarga", callback_data="broadcast_audience_absent"),
    )

    await message.answer(
        "📢 Broadcast\n\n"
        "🎯 Kimga yuborilsin?",
        reply_markup=keyboard
    )
    await BroadcastState.waiting_for_audience_type.set()


async def _build_group_selection_keyboard(groups, selected_groups):
    """Guruh tanlash (multiselect) keyboardini quradi — 'hammaga' va 'davomat' oqimlari uchun umumiy"""
    keyboard = InlineKeyboardMarkup(row_width=1)

    for group in groups:
        student_count = await sync_to_async(group.enrolled_students.count)()
        course_name = group.course.name if group.course else "N/A"
        checkbox = "✅" if group.id in selected_groups else "☐"
        keyboard.add(
            InlineKeyboardButton(
                text=f"{checkbox} {course_name} - {group.name} ({student_count} ta)",
                callback_data=f"broadcast_toggle_{group.id}"
            )
        )

    total_students = sum([await sync_to_async(g.enrolled_students.count)() for g in groups])
    all_group_ids = [g.id for g in groups]
    all_selected = bool(all_group_ids) and set(selected_groups) == set(all_group_ids)

    keyboard.add(
        InlineKeyboardButton(
            text=("❌ Barchasini bekor qilish" if all_selected else f"📢 Barcha guruhlarni tanlash ({total_students} ta)"),
            callback_data="broadcast_select_all"
        )
    )

    selected_student_count = 0
    for group in groups:
        if group.id in selected_groups:
            selected_student_count += await sync_to_async(group.enrolled_students.count)()

    keyboard.add(
        InlineKeyboardButton(
            text=f"➡️ Davom etish ({len(selected_groups)} ta guruh, {selected_student_count} ta student)",
            callback_data="broadcast_groups_confirm"
        )
    )
    return keyboard


@dp.callback_query_handler(lambda c: c.data == "broadcast_audience_all", state=BroadcastState.waiting_for_audience_type)
async def broadcast_audience_all(callback: types.CallbackQuery, state: FSMContext):
    """'Hammaga' tanlandi — to'g'ridan-to'g'ri guruh tanlash ekraniga o'tamiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group

    await state.update_data(audience_mode='all', session_id=None)

    groups = await sync_to_async(list)(
        Group.objects.select_related('course').prefetch_related('enrolled_students').all()
    )
    if not groups:
        await callback.message.edit_text("❌ Hech qanday guruh topilmadi.")
        await state.finish()
        return

    keyboard = await _build_group_selection_keyboard(groups, [])
    await callback.message.edit_text(
        "👥 Guruh(lar)ni tanlang:\n"
        "☐ - tanlanmagan\n"
        "✅ - tanlangan\n\n"
        "📭 Hech qanday guruh tanlanmagan",
        reply_markup=keyboard
    )
    await BroadcastState.waiting_for_group_selection.set()
    await callback.answer()


SESSIONS_PAGE_SIZE = 8


async def _build_sessions_page(page: int):
    """Davomat sessiyalari ro'yxatini sahifalab ko'rsatadi (page 1-based)"""
    from base_app.models import AttendanceSession
    from django.utils import timezone as dj_timezone

    sessions = await sync_to_async(list)(
        AttendanceSession.objects.order_by('-created_at')
    )
    if not sessions:
        return None, None

    total = len(sessions)
    total_pages = max(1, (total + SESSIONS_PAGE_SIZE - 1) // SESSIONS_PAGE_SIZE)
    page = max(1, min(page, total_pages))

    start = (page - 1) * SESSIONS_PAGE_SIZE
    page_items = sessions[start:start + SESSIONS_PAGE_SIZE]

    now = dj_timezone.now()
    keyboard = InlineKeyboardMarkup(row_width=1)
    for session in page_items:
        created_local = dj_timezone.localtime(session.created_at)
        status = "🟢" if session.is_active and session.expires_at > now else "🔴"
        keyboard.add(
            InlineKeyboardButton(
                text=f"{status} {session.code} — {created_local.strftime('%d.%m %H:%M')}",
                callback_data=f"broadcast_session_{session.id}"
            )
        )

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀", callback_data=f"broadcast_sessions_page:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="broadcast_sessions_noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶", callback_data=f"broadcast_sessions_page:{page+1}"))
    keyboard.add(*nav)

    text = (
        f"📅 Qaysi davomat sessiyasiga qatnashmaganlarga xabar yuborilsin? ({page}/{total_pages} sahifa, jami {total} ta)\n\n"
        "🟢 - faol, 🔴 - tugagan"
    )
    return text, keyboard


@dp.callback_query_handler(lambda c: c.data == "broadcast_audience_absent", state=BroadcastState.waiting_for_audience_type)
async def broadcast_audience_absent(callback: types.CallbackQuery, state: FSMContext):
    """'Davomat qilmaganlarga' tanlandi — sessiyalar ro'yxatini (sahifalab) ko'rsatamiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    text, keyboard = await _build_sessions_page(1)
    if text is None:
        await callback.message.edit_text("❌ Hech qanday davomat sessiyasi topilmagan.")
        await state.finish()
        return

    await callback.message.edit_text(text, reply_markup=keyboard)
    await BroadcastState.waiting_for_session_selection.set()
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("broadcast_sessions_page:"), state=BroadcastState.waiting_for_session_selection)
async def broadcast_sessions_page(callback: types.CallbackQuery, state: FSMContext):
    """Sessiyalar ro'yxatida sahifa almashtirish"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    page = int(callback.data.split(":")[1])
    text, keyboard = await _build_sessions_page(page)
    if text is None:
        await callback.message.edit_text("❌ Hech qanday davomat sessiyasi topilmagan.")
        await state.finish()
        return

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "broadcast_sessions_noop", state=BroadcastState.waiting_for_session_selection)
async def broadcast_sessions_noop(callback: types.CallbackQuery):
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("broadcast_session_"), state=BroadcastState.waiting_for_session_selection)
async def broadcast_session_select(callback: types.CallbackQuery, state: FSMContext):
    """Sessiya tanlandi — endi qaysi guruh shu darsga qatnashishi kerakligini so'raymiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group, AttendanceSession

    session_id = int(callback.data.split("_")[2])
    session = await sync_to_async(AttendanceSession.objects.filter(id=session_id).first)()
    if not session:
        await callback.answer("❌ Sessiya topilmadi.", show_alert=True)
        return

    await state.update_data(audience_mode='absent', session_id=session_id)

    groups = await sync_to_async(list)(
        Group.objects.select_related('course').prefetch_related('enrolled_students').all()
    )
    if not groups:
        await callback.message.edit_text("❌ Hech qanday guruh topilmadi.")
        await state.finish()
        return

    keyboard = await _build_group_selection_keyboard(groups, [])
    await callback.message.edit_text(
        f"📵 Sessiya: <b>{session.code}</b>\n\n"
        "👥 Ushbu darsga qaysi guruh talabalari qatnashishi kerak edi? Guruh(lar)ni tanlang:\n"
        "☐ - tanlanmagan\n"
        "✅ - tanlangan\n\n"
        "📭 Hech qanday guruh tanlanmagan",
        reply_markup=keyboard,
        parse_mode="HTML"
    )
    await BroadcastState.waiting_for_group_selection.set()
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("broadcast_toggle_"), state=BroadcastState.waiting_for_group_selection)
async def toggle_group_selection(callback: types.CallbackQuery, state: FSMContext):
    """Guruhni tanlash/bekor qilish (toggle)"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    
    from base_app.models import Group, AttendanceSession

    # Qaysi guruh bosilganini aniqlaymiz
    group_id = int(callback.data.split("_")[2])

    # State dan tanlangan guruhlarni olamiz
    data = await state.get_data()
    selected_groups = data.get('selected_groups', [])

    # Toggle: agar tanlangan bo'lsa - olib tashlaymiz, aks holda qo'shamiz
    if group_id in selected_groups:
        selected_groups.remove(group_id)
    else:
        selected_groups.append(group_id)

    # State ni yangilaymiz
    await state.update_data(selected_groups=selected_groups)

    groups = await sync_to_async(list)(
        Group.objects.select_related('course').prefetch_related('enrolled_students').all()
    )
    keyboard = await _build_group_selection_keyboard(groups, selected_groups)

    selected_student_count = 0
    for group in groups:
        if group.id in selected_groups:
            selected_student_count += await sync_to_async(group.enrolled_students.count)()

    # Xabar matnini ham yangilaymiz - tanlangan guruhlar ko'rinsin
    message_text = ""
    if data.get('audience_mode') == 'absent' and data.get('session_id'):
        session = await sync_to_async(AttendanceSession.objects.filter(id=data['session_id']).first)()
        if session:
            message_text += f"📵 Sessiya: {session.code}\n\n"
    message_text += (
        "👥 Guruh(lar)ni tanlang:\n"
        "☐ - tanlanmagan\n"
        "✅ - tanlangan\n\n"
    )

    if selected_groups:
        message_text += f"📊 Tanlandi: {len(selected_groups)} ta guruh, {selected_student_count} ta student"
    else:
        message_text += "📭 Hech qanday guruh tanlanmagan"

    try:
        await callback.message.edit_text(
            text=message_text,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Message update error: {e}")

    await callback.answer(f"{'✅ Tanlandi' if group_id in selected_groups else '❌ Bekor qilindi'}")


@dp.callback_query_handler(lambda c: c.data == "broadcast_select_all", state=BroadcastState.waiting_for_group_selection)
async def select_all_groups(callback: types.CallbackQuery, state: FSMContext):
    """Barcha guruhlarni tanlash/bekor qilish"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    
    from base_app.models import Group, AttendanceSession

    # State dan tanlangan guruhlarni olamiz
    data = await state.get_data()
    selected_groups = data.get('selected_groups', [])

    # Barcha guruhlarni olamiz
    groups = await sync_to_async(list)(
        Group.objects.select_related('course').prefetch_related('enrolled_students').all()
    )

    all_group_ids = [g.id for g in groups]

    # Agar barcha tanlangan bo'lsa - barchasini bekor qilamiz, aks holda barchasini tanlaymiz
    if set(selected_groups) == set(all_group_ids):
        selected_groups = []
    else:
        selected_groups = all_group_ids.copy()

    # State ni yangilaymiz
    await state.update_data(selected_groups=selected_groups)

    keyboard = await _build_group_selection_keyboard(groups, selected_groups)
    all_selected = len(selected_groups) == len(all_group_ids)

    selected_student_count = 0
    for group in groups:
        if group.id in selected_groups:
            selected_student_count += await sync_to_async(group.enrolled_students.count)()

    # Xabar matnini ham yangilaymiz
    message_text = ""
    if data.get('audience_mode') == 'absent' and data.get('session_id'):
        session = await sync_to_async(AttendanceSession.objects.filter(id=data['session_id']).first)()
        if session:
            message_text += f"📵 Sessiya: {session.code}\n\n"
    message_text += (
        "👥 Guruh(lar)ni tanlang:\n"
        "☐ - tanlanmagan\n"
        "✅ - tanlangan\n\n"
    )

    if selected_groups:
        message_text += f"📊 Tanlandi: {len(selected_groups)} ta guruh, {selected_student_count} ta student"
    else:
        message_text += "📭 Hech qanday guruh tanlanmagan"

    try:
        await callback.message.edit_text(
            text=message_text,
            reply_markup=keyboard
        )
    except Exception as e:
        print(f"Message update error: {e}")

    await callback.answer(f"{'✅ Hammasi tanlandi!' if all_selected else '❌ Hammasi bekor qilindi!'}")


async def _resolve_broadcast_targets(data):
    """State ma'lumotlari asosida (guruhlar + auditoriya rejimi) yuboriladigan studentlar ro'yxatini hisoblaydi.

    Qaytaradi: (students_list, group_names, session_label) yoki xatolik bo'lsa (None, error_text, None)
    """
    from base_app.models import Group, Attendance, AttendanceSession

    selected_groups = data.get('selected_groups', [])
    audience_mode = data.get('audience_mode', 'all')
    session_id = data.get('session_id')

    if not selected_groups:
        return None, "❌ Hech qanday guruh tanlanmagan!", None

    groups = await sync_to_async(list)(
        Group.objects.filter(id__in=selected_groups).select_related('course').prefetch_related('enrolled_students')
    )
    if not groups:
        return None, "❌ Guruhlar topilmadi!", None

    group_names = [f"{group.course.name if group.course else 'N/A'} - {group.name}" for group in groups]

    unique_students = {}
    for group in groups:
        students = await sync_to_async(list)(group.enrolled_students.all())
        for student in students:
            unique_students[student.id] = student

    students_list = list(unique_students.values())

    session_label = ""
    if audience_mode == 'absent' and session_id:
        session = await sync_to_async(AttendanceSession.objects.filter(id=session_id).first)()
        if not session:
            return None, "❌ Sessiya topilmadi!", None
        session_label = f"📵 Sessiya: {session.code}\n"

        attended_ids = set(await sync_to_async(list)(
            Attendance.objects.filter(
                session_id=session_id,
                student_id__in=list(unique_students.keys())
            ).values_list('student_id', flat=True)
        ))
        students_list = [s for s in students_list if s.id not in attended_ids]

    if not students_list:
        return None, "❌ Yuboriladigan student qolmadi (barchasi davomat qo'ygan yoki guruhda studentlar yo'q)!", None

    return students_list, group_names, session_label


@dp.callback_query_handler(lambda c: c.data == "broadcast_groups_confirm", state=BroadcastState.waiting_for_group_selection)
async def broadcast_groups_confirm(callback: types.CallbackQuery, state: FSMContext):
    """Guruh(lar) tanlandi — endi xabar matnini so'raymiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    data = await state.get_data()
    students_list, group_names_or_error, session_label = await _resolve_broadcast_targets(data)

    if students_list is None:
        await callback.answer(group_names_or_error, show_alert=True)
        return

    group_names = group_names_or_error

    await callback.message.edit_text(
        (session_label or "") +
        f"👥 Tanlangan guruhlar ({len(group_names)} ta):\n" +
        "\n".join([f"  • {name}" for name in group_names[:5]]) +
        (f"\n  • ... va yana {len(group_names) - 5} ta" if len(group_names) > 5 else "") +
        f"\n📝 Yuboriladigan studentlar: {len(students_list)} ta\n\n"
        "✍️ Endi yubormoqchi bo'lgan xabaringizni yuboring:\n"
        "⚠️ Xabar matn, rasm, video yoki hujjat bo'lishi mumkin.\n"
        "❌ Bekor qilish uchun: /cancel"
    )
    await BroadcastState.waiting_for_message.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=BroadcastState.waiting_for_message, user_id=ADMINS, content_types=types.ContentTypes.ANY)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    """Xabar qabul qilindi — avval tanlangan auditoriyaga yuboradi"""
    data = await state.get_data()
    students_list, group_names_or_error, session_label = await _resolve_broadcast_targets(data)

    if students_list is None:
        await message.answer(group_names_or_error)
        await state.finish()
        return

    group_names = group_names_or_error
    message_id = message.message_id
    from_chat_id = message.chat.id

    await message.answer(
        f"📤 Xabar yuborilmoqda...\n\n" +
        (session_label or "") +
        f"👥 Tanlangan guruhlar ({len(group_names)} ta):\n" +
        "\n".join([f"  • {name}" for name in group_names[:5]]) +
        (f"\n  • ... va yana {len(group_names) - 5} ta" if len(group_names) > 5 else "") +
        f"\n\n📝 Yuboriladigan studentlar: {len(students_list)} ta"
    )

    success_count = 0
    fail_count = 0

    # Xabarni copy qilish
    for student in students_list:
        try:
            await bot.copy_message(
                chat_id=student.telegram_id,
                from_chat_id=from_chat_id,
                message_id=message_id
            )
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"Failed to send to {student.telegram_id}: {e}")

    # Natijani ko'rsatish
    result_text = (
        f"✅ Xabar yuborish tugadi!\n\n" +
        (session_label or "") +
        f"👥 Tanlangan guruhlar: {len(group_names)} ta\n"
        f"📋 Guruhlar:\n" +
        "\n".join([f"  • {name}" for name in group_names[:5]]) +
        (f"\n  • ... va yana {len(group_names) - 5} ta" if len(group_names) > 5 else "") +
        f"\n\n📊 Natija:\n"
        f"✅ Muvaffaqiyatli: {success_count}\n"
        f"❌ Xato: {fail_count}\n"
        f"📝 Jami: {len(students_list)}"
    )

    await message.answer(result_text)
    await state.finish()


@dp.message_handler(IsPrivate(), commands=["cancel"], state="*", user_id=ADMINS)
async def cancel_broadcast(message: types.Message, state: FSMContext):
    """Broadcast jarayonini bekor qilish"""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("❌ Hech qanday jarayon yo'q.")
        return
    
    try:
        await state.finish()
    except KeyError:
        pass
    await message.answer("✅ Jarayon bekor qilindi.")


# --- ADMIN PANEL ---
@dp.message_handler(IsPrivate(), commands=["admin"], user_id=ADMINS)
async def admin_panel(message: types.Message):
    """Admin panel — barcha buyruqlar inline tugmalar orqali"""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Mavzu qo'shish\nYangi mavzu yaratish", callback_data="admin_menu_add_topic"),
        InlineKeyboardButton("🔧 Javoblarni o'zgartirish\nTest kalitini tahrirlash", callback_data="admin_menu_update_answers"),
    )
    kb.add(
        InlineKeyboardButton("📋 Barcha mavzular\nRo'yxat va holat", callback_data="admin_menu_topics"),
        InlineKeyboardButton("🧪 Test qo'shish\nMavzuga test biriktirish", callback_data="admin_menu_addtest"),
    )
    kb.add(
        InlineKeyboardButton("➕ Kurs qo'shish\nYangi kurs yaratish", callback_data="admin_menu_add_course"),
        InlineKeyboardButton("📚 Kurslarni boshqarish\nNomini o'zgartirish, o'chirish", callback_data="admin_menu_manage_courses"),
    )
    kb.add(
        InlineKeyboardButton("📢 Broadcast\nBarcha foydalanuvchilarga xabar", callback_data="admin_menu_broadcast"),
        InlineKeyboardButton("📊 Test statistikasi\nTopshiriqlar soni va foizi", callback_data="stats:1:all"),
    )
    kb.add(
        InlineKeyboardButton("📁 Hisobotlar\nPDF yuklab olish", callback_data="admin_menu_reports"),
        InlineKeyboardButton("📊 O'tgan natijalar\nOldingi test natijalari", callback_data="admin_menu_past_results"),
    )
    kb.add(
        InlineKeyboardButton("⏰ Deadline natijalari\nMuddati tugagan testlar", callback_data="admin_menu_deadline_results"),
        InlineKeyboardButton("📅 Davomat sessiyasi\nDars uchun kod ochish", callback_data="admin_menu_attendance"),
    )
    kb.add(
        InlineKeyboardButton("⚙️ Sozlamalar\nSchedule va haftalik PDF", callback_data="admin_menu_settings"),
    )
    await message.answer("👨‍💼 <b>Admin panel</b>\n\nKerakli amalni tanlang:", reply_markup=kb, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data.startswith("admin_menu_"))
async def admin_menu_dispatch(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    action = callback.data  # admin_menu_xxx

    # Hisobotlar submenyusi — message o'chirilmaydi, edit_text ishlatiladi
    if action == "admin_menu_reports":
        await reports_submenu(callback)
        return

    if action == "admin_menu_pdf":
        await pdf_select_course(callback)
        return

    if action == "admin_menu_coin_pdf":
        await coin_pdf_select_course(callback)
        return

    if action == "admin_menu_settings":
        await settings_menu(callback)
        return

    await callback.message.delete()

    if action == "admin_menu_add_topic":
        await add_topic_start(callback.message)
    elif action == "admin_menu_add_course":
        await add_course_start(callback.message)
    elif action == "admin_menu_manage_courses":
        await manage_courses_start(callback.message)
    elif action == "admin_menu_update_answers":
        await update_test_answers_start(callback.message)
    elif action == "admin_menu_broadcast":
        await start_broadcast(callback.message, state)
    elif action == "admin_menu_topics":
        await show_all_topics(callback.message)
    elif action == "admin_menu_addtest":
        from handlers.users.task_handlers import admin_add_test_start
        await admin_add_test_start(callback.message, state)
    elif action == "admin_menu_past_results":
        from handlers.users.task_handlers import admin_send_past_results
        await admin_send_past_results(callback.message, state)
    elif action == "admin_menu_deadline_results":
        from handlers.users.scheduled_tasks import send_deadline_results
        await callback.message.answer("⏳ Deadline natijalari yuborilmoqda...")
        try:
            await send_deadline_results()
            await callback.message.answer("✅ Deadline natijalari yuborildi!")
        except Exception as e:
            await callback.message.answer(f"❌ Xatolik: {str(e)[:200]}")
    elif action == "admin_menu_attendance":
        from handlers.users.attendance_handler import _open_attendance_session
        await _open_attendance_session(callback.message.chat.id)

    await callback.answer()


# --- TEST STATISTIKASI ---
PAGE_SIZE = 8

async def _build_stats_message(page: int, course_filter: str):
    """Statistika xabari va keyboardini yaratadi. (page 1-based, course_filter: 'all' yoki course.id)"""
    from base_app.models import Task, Course
    from django.db.models import Count

    # Kurslarni olamiz (filter tugmalari uchun — faol va nofaol)
    courses = await sync_to_async(list)(Course.objects.all().order_by('-is_active', 'name'))

    # Asosiy query
    qs = Task.objects.filter(task_type='test').exclude(test_code__isnull=True).exclude(test_code='')

    if course_filter != 'all':
        try:
            qs = qs.filter(topic__course__id=int(course_filter))
        except (ValueError, TypeError):
            pass

    # test_code bo'yicha guruhlab, unique studentlar sonini hisoblaymiz
    stats = await sync_to_async(list)(
        qs.values('test_code', 'topic__title', 'topic__course__name')
          .annotate(count=Count('student', distinct=True))
          .order_by('-topic__id')
    )

    total = len(stats)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))

    start = (page - 1) * PAGE_SIZE
    page_items = stats[start:start + PAGE_SIZE]

    # Xabar matni
    course_label = "Barchasi"
    for c in courses:
        if str(c.id) == course_filter:
            course_label = c.name
            break

    lines = [f"📊 <b>Test statistikasi</b>  ({page}/{total_pages} sahifa, jami {total} ta)\n"
             f"🗂 Kurs: <b>{course_label}</b>\n"]
    for item in page_items:
        code = item['test_code']
        count = item['count']
        topic_name = item['topic__title'] or code
        lines.append(f"🔑 <code>{code}</code> — 👥 <b>{count}</b> kishi\n   📚 {topic_name}")

    text = "\n".join(lines)

    # Keyboard
    kb = InlineKeyboardMarkup(row_width=3)

    # Kurs filter tugmalari
    filter_buttons = [InlineKeyboardButton(
        f"{'✅ ' if course_filter == 'all' else ''}Barchasi",
        callback_data="stats:1:all"
    )]
    for c in courses:
        prefix = '✅ ' if str(c.id) == course_filter else ''
        suffix = '' if c.is_active else ' 🔒'
        label = f"{prefix}{c.name}{suffix}"
        filter_buttons.append(InlineKeyboardButton(label, callback_data=f"stats:1:{c.id}"))
    kb.add(*filter_buttons)

    # Navigatsiya tugmalari
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀", callback_data=f"stats:{page-1}:{course_filter}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="stats_noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶", callback_data=f"stats:{page+1}:{course_filter}"))
    kb.add(*nav)

    kb.add(InlineKeyboardButton("🔙 Menyuga qaytish", callback_data="admin_back"))

    return text, kb


@dp.callback_query_handler(lambda c: c.data.startswith("stats:") or c.data == "stats_noop")
async def stats_handler(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    if callback.data == "stats_noop":
        await callback.answer()
        return

    _, page_str, course_filter = callback.data.split(":", 2)
    text, kb = await _build_stats_message(int(page_str), course_filter)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")

    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_back")
async def admin_back_handler(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    await callback.message.delete()
    await admin_panel(callback.message)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_menu_reports")
async def reports_submenu_back(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    await reports_submenu(callback)


# --- HISOBOTLAR SUBMENYUSI ---

async def reports_submenu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📄 Attestat PDF (50-savollik)", callback_data="reports_attestat"),
        InlineKeyboardButton("👥 Guruh natijalari PDF", callback_data="reports_group_test"),
        InlineKeyboardButton("🏆 Reyting PDF — Umumiy", callback_data="reports_coin_all"),
        InlineKeyboardButton("🏆 Reyting PDF — Guruh bo'yicha", callback_data="reports_coin_group"),
        InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"),
    )
    await callback.message.edit_text(
        "📁 <b>Hisobotlar</b>\n\nTur tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("reports_"))
async def reports_dispatch(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    action = callback.data
    if action == "reports_attestat":
        await pdf_select_course(callback)
    elif action == "reports_group_test":
        await grp_test_select_course(callback)
    elif action == "reports_coin_all":
        await coin_pdf_select_course(callback)
    elif action == "reports_coin_group":
        await coin_grp_select_course(callback)


# ── GURUH NATIJALARI PDF ─────────────────────────────────────────────────────

async def grp_test_select_course(callback: types.CallbackQuery):
    from base_app.models import Course
    courses = await sync_to_async(list)(Course.objects.all().order_by('-is_active', 'name'))
    if not courses:
        await callback.answer("❌ Kurslar yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for crs in courses:
        label = crs.name if crs.is_active else f"🔒 {crs.name}"
        kb.add(InlineKeyboardButton(label, callback_data=f"grp_test_course_{crs.id}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_reports"))
    await callback.message.edit_text(
        "👥 <b>Guruh natijalari PDF</b>\n\nKursni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("grp_test_course_"))
async def grp_test_select_group(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    course_id = int(callback.data.split("_")[3])
    from base_app.models import Group
    groups = await sync_to_async(list)(
        Group.objects.filter(course_id=course_id).prefetch_related('enrolled_students').order_by('name')
    )
    if not groups:
        await callback.answer("❌ Bu kursda guruhlar yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📋 Barcha guruhlar", callback_data=f"grp_test_grp_{course_id}_0"))
    for g in groups:
        count = await sync_to_async(g.enrolled_students.count)()
        kb.add(InlineKeyboardButton(f"{g.name} ({count} ta)", callback_data=f"grp_test_grp_{course_id}_{g.id}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="reports_group_test"))
    await callback.message.edit_text(
        "👥 <b>Guruh natijalari PDF</b>\n\nGuruhni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("grp_test_grp_"))
async def grp_test_init_topic_select(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    # format: grp_test_grp_{course_id}_{group_id}  (group_id=0 → barcha)
    parts = callback.data.split("_")
    course_id = int(parts[3])
    group_id = int(parts[4])

    from base_app.models import Topic, Group
    topics = await sync_to_async(list)(
        Topic.objects.filter(course_id=course_id, correct_answers__isnull=False).order_by('-id')
    )
    topics = [t for t in topics if t.correct_answers]
    if not topics:
        await callback.answer("❌ Bu kursda mavzular yo'q.", show_alert=True)
        return

    group_name = None
    if group_id != 0:
        group = await sync_to_async(Group.objects.get)(id=group_id)
        group_name = group.name

    all_topic_ids = [t.id for t in topics]
    await state.update_data(
        course_id=course_id,
        group_id=group_id,
        group_name=group_name,
        all_topic_ids=all_topic_ids,
        selected_topic_ids=[],
    )
    await GrpTestState.selecting_topics.set()

    scope = group_name or "Barcha guruhlar"
    kb = _build_grp_topic_kb(topics, selected_ids=[], course_id=course_id)
    await callback.message.edit_text(
        f"👥 <b>Guruh natijalari PDF</b>\n"
        f"🏫 Guruh: <b>{scope}</b>\n\n"
        f"Mavzularni tanlang (bir yoki bir nechta):\n"
        f"☐ — tanlanmagan  ✅ — tanlangan",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


def _build_grp_topic_kb(topics, selected_ids: list, course_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for t in topics:
        code = next(iter(t.correct_answers), "—") if t.correct_answers else "—"
        check = "✅" if t.id in selected_ids else "☐"
        kb.add(InlineKeyboardButton(
            f"{check} {t.title[:28]}  [{code}]",
            callback_data=f"grptog_{t.id}"
        ))
    all_sel = len(selected_ids) == len(topics) and len(topics) > 0
    kb.add(InlineKeyboardButton(
        "❌ Barchasini bekor qilish" if all_sel else "✅ Barchasini tanlash",
        callback_data="grp_selall"
    ))
    n = len(selected_ids)
    kb.add(InlineKeyboardButton(
        f"📄 PDF yaratish ({n} ta mavzu)" if n else "📄 PDF yaratish (mavzu tanlanmagan)",
        callback_data="grp_generate"
    ))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data=f"grp_test_course_{course_id}"))
    return kb


async def _grp_refresh_topic_msg(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    all_ids = data.get('all_topic_ids', [])
    selected = data.get('selected_topic_ids', [])
    course_id = data.get('course_id')
    group_name = data.get('group_name')

    from base_app.models import Topic
    topics = await sync_to_async(list)(
        Topic.objects.filter(id__in=all_ids).order_by('-id')
    )
    topics = sorted(topics, key=lambda t: all_ids.index(t.id))

    kb = _build_grp_topic_kb(topics, selected, course_id)
    n = len(selected)
    scope = group_name or "Barcha guruhlar"
    await callback.message.edit_text(
        f"👥 <b>Guruh natijalari PDF</b>\n"
        f"🏫 Guruh: <b>{scope}</b>\n\n"
        f"Mavzularni tanlang (bir yoki bir nechta):\n"
        f"☐ — tanlanmagan  ✅ — tanlangan\n\n"
        f"{'📌 Tanlandi: <b>' + str(n) + '</b> ta mavzu' if n else '📭 Hech qanday mavzu tanlanmagan'}",
        reply_markup=kb, parse_mode="HTML"
    )


@dp.callback_query_handler(lambda c: c.data.startswith("grptog_"), state=GrpTestState.selecting_topics)
async def grp_topic_toggle(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    topic_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    selected = data.get('selected_topic_ids', [])
    if topic_id in selected:
        selected.remove(topic_id)
        await callback.answer("❌ Bekor qilindi")
    else:
        selected.append(topic_id)
        await callback.answer("✅ Tanlandi")
    await state.update_data(selected_topic_ids=selected)
    await _grp_refresh_topic_msg(callback, state)


@dp.callback_query_handler(lambda c: c.data == "grp_selall", state=GrpTestState.selecting_topics)
async def grp_select_all(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    data = await state.get_data()
    all_ids = data.get('all_topic_ids', [])
    selected = data.get('selected_topic_ids', [])
    if set(selected) == set(all_ids):
        selected = []
        await callback.answer("❌ Barchasi bekor qilindi")
    else:
        selected = all_ids.copy()
        await callback.answer(f"✅ {len(selected)} ta mavzu tanlandi")
    await state.update_data(selected_topic_ids=selected)
    await _grp_refresh_topic_msg(callback, state)


@dp.callback_query_handler(lambda c: c.data == "grp_generate", state=GrpTestState.selecting_topics)
async def grp_go_to_month(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    data = await state.get_data()
    selected = data.get('selected_topic_ids', [])
    if not selected:
        await callback.answer("⚠️ Kamida 1 ta mavzu tanlang!", show_alert=True)
        return

    group_id = data.get('group_id', 0)
    group_name = data.get('group_name')

    student_ids = None
    if group_id != 0:
        from base_app.models import Group
        grp = await sync_to_async(Group.objects.prefetch_related('enrolled_students').get)(id=group_id)
        student_ids = await sync_to_async(
            lambda: list(grp.enrolled_students.values_list('id', flat=True))
        )()

    months = await _get_task_months(selected, student_ids)
    if not months:
        # Ma'lumot bor, lekin oy yo'q — to'g'ridan generate
        import asyncio
        await state.finish()
        status_msg = await callback.message.edit_text("⏳ PDF tayyorlanmoqda...")
        await callback.answer()
        asyncio.create_task(_generate_and_send_group_matrix_pdf(
            callback.from_user.id, callback.message.chat.id, status_msg.message_id,
            selected, group_id, group_name, 0, 0
        ))
        return

    await GrpTestState.selecting_month.set()
    scope = group_name or "Barcha guruhlar"
    kb = _build_month_kb(months, "grpmo", "grp_generate_back")
    await callback.message.edit_text(
        f"👥 <b>Guruh natijalari PDF</b>\n🏫 {scope}\n\nOyni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "grp_generate_back", state=GrpTestState.selecting_month)
async def grp_month_back(callback: types.CallbackQuery, state: FSMContext):
    await GrpTestState.selecting_topics.set()
    await _grp_refresh_topic_msg(callback, state)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("grpmo_"), state=GrpTestState.selecting_month)
async def grp_month_selected(callback: types.CallbackQuery, state: FSMContext):
    import asyncio
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer()
        return
    # format: grpmo_{year}_{month}
    parts = callback.data.split("_")
    year, month = int(parts[1]), int(parts[2])
    data = await state.get_data()
    selected = data.get('selected_topic_ids', [])
    group_id = data.get('group_id', 0)
    group_name = data.get('group_name')
    await state.finish()
    status_msg = await callback.message.edit_text("⏳ PDF tayyorlanmoqda...")
    await callback.answer()
    asyncio.create_task(_generate_and_send_group_matrix_pdf(
        callback.from_user.id, callback.message.chat.id, status_msg.message_id,
        selected, group_id, group_name, year, month
    ))


async def _generate_and_send_group_matrix_pdf(
    user_id: int, chat_id: int, status_msg_id: int,
    topic_ids: list, group_id: int, group_name: str,
    year: int = 0, month: int = 0
):
    from base_app.models import Topic, Task, Group
    from utils.pdf_report import generate_group_matrix_pdf
    from aiogram.types import InputFile
    try:
        topics = await sync_to_async(list)(
            Topic.objects.select_related('course').filter(id__in=topic_ids)
        )
        topics = sorted(topics, key=lambda t: topic_ids.index(t.id))

        def _task_qs(base_qs):
            if year and month:
                base_qs = base_qs.filter(submitted_at__year=year, submitted_at__month=month)
            return base_qs.exclude(test_answers__isnull=True).exclude(test_answers='')

        if group_id == 0:
            tasks = await sync_to_async(list)(
                _task_qs(Task.objects.filter(topic_id__in=topic_ids, task_type='test'))
                    .select_related('student')
            )
            student_map = {t.student_id: t.student for t in tasks}
            students = sorted(student_map.values(), key=lambda s: s.full_name)
        else:
            group = await sync_to_async(
                Group.objects.prefetch_related('enrolled_students').get
            )(id=group_id)
            students = await sync_to_async(list)(
                group.enrolled_students.all().order_by('full_name')
            )
            student_ids = [s.id for s in students]
            tasks = await sync_to_async(list)(
                _task_qs(Task.objects.filter(
                    topic_id__in=topic_ids, task_type='test', student_id__in=student_ids
                )).select_related('student')
            )

        if not tasks:
            no_data = "❌ Bu oyda test topshiruvchilar yo'q." if (year and month) else "❌ Bu bo'yicha hali test topshiruvchilar yo'q."
            await bot.edit_message_text(no_data, chat_id=chat_id, message_id=status_msg_id)
            return

        tasks_map = {}
        for task in tasks:
            tasks_map.setdefault(task.topic_id, {})[task.student_id] = task

        month_label = f"{MONTH_NAMES_UZ[month]} {year}" if (year and month) else None
        scope = group_name or "Barcha guruhlar"
        codes = [next(iter(t.correct_answers), t.title[:8]) for t in topics[:4]]
        caption_topics = ", ".join(codes) + (f" +{len(topics)-4}" if len(topics) > 4 else "")
        month_line = f"📅 {month_label}\n" if month_label else ""
        base_caption = (
            f"👥 <b>Guruh natijalari</b>\n"
            f"🏫 Guruh: {scope}\n"
            f"{month_line}"
            f"📚 Mavzular: {caption_topics}\n"
            f"👥 {len(students)} ta student"
        )

        # Web havola (har doim yuboriladi)
        from base_app.report_views import generate_matrix_token
        token = await sync_to_async(generate_matrix_token)(
            group_id, topic_ids, year, month, group_name
        )
        web_url = f"http://vazifa.matematikapro.uz/report/matrix/{token}/"
        web_caption = base_caption + f"\n\n🌐 <a href=\"{web_url}\">Brauzerda ko'rish</a> (7 kun)"

        # 10 ta va undan kam mavzu → PDF ham yuboriladi
        if len(topics) <= 10:
            pdf_buffer = await sync_to_async(generate_group_matrix_pdf)(
                group_name=group_name,
                topics=topics,
                tasks_map=tasks_map,
                students=students,
                month_label=month_label,
            )
            await bot.send_document(
                user_id,
                InputFile(pdf_buffer, filename=f"natijalar_{scope[:20]}.pdf"),
                caption=web_caption,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(
                user_id,
                web_caption,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
    except Exception as e:
        try:
            await bot.edit_message_text(
                f"❌ Xatolik: {str(e)[:200]}",
                chat_id=chat_id, message_id=status_msg_id
            )
        except Exception:
            pass


# ── TANGA REYTINGI GURUH BO'YICHA ───────────────────────────────────────────

async def coin_grp_select_course(callback: types.CallbackQuery):
    from base_app.models import Course
    courses = await sync_to_async(list)(Course.objects.all().order_by('-is_active', 'name'))
    if not courses:
        await callback.answer("❌ Kurslar yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    for crs in courses:
        label = crs.name if crs.is_active else f"🔒 {crs.name}"
        kb.add(InlineKeyboardButton(label, callback_data=f"coin_grp_course_{crs.id}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_reports"))
    await callback.message.edit_text(
        "🏆 <b>Reyting PDF — Guruh bo'yicha</b>\n\nKursni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("coin_grp_course_"))
async def coin_grp_select_group(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    course_id = int(callback.data.split("_")[3])
    from base_app.models import Group
    groups = await sync_to_async(list)(
        Group.objects.filter(course_id=course_id).prefetch_related('enrolled_students').order_by('name')
    )
    if not groups:
        await callback.answer("❌ Bu kursda guruhlar yo'q.", show_alert=True)
        return
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("📋 Barcha guruhlar (umumiy)", callback_data=f"coin_grp_gen_{course_id}_0"))
    for g in groups:
        count = await sync_to_async(g.enrolled_students.count)()
        kb.add(InlineKeyboardButton(f"{g.name} ({count} ta)", callback_data=f"coin_grp_gen_{course_id}_{g.id}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="reports_coin_group"))
    await callback.message.edit_text(
        "🏆 <b>Reyting PDF</b>\n\nGuruhni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("coin_grp_gen_"))
async def coin_grp_select_month(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    # format: coin_grp_gen_{course_id}_{group_id}
    parts = callback.data.split("_")
    course_id, group_id = int(parts[3]), int(parts[4])

    student_ids = None
    group_name = None
    if group_id != 0:
        from base_app.models import Group
        grp = await sync_to_async(Group.objects.prefetch_related('enrolled_students').get)(id=group_id)
        student_ids = await sync_to_async(
            lambda: list(grp.enrolled_students.values_list('id', flat=True))
        )()
        group_name = grp.name

    months = await _get_coin_months(course_id, student_ids)
    if not months:
        status_msg = await callback.message.edit_text("⏳ Reyting PDF tayyorlanmoqda...")
        await callback.answer()
        import asyncio
        asyncio.create_task(_generate_and_send_coin_grp_pdf(
            callback.from_user.id, callback.message.chat.id, status_msg.message_id,
            course_id, group_id, 0, 0
        ))
        return

    scope = group_name or "Barcha guruhlar"
    kb = _build_month_kb(months, f"cgrp_mo_{course_id}_{group_id}", f"coin_grp_course_{course_id}")
    await callback.message.edit_text(
        f"🏆 <b>Reyting PDF</b>\n🏫 {scope}\n\nOyni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("cgrp_mo_"))
async def coin_grp_month_selected(callback: types.CallbackQuery):
    import asyncio
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    # format: cgrp_mo_{course_id}_{group_id}_{year}_{month}
    parts = callback.data.split("_")
    course_id, group_id, year, month = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
    status_msg = await callback.message.edit_text("⏳ Reyting PDF tayyorlanmoqda...")
    await callback.answer()
    asyncio.create_task(_generate_and_send_coin_grp_pdf(
        callback.from_user.id, callback.message.chat.id, status_msg.message_id,
        course_id, group_id, year, month
    ))


async def _generate_and_send_coin_grp_pdf(
    user_id: int, chat_id: int, status_msg_id: int,
    course_id: int, group_id: int, year: int = 0, month: int = 0
):
    from base_app.models import Course, CoinWallet, CoinTransaction, Group
    from utils.pdf_report import generate_coin_rating_pdf, generate_coin_monthly_pdf
    from django.db.models import Sum
    from aiogram.types import InputFile
    try:
        course = await sync_to_async(Course.objects.get)(id=course_id)

        # Guruh student IDlari
        student_ids = None
        group_name = None
        if group_id != 0:
            group = await sync_to_async(Group.objects.prefetch_related('enrolled_students').get)(id=group_id)
            student_ids = await sync_to_async(
                lambda: list(group.enrolled_students.values_list('id', flat=True))
            )()
            group_name = group.name

        scope = group_name or "Umumiy"

        if year and month:
            from base_app.coins import get_monthly_rating_rows
            rows = await sync_to_async(get_monthly_rating_rows)(course_id, year, month, student_ids)
            if not rows:
                await bot.edit_message_text(
                    "❌ Bu bo'yicha hali tanga reyting yo'q.",
                    chat_id=chat_id, message_id=status_msg_id
                )
                return
            month_label = f"{MONTH_NAMES_UZ[month]} {year}"
            pdf_buffer = await sync_to_async(generate_coin_monthly_pdf)(course, rows, group_name, month_label)
            safe_name = course.name.replace('/', '-')[:30]
            safe_scope = scope.replace('/', '-')[:15]
            await bot.send_document(
                user_id,
                InputFile(pdf_buffer, filename=f"reyting_{safe_name}_{safe_scope}_{year}_{month}.pdf"),
                caption=(
                    f"🏆 <b>{course.name}</b>\n"
                    f"🏫 Guruh: {scope}\n"
                    f"📅 {month_label}\n"
                    f"👥 {len(rows)} ta student"
                ),
                parse_mode="HTML"
            )
            await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            return

        # Barcha vaqt — CoinWallet (streak bilan)
        qs_w = CoinWallet.objects.filter(course_id=course_id).select_related('student')
        if student_ids:
            qs_w = qs_w.filter(student_id__in=student_ids)
        wallets = await sync_to_async(list)(qs_w.order_by('-total_coins', '-longest_streak'))

        if not wallets:
            await bot.edit_message_text(
                "❌ Bu bo'yicha hali tanga reyting yo'q.",
                chat_id=chat_id, message_id=status_msg_id
            )
            return

        pdf_buffer = await sync_to_async(generate_coin_rating_pdf)(course, wallets, group_name)
        safe_name = course.name.replace('/', '-')[:35]
        safe_scope = scope.replace('/', '-')[:20]
        await bot.send_document(
            user_id,
            InputFile(pdf_buffer, filename=f"reyting_{safe_name}_{safe_scope}.pdf"),
            caption=(
                f"🏆 <b>{course.name}</b>\n"
                f"🏫 Guruh: {scope}\n"
                f"👥 {len(wallets)} ta student"
            ),
            parse_mode="HTML"
        )
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
    except Exception as e:
        try:
            await bot.edit_message_text(
                f"❌ Xatolik: {str(e)[:200]}",
                chat_id=chat_id, message_id=status_msg_id
            )
        except Exception:
            pass


# --- PDF HISOBOT ---
@dp.callback_query_handler(lambda c: c.data == "admin_menu_pdf")
async def pdf_select_course(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    from base_app.models import Course
    courses = await sync_to_async(list)(Course.objects.all().order_by('-is_active', 'name'))

    if not courses:
        await callback.answer("❌ Kurslar yo'q.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for c in courses:
        label = c.name if c.is_active else f"🔒 {c.name}"
        kb.add(InlineKeyboardButton(label, callback_data=f"pdf_course_{c.id}_1"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"))

    await callback.message.edit_text("📄 <b>PDF hisobot</b>\n\nKursni tanlang:", reply_markup=kb, parse_mode="HTML")
    await callback.answer()


PDF_TOPICS_PAGE_SIZE = 8

@dp.callback_query_handler(lambda c: c.data.startswith("pdf_course_"))
async def pdf_select_topic(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    # format: pdf_course_{course_id}_{page}
    parts = callback.data.split("_")
    course_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 1

    from base_app.models import Topic
    from utils.pdf_report import _parse_answers

    all_topics = await sync_to_async(list)(
        Topic.objects.filter(course_id=course_id, correct_answers__isnull=False).order_by('-id')
    )

    fifty_topics = []
    for t in all_topics:
        if not t.correct_answers:
            continue
        code = next(iter(t.correct_answers), None)
        if not code:
            continue
        if len(_parse_answers(t.correct_answers[code])) == 50:
            fifty_topics.append(t)

    if not fifty_topics:
        await callback.answer("❌ Bu kursda 50 savollik topiclar yo'q.", show_alert=True)
        return

    total = len(fifty_topics)
    total_pages = max(1, (total + PDF_TOPICS_PAGE_SIZE - 1) // PDF_TOPICS_PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start = (page - 1) * PDF_TOPICS_PAGE_SIZE
    page_items = fifty_topics[start:start + PDF_TOPICS_PAGE_SIZE]

    kb = InlineKeyboardMarkup(row_width=1)
    for t in page_items:
        code = next(iter(t.correct_answers), "—")
        kb.add(InlineKeyboardButton(f"{t.title}  [{code}]", callback_data=f"pdf_topic_{t.id}"))

    # Navigatsiya
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀", callback_data=f"pdf_course_{course_id}_{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="stats_noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("▶", callback_data=f"pdf_course_{course_id}_{page + 1}"))
    if len(nav) > 1:
        kb.add(*nav)

    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_pdf"))

    await callback.message.edit_text(
        f"📄 <b>PDF hisobot</b>\n\nMavzuni tanlang ({page}/{total_pages}, jami {total} ta):",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


async def _generate_and_send_pdf(user_id: int, chat_id: int, status_msg_id: int, topic_id: int):
    """Background task: PDF generatsiya qiladi va yuboradi."""
    from base_app.models import Topic, Task
    from utils.pdf_report import generate_topic_pdf
    from aiogram.types import InputFile

    try:
        topic = await sync_to_async(
            Topic.objects.select_related('course').get
        )(id=topic_id)

        tasks = await sync_to_async(list)(
            Task.objects.filter(topic_id=topic_id, task_type='test')
                .select_related('student')
                .exclude(test_answers__isnull=True)
                .exclude(test_answers='')
        )

        if not tasks:
            await bot.edit_message_text(
                "❌ Bu mavzu bo'yicha test topshiruvchilar yo'q.",
                chat_id=chat_id, message_id=status_msg_id
            )
            return

        pdf_buffer = await sync_to_async(generate_topic_pdf)(topic, tasks)

        safe_title = topic.title.replace('/', '-').replace('\\', '-')[:40]
        await bot.send_document(
            user_id,
            InputFile(pdf_buffer, filename=f"{safe_title}.pdf"),
            caption=f"📄 <b>{topic.title}</b>\n👥 {len(tasks)} ta student",
            parse_mode="HTML"
        )
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)

    except Exception as e:
        try:
            await bot.edit_message_text(
                f"❌ Xatolik: {str(e)[:200]}",
                chat_id=chat_id, message_id=status_msg_id
            )
        except Exception:
            pass


@dp.callback_query_handler(lambda c: c.data.startswith("pdf_topic_"))
async def pdf_generate(callback: types.CallbackQuery):
    import asyncio

    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    topic_id = int(callback.data.split("_")[2])

    status_msg = await callback.message.edit_text("⏳ PDF tayyorlanmoqda, biroz kuting...")
    await callback.answer()

    asyncio.create_task(
        _generate_and_send_pdf(
            user_id=callback.from_user.id,
            chat_id=callback.message.chat.id,
            status_msg_id=status_msg.message_id,
            topic_id=topic_id,
        )
    )


# --- TANGA REYTING PDF ---
@dp.callback_query_handler(lambda c: c.data == "admin_menu_coin_pdf")
async def coin_pdf_select_course(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    from base_app.models import Course
    courses = await sync_to_async(list)(Course.objects.all().order_by('-is_active', 'name'))

    if not courses:
        await callback.answer("❌ Kurslar yo'q.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for course in courses:
        label = course.name if course.is_active else f"🔒 {course.name}"
        kb.add(InlineKeyboardButton(label, callback_data=f"coin_pdf_course_{course.id}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"))

    await callback.message.edit_text(
        "🏆 <b>Tanga reyting PDF</b>\n\nKursni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("coin_pdf_course_"))
async def coin_pdf_select_month(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    course_id = int(callback.data.split("_")[3])
    months = await _get_coin_months(course_id)
    if not months:
        status_msg = await callback.message.edit_text("⏳ Reyting PDF tayyorlanmoqda...")
        await callback.answer()
        import asyncio
        asyncio.create_task(_generate_and_send_coin_pdf(
            callback.from_user.id, callback.message.chat.id, status_msg.message_id, course_id, 0, 0
        ))
        return
    kb = _build_month_kb(months, f"coin_mo_{course_id}", "reports_coin_all")
    await callback.message.edit_text(
        "🏆 <b>Reyting PDF — Umumiy</b>\n\nOyni tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("coin_mo_"))
async def coin_pdf_month_selected(callback: types.CallbackQuery):
    import asyncio
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    # format: coin_mo_{course_id}_{year}_{month}
    parts = callback.data.split("_")
    course_id, year, month = int(parts[2]), int(parts[3]), int(parts[4])
    status_msg = await callback.message.edit_text("⏳ Reyting PDF tayyorlanmoqda...")
    await callback.answer()
    asyncio.create_task(_generate_and_send_coin_pdf(
        callback.from_user.id, callback.message.chat.id, status_msg.message_id, course_id, year, month
    ))


async def _generate_and_send_coin_pdf(
    user_id: int, chat_id: int, status_msg_id: int,
    course_id: int, year: int = 0, month: int = 0
):
    from base_app.models import Course, CoinWallet, CoinTransaction
    from utils.pdf_report import generate_coin_rating_pdf, generate_coin_monthly_pdf
    from django.db.models import Sum
    from aiogram.types import InputFile

    try:
        course = await sync_to_async(Course.objects.get)(id=course_id)

        if year and month:
            from base_app.coins import get_monthly_rating_rows
            rows = await sync_to_async(get_monthly_rating_rows)(course_id, year, month, None)
            if not rows:
                await bot.edit_message_text(
                    "❌ Bu kursda hali tanga reyting yo'q.",
                    chat_id=chat_id, message_id=status_msg_id
                )
                return
            month_label = f"{MONTH_NAMES_UZ[month]} {year}"
            pdf_buffer = await sync_to_async(generate_coin_monthly_pdf)(course, rows, None, month_label)
            safe_name = course.name.replace('/', '-')[:30]
            await bot.send_document(
                user_id,
                InputFile(pdf_buffer, filename=f"reyting_{safe_name}_{year}_{month}.pdf"),
                caption=f"🏆 <b>{course.name}</b>\n📅 {month_label}\n👥 {len(rows)} ta student",
                parse_mode="HTML"
            )
            await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)
            return

        wallets = await sync_to_async(list)(
            CoinWallet.objects.filter(course_id=course_id)
            .select_related('student')
            .order_by('-total_coins', '-longest_streak')[:600]
        )

        if not wallets:
            await bot.edit_message_text(
                "❌ Bu kursda hali tanga reyting yo'q.",
                chat_id=chat_id, message_id=status_msg_id
            )
            return

        pdf_buffer = await sync_to_async(generate_coin_rating_pdf)(course, wallets)

        safe_name = course.name.replace('/', '-').replace('\\', '-')[:40]
        await bot.send_document(
            user_id,
            InputFile(pdf_buffer, filename=f"reyting_{safe_name}.pdf"),
            caption=f"🏆 <b>{course.name}</b> — Tanga reytingi\n👥 {len(wallets)} ta student",
            parse_mode="HTML"
        )
        await bot.delete_message(chat_id=chat_id, message_id=status_msg_id)

    except Exception as e:
        try:
            await bot.edit_message_text(
                f"❌ Xatolik: {str(e)[:200]}",
                chat_id=chat_id, message_id=status_msg_id
            )
        except Exception:
            pass


def _recalculate_coins_for_tasks(tasks_to_update):
    """
    Grade o'zgargan tasklar uchun CoinTransaction va CoinWallet ni yangilaydi.
    Faqat result_coins (= grade) o'zgaradi; streak_coins o'zgarmaydi.
    CoinTransaction bo'lmasa — retroaktiv yaratiladi (result_coins, streak_coins=0).
    """
    import logging
    from django.db import transaction as db_transaction
    from base_app.models import CoinTransaction, CoinWallet

    logger = logging.getLogger(__name__)

    with db_transaction.atomic():
        for task in tasks_to_update:
            new_result_coins = max(0, task.grade)
            course = task.topic.course
            if not course:
                continue

            try:
                txn = CoinTransaction.objects.select_for_update().get(
                    wallet__student=task.student,
                    topic=task.topic,
                    task_type='test',
                )
            except CoinTransaction.DoesNotExist:
                # Avval tanga tizimi bo'lmagan — retroaktiv yaratamiz
                try:
                    wallet, _ = CoinWallet.objects.select_for_update().get_or_create(
                        student=task.student, course=course
                    )
                    CoinTransaction.objects.create(
                        wallet=wallet,
                        topic=task.topic,
                        task_type='test',
                        result_coins=new_result_coins,
                        streak_coins=0,
                        total_coins=new_result_coins,
                        streak_after=wallet.current_streak,
                        deadline_penalty=False,
                    )
                    CoinWallet.objects.filter(pk=wallet.pk).update(
                        total_coins=models_F('total_coins') + new_result_coins
                    )
                except Exception as e:
                    logger.error(f"Retroaktiv CoinTransaction yaratishda xato: {e}")
                continue

            old_result_coins = txn.result_coins
            coin_diff = new_result_coins - old_result_coins
            if coin_diff == 0:
                continue

            txn.result_coins = new_result_coins
            txn.total_coins = new_result_coins + txn.streak_coins
            txn.save(update_fields=['result_coins', 'total_coins'])

            # total_coins manfiy bo'lib ketmasligi uchun
            wallet = CoinWallet.objects.select_for_update().get(pk=txn.wallet_id)
            new_total = max(0, wallet.total_coins + coin_diff)
            wallet.total_coins = new_total
            wallet.save(update_fields=['total_coins'])


# --- TEST JAVOBLARINI O'ZGARTIRISH ---
@dp.message_handler(IsPrivate(), lambda msg: msg.text == "🔧 Test javoblarini o'zgartirish", user_id=ADMINS)
async def update_test_answers_start(message: types.Message):
    """Admin test javoblarini o'zgartirish jarayonini boshlaydi"""
    from base_app.models import Topic
    
    # Faqat test mavzularini olamiz (correct_answers mavjud bo'lganlar)
    topics = await sync_to_async(list)(
        Topic.objects.filter(correct_answers__isnull=False, is_active=True).order_by('-id')
    )
    
    if not topics:
        await message.answer("❌ Hozircha test mavzulari mavjud emas.")
        return
    
    # Topic ro'yxatini inline keyboard bilan ko'rsatamiz
    keyboard = InlineKeyboardMarkup(row_width=1)
    for topic in topics:
        # Test code va mavzu nomini ko'rsatamiz
        correct_code = list(topic.correct_answers.keys())[0] if topic.correct_answers else "?"
        keyboard.add(
            InlineKeyboardButton(
                text=f"{topic.title} (Kod: {correct_code})",
                callback_data=f"update_topic_{topic.id}"
            )
        )
    
    await message.answer(
        "🔧 Test javoblarini o'zgartirish\n\n"
        "Qaysi mavzu uchun to'g'ri javoblarni o'zgartirmoqchisiz?",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data.startswith("update_topic_"), state="*")
async def topic_selected_for_update(callback: types.CallbackQuery, state: FSMContext):
    """Admin topic tanladi, endi yangi javoblarni so'raymiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    
    topic_id = int(callback.data.split("_")[2])
    
    from base_app.models import Topic
    topic = await sync_to_async(Topic.objects.get)(id=topic_id)
    
    # Hozirgi javoblarni ko'rsatamiz
    current_code = list(topic.correct_answers.keys())[0]
    current_answers = topic.correct_answers[current_code]
    
    # Javoblar sonini to'g'ri hisoblash (uch formatni qo'llab-quvvatlash)
    import re
    if re.match(r'^[a-z]+$', current_answers):
        # Format 1: faqat harflar (abc = 3 ta)
        answer_count = len(current_answers)
    else:
        # Format 2: raqam+harf(lar) (1a2b3c = 3 ta, 1ab2x3cd = 3 ta)
        answer_count = len(re.findall(r'\d+[a-zx]+', current_answers))
    
    await callback.message.edit_text(
        f"📝 Mavzu: {topic.title}\n"
        f"🔤 Hozirgi test kodi: {current_code}\n"
        f"✅ Hozirgi to'g'ri javoblar ({answer_count} ta): {current_answers}\n\n"
        f"Yangi to'g'ri javoblarni yuboring ({answer_count} ta javob):\n"
        f"• Faqat harflar: abc, abcd...\n"
        f"• Raqam+harf: 1a2b3c, 1a2c3d...\n\n"
        f"❌ Bekor qilish uchun /cancel"
    )
    
    # State ga topic_id va javoblar sonini saqlaymiz
    await state.update_data(
        topic_id=topic_id, 
        topic_title=topic.title, 
        test_code=current_code,
        answer_count=answer_count
    )
    await UpdateAnswersState.waiting_for_new_answers.set()
    
    await callback.answer()


@dp.message_handler(IsPrivate(), state=UpdateAnswersState.waiting_for_new_answers, user_id=ADMINS)
async def process_new_answers(message: types.Message, state: FSMContext):
    """Yangi javoblarni qabul qilib, validatsiya qilamiz va DB ga yozamiz"""
    new_answers = message.text.strip().lower()
    
    # State dan topic ma'lumotlarini olamiz
    data = await state.get_data()
    topic_id = data['topic_id']
    topic_title = data['topic_title']
    test_code = data['test_code']
    answer_count = data['answer_count']
    
    # Validatsiya: uchta formatni qo'llab-quvvatlaymiz
    # 1. Faqat harflar: "abc" 
    # 2. Raqam + harf(lar): "1a2b3c" yoki "1ab2x3cd" (bir nechta variant yoki x)
    # 3. x = hech biri to'g'ri emas
    
    # Formatni aniqlash
    import re
    
    # Format 1: faqat harflar (abc, abcd, ...)
    if re.match(r'^[a-z]+$', new_answers):
        if len(new_answers) != answer_count:
            await message.answer(
                f"❌ Xato! To'g'ri javoblar {answer_count} ta bo'lishi kerak.\n"
                f"Siz {len(new_answers)} ta harf yubordingiz.\n\n"
                f"Qaytadan yuboring yoki /cancel"
            )
            return
        # Format to'g'ri, davom etamiz
    
    # Format 2: raqam+harf(lar) yoki x (1a2b3c, 1ab2x3cd, ...)
    # x = hech biri to'g'ri emas
    # ko'p harflar = bir nechta to'g'ri javob
    elif re.match(r'^(\d+[a-zx]+)+$', new_answers):
        # Javoblar sonini sanab ko'ramiz
        questions = re.findall(r'\d+[a-zx]+', new_answers)
        if len(questions) != answer_count:
            await message.answer(
                f"❌ Xato! To'g'ri javoblar {answer_count} ta bo'lishi kerak.\n"
                f"Siz {len(questions)} ta javob yubordingiz.\n\n"
                f"Qaytadan yuboring yoki /cancel"
            )
            return
        # Format to'g'ri, davom etamiz
    
    else:
        await message.answer(
            "❌ Xato format! Uch xil formatdan foydalaning:\n\n"
            "1️⃣ Faqat harflar: abc, abcd, ...\n"
            "2️⃣ Raqam + harf: 1a2b3c, 1a2c3d, ...\n"
            "3️⃣ Ko'p variant: 1ab2x3abcd\n"
            "   • 1ab = 1-savol: a yoki b to'g'ri\n"
            "   • 2x = 2-savol: hech biri to'g'ri emas\n"
            "   • 3abcd = 3-savol: hammasi to'g'ri\n\n"
            "Barcha kichik lotin harflaridan foydalaning (a-z).\n"
            "Qaytadan yuboring yoki /cancel"
        )
        return
    
    from base_app.models import Topic, Task
    
    # Topic ni yangilaymiz
    topic = await sync_to_async(Topic.objects.get)(id=topic_id)
    old_answers = topic.correct_answers[test_code]
    
    # Faqat tanlangan test kodini yangilaymiz, boshqalarini saqlaymiz
    topic.correct_answers[test_code] = new_answers
    await sync_to_async(topic.save)()
    
    await message.answer(
        f"⏳ Javoblar yangilandi, testlar qayta hisoblanmoqda...\n\n"
        f"📝 Mavzu: {topic_title}\n"
        f"❌ Eski: {old_answers}\n"
        f"✅ Yangi: {new_answers}"
    )
    
    # Yangi javoblarni parse qilish (uch formatni qo'llab-quvvatlash)
    import re
    
    # Raqam bor-yo'qligini tekshirish
    has_numbers = bool(re.search(r'\d', new_answers))
    
    if has_numbers:
        # Format 2: raqam+harf(lar) (1a2b3c yoki 1ab2x3cd)
        # Har bir savolning to'g'ri javoblarini list qilib olamiz
        correct_answers_list = []
        for match in re.finditer(r'\d+([a-zx]+)', new_answers):
            answers = match.group(1)
            if answers == 'x':
                # 'x' = hech biri to'g'ri emas
                correct_answers_list.append(['x'])
            else:
                # Ko'p variant (ab, abcd, ...)
                correct_answers_list.append(list(answers))
    elif re.match(r'^[a-zx]+$', new_answers):
        # Format 1: faqat harflar (abc) -> har biri bitta to'g'ri javob
        correct_answers_list = [[ch] for ch in new_answers]
    else:
        # Noma'lum format - barcha kichik harflarni olamiz
        filtered = ''.join(ch for ch in new_answers if ch.isalpha() or ch == 'x')
        correct_answers_list = [[ch] for ch in filtered]
    
    import asyncio

    # Barcha bu mavzu bo'yicha test topshirgan studentlarning natijasini qayta hisoblaymiz
    tasks = await sync_to_async(list)(
        Task.objects.filter(topic_id=topic_id, task_type='test', test_code=test_code).select_related('student')
    )

    topic_deadline = topic.deadline

    tasks_to_update = []
    notifications = []
    deadline_penalty_count = 0
    grade_changes = []

    for task in tasks:
        student_answers = task.test_answers.lower().strip()

        if '-' in student_answers:
            parts = student_answers.split('-', 1)
            if len(parts) == 2 and parts[0].replace('_', '').isdigit():
                student_answers = parts[1]

        has_numbers = bool(re.search(r'\d', student_answers))

        if has_numbers:
            student_answers_list = [m.group(1) for m in re.finditer(r'\d+([a-zx])', student_answers)]
        elif re.match(r'^[a-zx]+$', student_answers):
            student_answers_list = list(student_answers)
        else:
            student_answers_list = [ch for ch in student_answers if ch.isalpha() or ch == 'x']

        if not student_answers_list or len(student_answers_list) != answer_count:
            continue

        old_grade = task.grade
        correct_count = 0
        bekor_count = 0

        for i in range(answer_count):
            correct_ans_list = correct_answers_list[i]
            if correct_ans_list == ['x']:
                correct_count += 1
                bekor_count += 1
            elif student_answers_list[i] in correct_ans_list:
                correct_count += 1

        new_grade = correct_count

        is_late = False
        if topic_deadline and task.submitted_at and task.submitted_at > topic_deadline:
            is_late = True
            new_grade = int(new_grade * 0.8)
            deadline_penalty_count += 1

        if old_grade == new_grade:
            continue

        task.grade = new_grade
        tasks_to_update.append(task)

        diff = new_grade - old_grade
        grade_changes.append({
            'student': task.student.full_name,
            'old': old_grade,
            'new': new_grade,
            'diff': diff,
            'is_late': is_late,
        })

        change_symbol = "📈" if diff > 0 else "📉"
        bekor_msg = f"\n\n🎁 {bekor_count} ta savol bekor qilindi (test xatosi tuzatildi)" if bekor_count > 0 else ""
        deadline_msg = "\n\n⚠️ Siz testni deadline dan keyin topshirgansiz, shuning uchun 80% ball berildi" if is_late else ""

        notifications.append((
            task.student.telegram_id,
            f"{change_symbol} Test natijangiz o'zgardi!\n\n"
            f"📚 Mavzu: {topic_title}\n"
            f"❌ Eski baho: {old_grade}/{answer_count}\n"
            f"✅ Yangi baho: {new_grade}/{answer_count}\n"
            f"{'➕' if diff > 0 else '➖'} Farq: {abs(diff)} ball"
            f"{bekor_msg}{deadline_msg}"
        ))

    # 1 ta bulk UPDATE — N ta save() o'rniga
    if tasks_to_update:
        await sync_to_async(Task.objects.bulk_update)(tasks_to_update, ['grade'])

    # Tangalarni qayta hisoblash: grade o'zgargan har bir task uchun
    if tasks_to_update:
        await sync_to_async(_recalculate_coins_for_tasks)(tasks_to_update)

    # Parallel xabar yuborish (semaphore bilan Telegram rate limit himoya)
    if notifications:
        sem = asyncio.Semaphore(20)

        async def _send(tid, txt):
            async with sem:
                try:
                    await safe_send_message(tid, txt)
                except Exception:
                    pass

        await asyncio.gather(*[_send(tid, txt) for tid, txt in notifications])

    updated_count = len(tasks_to_update)

    stats_text = "✅ Yangilash tugadi!\n\n📊 Statistika:\n"
    stats_text += f"• Qayta hisoblangan testlar: {updated_count} ta\n"
    stats_text += f"• Jami baholangan testlar: {len(tasks)} ta\n"
    if deadline_penalty_count > 0:
        stats_text += f"• ⚠️ Deadline dan keyin (80% ball): {deadline_penalty_count} ta\n"
    stats_text += "\n"

    if grade_changes:
        stats_text += f"📋 Baho o'zgargan studentlar ({len(grade_changes)} ta):\n"
        for change in grade_changes[:10]:
            symbol = "📈" if change['diff'] > 0 else "📉"
            late_mark = " ⚠️" if change.get('is_late', False) else ""
            stats_text += f"{symbol} {change['student']}: {change['old']} → {change['new']} ({change['diff']:+d} ball){late_mark}\n"
        if len(grade_changes) > 10:
            stats_text += f"\n... va yana {len(grade_changes) - 10} ta student"

    await message.answer(stats_text)
    await state.finish()


# --- YANGI KURS YARATISH ---
def _generate_unique_course_code(name: str) -> str:
    """Kurs nomidan (masalan 'Ingliz tili') unikal kod (masalan 'ingliz_tili') yasaydi"""
    import re
    from base_app.models import Course

    base = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_") or "kurs"
    code = base
    i = 2
    while Course.objects.filter(code=code).exists():
        code = f"{base}_{i}"
        i += 1
    return code


async def _prompt_course_name(target):
    await target.answer(
        "➕ Yangi kurs yaratish\n\n"
        "📝 Kurs nomini yuboring (masalan: Matematika, Ingliz tili):\n\n"
        "❌ Bekor qilish uchun /cancel"
    )


@dp.message_handler(IsPrivate(), lambda msg: msg.text == "➕ Kurs qo'shish", user_id=ADMINS)
async def add_course_start(message: types.Message):
    """Admin yangi kurs yaratish jarayonini boshlaydi"""
    await _prompt_course_name(message)
    await AddCourseState.waiting_for_name.set()


@dp.callback_query_handler(lambda c: c.data == "goto_add_course", state="*")
async def goto_add_course(callback: types.CallbackQuery, state: FSMContext):
    """'Faol kurslar yo'q' xabaridagi tugma orqali kurs yaratishni boshlaydi"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    await callback.answer()
    await _prompt_course_name(callback.message)
    await AddCourseState.waiting_for_name.set()


@dp.message_handler(IsPrivate(), state=AddCourseState.waiting_for_name, user_id=ADMINS)
async def process_course_name(message: types.Message, state: FSMContext):
    """Kurs nomini qabul qilish va vazifa turini so'rash"""
    name = message.text.strip()

    if not name:
        await message.answer("❌ Kurs nomi bo'sh bo'lishi mumkin emas. Qaytadan yuboring yoki /cancel")
        return

    from base_app.models import Course

    if await sync_to_async(Course.objects.filter(name=name).exists)():
        await message.answer("❌ Bu nomli kurs allaqachon mavjud. Boshqa nom kiriting yoki /cancel")
        return

    code = await sync_to_async(_generate_unique_course_code)(name)
    await state.update_data(name=name, code=code)

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🧪 Test", callback_data="course_task_type_test"),
        InlineKeyboardButton("📋 Maxsus topshiriq", callback_data="course_task_type_assignment"),
    )
    await message.answer(
        f"✅ Kurs nomi: {name}\n\n"
        f"📚 Bu kursda qanday vazifa turi qabul qilinadi?",
        reply_markup=keyboard
    )
    await AddCourseState.waiting_for_task_type.set()


@dp.callback_query_handler(
    lambda c: c.data in ("course_task_type_test", "course_task_type_assignment"),
    state=AddCourseState.waiting_for_task_type,
)
async def process_course_task_type(callback: types.CallbackQuery, state: FSMContext):
    """Vazifa turini qabul qilib, kursni yaratadi"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    task_type = "test" if callback.data == "course_task_type_test" else "assignment"
    data = await state.get_data()

    from base_app.models import Course

    course = await sync_to_async(Course.objects.create)(
        name=data.get("name"), code=data.get("code"), task_type=task_type, is_active=True
    )

    await callback.message.edit_text(
        f"✅ Yangi kurs yaratildi!\n\n"
        f"📚 Nomi: {course.name}\n"
        f"🔑 Kodi: {course.code}\n"
        f"📝 Vazifa turi: {'Test' if task_type == 'test' else 'Maxsus topshiriq'}\n\n"
        f"Endi “➕ Mavzu qo'shish” tugmasi orqali shu kursga mavzu qo'sha olasiz."
    )
    await state.finish()
    await callback.answer()


# --- KURSLARNI BOSHQARISH (nomini o'zgartirish / faollashtirish / o'chirish) ---
async def _render_course_list(target):
    from base_app.models import Course

    courses = await sync_to_async(list)(Course.objects.all().order_by('name'))
    if not courses:
        await target.answer("❌ Hozircha kurslar mavjud emas.")
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for course in courses:
        label = course.name if course.is_active else f"🔴 {course.name} (nofaol)"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"course_manage_{course.id}"))

    await target.answer("📚 Kurslar ro'yxati\n\nBoshqarish uchun kursni tanlang:", reply_markup=keyboard)


@dp.message_handler(IsPrivate(), lambda msg: msg.text == "📚 Kurslarni boshqarish", user_id=ADMINS)
async def manage_courses_start(message: types.Message):
    await _render_course_list(message)


async def _render_course_detail(callback_message, course):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("✏️ Nomini o'zgartirish", callback_data=f"course_rename_{course.id}"),
        InlineKeyboardButton(
            "🔴 Nofaollashtirish" if course.is_active else "🟢 Faollashtirish",
            callback_data=f"course_toggle_{course.id}",
        ),
        InlineKeyboardButton("🗑 O'chirish", callback_data=f"course_delete_confirm_{course.id}"),
        InlineKeyboardButton("⬅️ Orqaga", callback_data="course_manage_back"),
    )
    await callback_message.edit_text(
        f"📚 <b>{course.name}</b>\n\n"
        f"🔑 Kodi: {course.code}\n"
        f"📝 Vazifa turi: {'Test' if course.task_type == 'test' else 'Maxsus topshiriq'}\n"
        f"Holati: {'🟢 Faol' if course.is_active else '🔴 Nofaol'}",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@dp.callback_query_handler(lambda c: c.data.startswith("course_manage_") and c.data != "course_manage_back", state="*")
async def course_manage_detail(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Course

    course_id = int(callback.data.split("_")[-1])
    try:
        course = await sync_to_async(Course.objects.get)(id=course_id)
    except Course.DoesNotExist:
        await callback.answer("❌ Kurs topilmadi.", show_alert=True)
        return

    await _render_course_detail(callback.message, course)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "course_manage_back", state="*")
async def course_manage_back(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    await callback.message.delete()
    await _render_course_list(callback.message)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("course_toggle_"), state="*")
async def course_toggle_active(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Course

    course_id = int(callback.data.split("_")[-1])
    course = await sync_to_async(Course.objects.get)(id=course_id)
    course.is_active = not course.is_active
    await sync_to_async(course.save)()

    await _render_course_detail(callback.message, course)
    await callback.answer("✅ Holat o'zgartirildi")


@dp.callback_query_handler(lambda c: c.data.startswith("course_rename_"), state="*")
async def course_rename_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    course_id = int(callback.data.split("_")[-1])
    await state.update_data(rename_course_id=course_id)
    await ManageCourseState.waiting_for_new_name.set()

    await callback.message.answer(
        "✏️ Kursning yangi nomini yuboring:\n\n❌ Bekor qilish uchun /cancel"
    )
    await callback.answer()


@dp.message_handler(IsPrivate(), state=ManageCourseState.waiting_for_new_name, user_id=ADMINS)
async def course_rename_finish(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Kurs nomi bo'sh bo'lishi mumkin emas. Qaytadan yuboring yoki /cancel")
        return

    from base_app.models import Course

    data = await state.get_data()
    course_id = data.get("rename_course_id")

    if await sync_to_async(Course.objects.filter(name=new_name).exclude(id=course_id).exists)():
        await message.answer("❌ Bu nomli kurs allaqachon mavjud. Boshqa nom kiriting yoki /cancel")
        return

    course = await sync_to_async(Course.objects.get)(id=course_id)
    old_name = course.name
    course.name = new_name
    await sync_to_async(course.save)()

    await state.finish()
    await message.answer(f"✅ Kurs nomi o'zgartirildi: {old_name} → {new_name}")


@dp.callback_query_handler(lambda c: c.data.startswith("course_delete_confirm_"), state="*")
async def course_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    course_id = int(callback.data.split("_")[-1])
    from base_app.models import Course

    course = await sync_to_async(Course.objects.get)(id=course_id)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"course_delete_yes_{course_id}"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"course_manage_{course_id}"),
    )
    await callback.message.edit_text(
        f"⚠️ Rostdan ham <b>{course.name}</b> kursini o'chirmoqchimisiz?\n\n"
        f"Bu amalni ortga qaytarib bo'lmaydi.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("course_delete_yes_"), state="*")
async def course_delete_execute(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from django.db.models import ProtectedError
    from base_app.models import Course, Group, Topic

    course_id = int(callback.data.split("_")[-1])
    course = await sync_to_async(Course.objects.get)(id=course_id)
    course_name = course.name

    try:
        await sync_to_async(course.delete)()
    except ProtectedError:
        groups_count = await sync_to_async(Group.objects.filter(course_id=course_id).count)()
        topics_count = await sync_to_async(Topic.objects.filter(course_id=course_id).count)()
        await callback.message.edit_text(
            f"❌ <b>{course_name}</b> kursini o'chirib bo'lmadi.\n\n"
            f"Unga {groups_count} ta guruh va {topics_count} ta mavzu bog'langan.\n"
            f"Avval ularni o'chiring/boshqa kursga o'tkazing, yoki kursni shunchaki "
            f"nofaollashtiring («🔴 Nofaollashtirish» tugmasi).",
            parse_mode="HTML",
        )
        await callback.answer()
        return

    await callback.message.edit_text(f"✅ <b>{course_name}</b> kursi o'chirildi.", parse_mode="HTML")
    await callback.answer()


# --- YANGI MAVZU QO'SHISH ---
@dp.message_handler(IsPrivate(), lambda msg: msg.text == "➕ Mavzu qo'shish", user_id=ADMINS)
async def add_topic_start(message: types.Message):
    """Admin yangi mavzu qo'shish jarayonini boshlaydi"""
    from base_app.models import Course
    
    # Barcha kurslarni olamiz
    courses = await sync_to_async(list)(Course.objects.filter(is_active=True).order_by('name'))

    if not courses:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("➕ Yangi kurs yaratish", callback_data="goto_add_course")
        )
        await message.answer(
            "❌ Hozircha faol kurslar mavjud emas.\n\n"
            "Avval kurs yarating:",
            reply_markup=keyboard
        )
        return
    
    # Kurs tanlash uchun inline keyboard
    keyboard = InlineKeyboardMarkup(row_width=1)
    for course in courses:
        keyboard.add(
            InlineKeyboardButton(
                text=f"{course.name}",
                callback_data=f"add_topic_course_{course.id}"
            )
        )
    
    await message.answer(
        "➕ Yangi mavzu qo'shish\n\n"
        "Birinchi navbatda, qaysi kurs uchun mavzu qo'shmoqchisiz?",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data.startswith("add_topic_course_"), state="*")
async def course_selected_for_topic(callback: types.CallbackQuery, state: FSMContext):
    """Admin kurs tanladi, endi mavzu nomini so'raymiz"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    
    course_id = int(callback.data.split("_")[3])
    
    from base_app.models import Course
    course = await sync_to_async(Course.objects.get)(id=course_id)
    
    await callback.message.edit_text(
        f"✅ Kurs tanlandi: {course.name}\n\n"
        f"📝 Endi mavzu nomini yuboring:\n\n"
        f"Masalan: 1-mavzu, 2-mavzu va h.k.\n\n"
        f"❌ Bekor qilish uchun /cancel"
    )
    
    # State ga course_id saqlaymiz
    await state.update_data(course_id=course_id, course_name=course.name)
    await AddTopicState.waiting_for_title.set()
    
    await callback.answer()


@dp.message_handler(IsPrivate(), state=AddTopicState.waiting_for_title, user_id=ADMINS)
async def process_topic_title(message: types.Message, state: FSMContext):
    """Mavzu nomini qabul qilish va deadline so'rash"""
    title = message.text.strip()
    
    if not title:
        await message.answer("❌ Mavzu nomi bo'sh bo'lishi mumkin emas. Qaytadan yuboring yoki /cancel")
        return
    
    # Title ni state ga saqlaymiz
    data = await state.get_data()
    await state.update_data(title=title)
    
    # Deadline tanlash uchun inline keyboard
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="📅 Deadline belgilash", callback_data="set_deadline"),
        InlineKeyboardButton(text="⏩ O'tkazib yuborish", callback_data="skip_deadline")
    )
    
    await message.answer(
        f"✅ Mavzu nomi: {title}\n\n"
        f"📅 Deadline belgilaysizmi?\n\n"
        f"Agar deadline belgilasangiz, deadline dan keyin topshirilgan testlar 80% ball oladi.",
        reply_markup=keyboard
    )


@dp.callback_query_handler(lambda c: c.data == "skip_deadline", state=AddTopicState.waiting_for_title)
async def skip_deadline(callback: types.CallbackQuery, state: FSMContext):
    """Deadline ni o'tkazib yuborish va show_detailed_results so'rash"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="✅ Ha", callback_data="detailed_yes"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data="detailed_no")
    )

    await callback.message.edit_text(
        "📊 Batafsil natijalarni ko'rsatish?\n\n"
        "Agar <b>Ha</b> deb tanlasangiz, talabalar testni topshirgandan so'ng har bir savol to'g'ri/noto'g'ri ekanligini ko'radi.\n\n"
        "Agar <b>Yo'q</b> deb tanlasangiz, faqat umumiy natija (umumiy ball) ko'rinadi.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await AddTopicState.waiting_for_detailed_results.set()
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "set_deadline", state=AddTopicState.waiting_for_title)
async def set_deadline_request(callback: types.CallbackQuery, state: FSMContext):
    """Deadline belgilash uchun so'rash"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"📅 Deadline ni quyidagi formatda yuboring:\n\n"
        f"<code>KUN.OY.YIL SOAT:DAQIQA</code>\n\n"
        f"Masalan:\n"
        f"<code>15.02.2026 23:59</code>\n"
        f"<code>20.03.2026 18:00</code>\n\n"
        f"❌ Bekor qilish uchun /cancel",
        parse_mode="HTML"
    )
    
    await AddTopicState.waiting_for_deadline.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=AddTopicState.waiting_for_deadline, user_id=ADMINS)
async def process_deadline(message: types.Message, state: FSMContext):
    """Deadline ni qabul qilish va mavzuni yaratish"""
    deadline_text = message.text.strip()
    
    # Deadline ni parse qilish
    from datetime import datetime
    import pytz
    
    try:
        # Format: "15.02.2026 23:59"
        dt = datetime.strptime(deadline_text, "%d.%m.%Y %H:%M")
        
        # Tashkent timezone bilan
        tashkent_tz = pytz.timezone('Asia/Tashkent')
        dt_aware = tashkent_tz.localize(dt)
        
        # ISO 8601 formatga o'zgartirish (API uchun)
        deadline_iso = dt_aware.isoformat()
        
    except ValueError:
        await message.answer(
            "❌ Xato format! Iltimos, quyidagi formatda yuboring:\n\n"
            "<code>KUN.OY.YIL SOAT:DAQIQA</code>\n\n"
            "Masalan: <code>15.02.2026 23:59</code>\n\n"
            "Qaytadan yuboring yoki /cancel",
            parse_mode="HTML"
        )
        return
    
    # Deadline ni odam tushunadigan formatga o'zgartirish
    deadline_readable = dt.strftime("%d.%m.%Y %H:%M")

    await state.update_data(deadline_iso=deadline_iso, deadline_readable=deadline_readable)

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(text="✅ Ha", callback_data="detailed_yes"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data="detailed_no")
    )

    await message.answer(
        f"✅ Deadline: {deadline_readable}\n\n"
        "📊 Batafsil natijalarni ko'rsatish?\n\n"
        "Agar <b>Ha</b> deb tanlasangiz, talabalar testni topshirgandan so'ng har bir savol to'g'ri/noto'g'ri ekanligini ko'radi.\n\n"
        "Agar <b>Yo'q</b> deb tanlasangiz, faqat umumiy natija (umumiy ball) ko'rinadi.",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await AddTopicState.waiting_for_detailed_results.set()


@dp.callback_query_handler(lambda c: c.data in ("detailed_yes", "detailed_no"), state=AddTopicState.waiting_for_detailed_results)
async def process_detailed_results(callback: types.CallbackQuery, state: FSMContext):
    """show_detailed_results tanlash va mavzuni yaratish"""
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    await callback.answer()

    show_detailed = callback.data == "detailed_yes"
    data = await state.get_data()
    course_id = data.get('course_id')
    course_name = data.get('course_name')
    title = data.get('title')
    deadline_iso = data.get('deadline_iso')
    deadline_readable = data.get('deadline_readable', "Yo'q")

    if not course_id or not title:
        await callback.message.answer("❌ Ma'lumotlar topilmadi. Qaytadan boshlang.")
        await state.finish()
        return

    payload = {
        "course_id": course_id,
        "title": title,
        "is_active": False,
        "show_detailed_results": show_detailed,
    }
    if deadline_iso:
        payload["deadline"] = deadline_iso

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/topics/create/", json=payload) as resp:
                if resp.status == 201:
                    topic_data = await resp.json()
                    topic_id = topic_data['id']
                    detailed_label = "✅ Ha" if show_detailed else "❌ Yo'q"

                    await callback.message.edit_text(
                        f"✅ Yangi mavzu muvaffaqiyatli yaratildi!\n\n"
                        f"📚 Kurs: {course_name}\n"
                        f"📝 Mavzu: {title}\n"
                        f"🆔 ID: {topic_id}\n"
                        f"📅 Deadline: {deadline_readable}\n"
                        f"📊 Batafsil natijalar: {detailed_label}\n"
                        f"🔴 Status: Inactive\n\n"
                        f"Mavzuni active qilish uchun: /activate {topic_id}"
                    )
                else:
                    error_text = await resp.text()
                    await callback.message.edit_text(f"❌ Xatolik yuz berdi (status {resp.status}):\n{error_text[:300]}")
    except Exception as e:
        await callback.message.answer(f"❌ Xatolik: {e}")
    finally:
        await state.finish()


# ═══════════════════════════════════════════════════════════════
# --- SOZLAMALAR: schedule (on/off, kunlar, vaqt) + Haftalik PDF ---
# ═══════════════════════════════════════════════════════════════

_JOB_EXPLANATIONS = {
    'weekly_report': "Tanlangan kunlarda har bir guruhga avtomatik PDF hisobot yuboriladi.",
    'unsubmitted_warnings': "Tanlangan kunlarda vazifa topshirmagan studentlarga shaxsiy eslatma + adminlarga yig'ma ro'yxat fayl yuboriladi.",
    'deadline_results': "Tanlangan kunlarda o'sha kuni muddati tugagan testlar bo'yicha studentlarga batafsil natija (qaysi savolga qanday javob berilgani) + adminga umumiy hisobot yuboriladi.",
    'attendance_csv': "Tanlangan kunlarda haftalik davomat statistikasi CSV fayl qilib faqat adminlarga yuboriladi.",
    'followup_reminders': "Tanlangan kunlarda qo'ng'iroq qilingan, lekin hali vazifa topshirmagan studentlar ro'yxati adminlarga yuboriladi.",
}


async def settings_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    from base_app.models import ScheduleConfig, WeeklyReportSetting
    configs = await sync_to_async(list)(ScheduleConfig.objects.all())
    config_map = {c.job_key: c for c in configs}
    weekly_setting = await sync_to_async(WeeklyReportSetting.objects.first)()

    kb = InlineKeyboardMarkup(row_width=1)
    for job_key, label in JOB_LABELS.items():
        cfg = config_map.get(job_key)
        if cfg:
            enabled, weekdays, hour, minute = cfg.enabled, cfg.weekdays, cfg.hour, cfg.minute
        else:
            d = DEFAULT_SCHEDULE[job_key]
            enabled, weekdays, hour, minute = True, d['weekdays'], d['hour'], d['minute']
        status = "✅" if enabled else "🚫"
        btn_text = f"{status} {label} — {days_str_to_label(weekdays)} {hour:02d}:{minute:02d}"
        kb.add(InlineKeyboardButton(btn_text, callback_data=f"sjob:{job_key}"))

    kb.add(InlineKeyboardButton(f"📄 Haftalik PDF — {_pdf_setting_label(weekly_setting)}", callback_data="spdf"))
    kb.add(InlineKeyboardButton("🔥 Oylik streak rejimi", callback_data="sstreak"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_back"))

    await callback.message.edit_text(
        "⚙️ <b>Sozlamalar</b>\n\nKerakli vazifani tanlang:",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


async def _render_job_detail(callback: types.CallbackQuery, job_key: str):
    from base_app.models import ScheduleConfig
    cfg = await sync_to_async(ScheduleConfig.objects.filter(job_key=job_key).first)()
    if cfg:
        enabled, weekdays, hour, minute = cfg.enabled, cfg.weekdays, cfg.hour, cfg.minute
    else:
        d = DEFAULT_SCHEDULE[job_key]
        enabled, weekdays, hour, minute = True, d['weekdays'], d['hour'], d['minute']

    status_lbl = "✅ Yoqilgan" if enabled else "🚫 O'chirilgan"
    text = (
        f"{JOB_LABELS[job_key]}\n\n"
        f"Holat: {status_lbl}\n"
        f"Kunlar: {days_str_to_label(weekdays)}\n"
        f"Vaqt: {hour:02d}:{minute:02d}\n\n"
        f"{_JOB_EXPLANATIONS[job_key]}"
    )
    kb = InlineKeyboardMarkup(row_width=1)
    toggle_lbl = "🚫 O'chirish" if enabled else "✅ Yoqish"
    kb.add(InlineKeyboardButton(toggle_lbl, callback_data=f"stoggle:{job_key}"))
    kb.add(InlineKeyboardButton("📅 Kunlarni o'zgartirish", callback_data=f"sdays:{job_key}"))
    kb.add(InlineKeyboardButton("🕐 Vaqtni o'zgartirish", callback_data=f"stime:{job_key}"))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_settings"))

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data.startswith("sjob:"))
async def settings_job_detail(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    await state.finish()
    job_key = callback.data.split(":", 1)[1]
    await _render_job_detail(callback, job_key)
    await callback.answer()


async def _get_or_default_cfg(job_key):
    from base_app.models import ScheduleConfig
    d = DEFAULT_SCHEDULE[job_key]

    def _get():
        cfg, _ = ScheduleConfig.objects.get_or_create(job_key=job_key, defaults={
            'enabled': True, 'weekdays': d['weekdays'], 'hour': d['hour'], 'minute': d['minute'],
        })
        return cfg
    return await sync_to_async(_get)()


# --- Yoqish/o'chirish ---

@dp.callback_query_handler(lambda c: c.data.startswith("stoggle:"))
async def settings_toggle_ask(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    job_key = callback.data.split(":", 1)[1]
    cfg = await _get_or_default_cfg(job_key)

    if cfg.enabled:
        text = (
            f"{JOB_LABELS[job_key]}\n\n"
            f"Hozir: ✅ Yoqilgan — {_JOB_EXPLANATIONS[job_key]}\n\n"
            f"O'chirsangiz, bu xabar/hisobot butunlay yuborilmay qo'yadi (ma'lumotlar yo'qolmaydi, "
            f"xohlagan payt qayta yoqish mumkin).\n\nO'chirishni tasdiqlaysizmi?"
        )
    else:
        text = (
            f"{JOB_LABELS[job_key]}\n\n"
            f"Hozir: 🚫 O'chirilgan.\n\n"
            f"Yoqsangiz: {_JOB_EXPLANATIONS[job_key]}\n\nYoqishni tasdiqlaysizmi?"
        )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha", callback_data=f"stoggleapply:{job_key}"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"sjob:{job_key}"),
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("stoggleapply:"))
async def settings_toggle_apply(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    job_key = callback.data.split(":", 1)[1]
    cfg = await _get_or_default_cfg(job_key)

    def _flip():
        from django.db import close_old_connections
        close_old_connections()
        cfg.enabled = not cfg.enabled
        cfg.save(update_fields=['enabled'])
        return cfg
    cfg = await sync_to_async(_flip)()

    if cfg.enabled:
        apply_job(job_key, cfg.weekdays, cfg.hour, cfg.minute)
    else:
        remove_job(job_key)

    await callback.answer("✅ Saqlandi")
    await _render_job_detail(callback, job_key)


# --- Kunlarni o'zgartirish ---

async def _render_days_kb(callback: types.CallbackQuery, job_key: str, selected: list):
    kb = InlineKeyboardMarkup(row_width=2)
    for day in DAY_ORDER:
        mark = "✅" if day in selected else "☐"
        kb.add(InlineKeyboardButton(f"{mark} {DAY_LABELS[day]}", callback_data=f"sdaytoggle:{day}"))
    kb.add(InlineKeyboardButton("➡️ Davom etish", callback_data="sdayconfirm"))
    kb.add(InlineKeyboardButton("🔙 Bekor qilish", callback_data=f"sjob:{job_key}"))
    text = f"{JOB_LABELS[job_key]}\n\nQaysi kunlarda ishlashini tanlang (kamida 1 ta):"
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data.startswith("sdays:"))
async def settings_days_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    job_key = callback.data.split(":", 1)[1]
    cfg = await _get_or_default_cfg(job_key)
    selected = [d for d in cfg.weekdays.split(',') if d] if cfg.weekdays else list(DAY_ORDER)

    await state.update_data(settings_job_key=job_key, settings_selected_days=selected)
    await SettingsState.waiting_for_days_selection.set()
    await _render_days_kb(callback, job_key, selected)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sdaytoggle:"), state=SettingsState.waiting_for_days_selection)
async def settings_days_toggle(callback: types.CallbackQuery, state: FSMContext):
    day = callback.data.split(":", 1)[1]
    data = await state.get_data()
    job_key = data.get('settings_job_key')
    selected = list(data.get('settings_selected_days', []))
    if day in selected:
        selected.remove(day)
    else:
        selected.append(day)
    await state.update_data(settings_selected_days=selected)
    await _render_days_kb(callback, job_key, selected)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "sdayconfirm", state=SettingsState.waiting_for_days_selection)
async def settings_days_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    job_key = data.get('settings_job_key')
    selected = data.get('settings_selected_days', [])
    if not selected:
        await callback.answer("⚠️ Kamida 1 ta kun tanlang!", show_alert=True)
        return

    cfg = await _get_or_default_cfg(job_key)
    old_days = days_str_to_label(cfg.weekdays)
    new_days_str = ",".join(d for d in DAY_ORDER if d in selected)
    new_days = days_str_to_label(new_days_str)

    await state.update_data(settings_new_days=new_days_str)

    text = (
        f"{JOB_LABELS[job_key]}\n\n"
        f"Hozir: {old_days}\n"
        f"Yangi: {new_days}\n\n"
        f"Bu kunlarga o'zgartirishni tasdiqlaysizmi?"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha", callback_data="sdayapply"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"sjob:{job_key}"),
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "sdayapply", state=SettingsState.waiting_for_days_selection)
async def settings_days_apply(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    job_key = data.get('settings_job_key')
    new_days_str = data.get('settings_new_days', '')

    cfg = await _get_or_default_cfg(job_key)

    def _save():
        from django.db import close_old_connections
        close_old_connections()
        cfg.weekdays = new_days_str
        cfg.save(update_fields=['weekdays'])
        return cfg
    cfg = await sync_to_async(_save)()

    if cfg.enabled:
        apply_job(job_key, cfg.weekdays, cfg.hour, cfg.minute)

    await state.finish()
    await callback.answer("✅ Saqlandi")
    await _render_job_detail(callback, job_key)


# --- Vaqtni o'zgartirish ---

@dp.callback_query_handler(lambda c: c.data.startswith("stime:"))
async def settings_time_start(callback: types.CallbackQuery, state: FSMContext):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    job_key = callback.data.split(":", 1)[1]
    await state.update_data(settings_job_key=job_key)
    await SettingsState.waiting_for_time_input.set()
    await callback.message.edit_text(
        f"{JOB_LABELS[job_key]}\n\n"
        f"Yangi vaqtni HH:MM formatida yuboring (masalan: 14:30).\n\n/cancel — bekor qilish",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message_handler(state=SettingsState.waiting_for_time_input)
async def settings_time_input(message: types.Message, state: FSMContext):
    if str(message.from_user.id) not in ADMINS:
        return
    text = message.text.strip() if message.text else ''
    if text == '/cancel':
        await state.finish()
        await message.answer("✅ Bekor qilindi.")
        return

    import re
    m = re.match(r'^([01]?\d|2[0-3]):([0-5]\d)$', text)
    if not m:
        await message.answer("❌ Noto'g'ri format. HH:MM ko'rinishida yuboring (masalan: 09:05 yoki 21:30).")
        return
    hour, minute = int(m.group(1)), int(m.group(2))

    data = await state.get_data()
    job_key = data.get('settings_job_key')
    cfg = await _get_or_default_cfg(job_key)

    await state.update_data(settings_new_hour=hour, settings_new_minute=minute)

    text_out = (
        f"{JOB_LABELS[job_key]}\n\n"
        f"Hozir: {cfg.hour:02d}:{cfg.minute:02d}\n"
        f"Yangi: {hour:02d}:{minute:02d}\n\n"
        f"O'zgartirishni tasdiqlaysizmi?"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha", callback_data="stimeapply"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"sjob:{job_key}"),
    )
    await message.answer(text_out, reply_markup=kb, parse_mode="HTML")


@dp.callback_query_handler(lambda c: c.data == "stimeapply", state=SettingsState.waiting_for_time_input)
async def settings_time_apply(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    job_key = data.get('settings_job_key')
    hour = data.get('settings_new_hour')
    minute = data.get('settings_new_minute')

    cfg = await _get_or_default_cfg(job_key)

    def _save():
        from django.db import close_old_connections
        close_old_connections()
        cfg.hour = hour
        cfg.minute = minute
        cfg.save(update_fields=['hour', 'minute'])
        return cfg
    cfg = await sync_to_async(_save)()

    if cfg.enabled:
        apply_job(job_key, cfg.weekdays, cfg.hour, cfg.minute)

    await state.finish()
    await callback.answer("✅ Saqlandi")
    await _render_job_detail(callback, job_key)


# --- Haftalik PDF sozlamasi (oxirgi 10 ta / aniq oy / avtomatik joriy oy) ---

def _pdf_setting_label(setting) -> str:
    if setting and setting.mode == 'auto':
        return "🔄 Avtomatik (har doim joriy oy)"
    if setting and setting.mode == 'month' and setting.year and setting.month:
        return f"{MONTH_NAMES_UZ[setting.month]} {setting.year}"
    return "Standart (oxirgi 10 ta mavzu)"


@dp.callback_query_handler(lambda c: c.data == "spdf")
async def settings_pdf_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    from base_app.models import WeeklyReportSetting
    setting = await sync_to_async(WeeklyReportSetting.objects.first)()
    current_lbl = _pdf_setting_label(setting)

    from datetime import date
    today = date.today()
    prev_y, prev_m = today.year, today.month - 1
    if prev_m == 0:
        prev_m, prev_y = 12, prev_y - 1

    is_auto = bool(setting and setting.mode == 'auto')
    is_current = bool(setting and setting.mode == 'month' and setting.year == today.year and setting.month == today.month)
    is_prev = bool(setting and setting.mode == 'month' and setting.year == prev_y and setting.month == prev_m)
    is_other_month = bool(setting and setting.mode == 'month' and not is_current and not is_prev)
    is_default = bool(not setting or setting.mode == 'last10')

    def mark(active):
        return "✅ " if active else ""

    text = (
        "📄 <b>Haftalik PDF sozlamasi</b>\n\n"
        f"Hozirgi rejim: <b>{current_lbl}</b> ✅\n\n"
        "Bu sozlama haftalik PDF hisobotda qaysi mavzular ustun sifatida ko'rsatilishini belgilaydi."
    )
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(f"{mark(is_auto)}🔄 Avtomatik (har doim joriy oy)", callback_data="spdfmode:auto"),
        InlineKeyboardButton(f"{mark(is_current)}📌 Joriy oyni qotirish", callback_data="spdfmode:current"),
        InlineKeyboardButton(f"{mark(is_prev)}⏮ Oldingi oy", callback_data="spdfmode:prev"),
        InlineKeyboardButton(f"{mark(is_other_month)}🗓 Boshqa oy tanlash", callback_data="spdfmode:pick"),
        InlineKeyboardButton(f"{mark(is_default)}♻️ Standart (oxirgi 10 ta)", callback_data="spdfmode:default"),
        InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_settings"),
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


async def _show_pdf_confirm(callback: types.CallbackQuery, mode: str, year: int, month: int):
    from base_app.models import WeeklyReportSetting
    setting = await sync_to_async(WeeklyReportSetting.objects.first)()
    old_lbl = _pdf_setting_label(setting)

    if mode == 'last10':
        new_lbl = "Standart (oxirgi 10 ta mavzu)"
        note = "Har bir guruh uchun eng oxirgi qo'shilgan 10 ta mavzu ustun sifatida ko'rsatiladi."
    elif mode == 'auto':
        new_lbl = "🔄 Avtomatik (har doim joriy oy)"
        note = (
            "Har safar haftalik hisobot tuzilayotganda tizim o'sha paytdagi joriy oyni o'zi "
            "hisoblab, faqat shu oyda faollashtirilgan mavzularni ko'rsatadi. Oy almashganda "
            "qo'lda qayta tanlash shart emas."
        )
    else:
        new_lbl = f"{MONTH_NAMES_UZ[month]} {year}"
        note = (
            f"Faqat {new_lbl} oyida faollashtirilgan mavzular ustun sifatida ko'rsatiladi "
            f"(boshqa oylardagi mavzular hisobotga kirmaydi). Bu tanlov shu oyga qotib qoladi — "
            f"keyingi oyda ham shu oy ko'rsatilaveradi, qayta o'zgartirmaguningizcha (agar avtomatik "
            f"rejim kerak bo'lsa, «🔄 Avtomatik» tugmasini tanlang)."
        )

    text = (
        "📄 <b>Haftalik PDF sozlamasi</b>\n\n"
        f"Hozir: <b>{old_lbl}</b>\n"
        f"Yangi: <b>{new_lbl}</b>\n\n"
        f"{note}\n\nTasdiqlaysizmi?"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Ha", callback_data=f"spdfapply:{mode}:{year}:{month}"),
        InlineKeyboardButton("❌ Yo'q", callback_data="spdf"),
    )
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("spdfmode:"))
async def settings_pdf_mode(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    mode = callback.data.split(":", 1)[1]

    if mode == 'pick':
        from base_app.models import Topic
        months = await sync_to_async(list)(
            Topic.objects.filter(activated_at__isnull=False).dates('activated_at', 'month', order='DESC')
        )
        if not months:
            await callback.answer("❌ Hali faollashtirilgan mavzular yo'q.", show_alert=True)
            return
        kb = InlineKeyboardMarkup(row_width=2)
        for d in months:
            kb.add(InlineKeyboardButton(
                f"📅 {MONTH_NAMES_UZ[d.month]} {d.year}",
                callback_data=f"spdfconfirm:{d.year}:{d.month}"
            ))
        kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="spdf"))
        await callback.message.edit_text("🗓 Oyni tanlang:", reply_markup=kb, parse_mode="HTML")
        await callback.answer()
        return

    from datetime import date
    today = date.today()

    if mode == 'default':
        await _show_pdf_confirm(callback, 'last10', 0, 0)
    elif mode == 'auto':
        await _show_pdf_confirm(callback, 'auto', 0, 0)
    elif mode == 'current':
        await _show_pdf_confirm(callback, 'month', today.year, today.month)
    elif mode == 'prev':
        y, m = today.year, today.month - 1
        if m == 0:
            m = 12
            y -= 1
        await _show_pdf_confirm(callback, 'month', y, m)


@dp.callback_query_handler(lambda c: c.data.startswith("spdfconfirm:"))
async def settings_pdf_pick_confirm(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    _, year, month = callback.data.split(":")
    await _show_pdf_confirm(callback, 'month', int(year), int(month))


@dp.callback_query_handler(lambda c: c.data.startswith("spdfapply:"))
async def settings_pdf_apply(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    _, mode, year, month = callback.data.split(":")
    year, month = int(year), int(month)

    from base_app.models import WeeklyReportSetting

    def _save():
        from django.db import close_old_connections
        close_old_connections()
        setting, _ = WeeklyReportSetting.objects.get_or_create(id=1, defaults={'mode': 'last10'})
        setting.mode = mode
        setting.year = year if mode == 'month' else None
        setting.month = month if mode == 'month' else None
        setting.save(update_fields=['mode', 'year', 'month'])
    await sync_to_async(_save)()

    await callback.answer("✅ Saqlandi")
    await settings_pdf_menu(callback)


# --- Oylik streak rejimi ---

_STREAK_EXPLANATION = (
    "Yoqilgan oy uchun Tangalarim, reyting va oylik PDF hisobotda streak (va unga bog'liq "
    "tanga bonusi) o'sha oyning birinchi mavzusidan 1 deb qayta hisoblanadi — avvalgi "
    "oylardagi uzviylik hisobga olinmaydi. Bu faqat ko'rsatish uchun (jonli hisoblanadi), "
    "hech qanday saqlangan ma'lumot o'zgartirilmaydi — o'chirib qo'ysangiz hammasi "
    "yana avvalgidek (uzluksiz) ko'rinadi."
)


@dp.callback_query_handler(lambda c: c.data == "sstreak")
async def settings_streak_menu(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return

    from base_app.models import Topic, MonthlyStreakSetting
    months = await sync_to_async(list)(
        Topic.objects.filter(activated_at__isnull=False).dates('activated_at', 'month', order='DESC')
    )
    if not months:
        await callback.answer("❌ Hali faollashtirilgan mavzular yo'q.", show_alert=True)
        return

    enabled_pairs = await sync_to_async(lambda: set(
        MonthlyStreakSetting.objects.filter(enabled=True).values_list('year', 'month')
    ))()

    kb = InlineKeyboardMarkup(row_width=1)
    for d in months:
        status = "✅" if (d.year, d.month) in enabled_pairs else "🚫"
        kb.add(InlineKeyboardButton(
            f"{status} {MONTH_NAMES_UZ[d.month]} {d.year}",
            callback_data=f"sstoggle:{d.year}:{d.month}"
        ))
    kb.add(InlineKeyboardButton("🔙 Orqaga", callback_data="admin_menu_settings"))

    await callback.message.edit_text(
        f"🔥 <b>Oylik streak rejimi</b>\n\n{_STREAK_EXPLANATION}\n\nOyni tanlang (yoqish/o'chirish):",
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sstoggle:"))
async def settings_streak_toggle(callback: types.CallbackQuery):
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Ruxsat yo'q.", show_alert=True)
        return
    _, year, month = callback.data.split(":")
    year, month = int(year), int(month)

    from base_app.models import MonthlyStreakSetting

    def _toggle():
        from django.db import close_old_connections
        close_old_connections()
        setting, _ = MonthlyStreakSetting.objects.get_or_create(year=year, month=month)
        setting.enabled = not setting.enabled
        setting.save(update_fields=['enabled'])
        return setting.enabled
    new_state = await sync_to_async(_toggle)()

    await callback.answer("✅ Yoqildi" if new_state else "🚫 O'chirildi")
    await settings_streak_menu(callback)
