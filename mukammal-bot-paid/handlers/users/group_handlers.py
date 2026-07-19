"""
Guruhlarni bot admin menyusi orqali boshqarish: ro'yxat, qo'shish, tahrirlash, o'chirish.
Har bir kursning ro'yxatdan o'tish strategiyasiga (registration_strategy) qarab
guruhdan so'raladigan maydonlar farq qiladi (score_min/max, max_students, target_role).
"""
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async

from data.config import ADMINS
from loader import dp, bot
from states.group_state import AddGroupState, EditGroupState
from filters.is_private import IsPrivate
from handlers.users.admin_handlers import REGISTRATION_STRATEGY_LABELS

TARGET_ROLE_LABELS = {
    'student': "🎓 Talaba",
    'teacher': "🧑‍🏫 O'qituvchi",
}


def _is_admin(user_id) -> bool:
    return str(user_id) in ADMINS


# ─── Guruh uchun kurs tanlash ──────────────────────────────────────────────

async def _render_course_list(target):
    from base_app.models import Course

    courses = await sync_to_async(list)(Course.objects.all().order_by('name'))
    if not courses:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(InlineKeyboardButton("➕ Yangi kurs yaratish", callback_data="goto_add_course"))
        await target.answer(
            "❌ Hozircha kurslar mavjud emas.\n\nAvval kurs yarating:",
            reply_markup=keyboard,
        )
        return

    keyboard = InlineKeyboardMarkup(row_width=1)
    for course in courses:
        label = course.name if course.is_active else f"🔴 {course.name} (nofaol)"
        keyboard.add(InlineKeyboardButton(label, callback_data=f"groupmgmt_course_{course.id}"))

    await target.answer("👥 Qaysi kursning guruhlarini boshqarmoqchisiz?", reply_markup=keyboard)


@dp.message_handler(IsPrivate(), lambda msg: msg.text == "👥 Guruhlarni boshqarish", user_id=ADMINS)
async def manage_groups_start(message: types.Message):
    await _render_course_list(message)


# ─── Bitta kursning guruhlar ro'yxati ──────────────────────────────────────

async def _render_group_list(callback_message, course):
    from base_app.models import Group

    groups = await sync_to_async(list)(
        Group.objects.filter(course=course).order_by('id')
    )

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("➕ Guruh qo'shish", callback_data=f"groupmgmt_add_{course.id}"))

    lines = [f"👥 <b>{course.name}</b> — guruhlar\n"]
    lines.append(f"Ro'yxatdan o'tish tartibi: {REGISTRATION_STRATEGY_LABELS[course.registration_strategy]}\n")

    if not groups:
        lines.append("Hozircha guruh yo'q.")
    else:
        for g in groups:
            count = await sync_to_async(g.enrolled_students.count)()
            link_mark = "🔗" if g.telegram_group_id else "❌ ulanmagan"
            keyboard.add(InlineKeyboardButton(f"{g.name} ({count} ta) {link_mark}", callback_data=f"groupmgmt_detail_{g.id}"))

    keyboard.add(InlineKeyboardButton("⬅️ Orqaga", callback_data="groupmgmt_backcourses"))

    await callback_message.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_course_"), state="*")
async def group_course_selected(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Course

    course_id = int(callback.data.split("_")[-1])
    course = await sync_to_async(Course.objects.get)(id=course_id)
    await callback.message.delete()
    await _render_group_list(callback.message, course)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data == "groupmgmt_backcourses", state="*")
async def group_back_to_courses(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    await callback.message.delete()
    await _render_course_list(callback.message)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_back_"), state="*")
async def group_back_to_list(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Course

    course_id = int(callback.data.split("_")[-1])
    course = await sync_to_async(Course.objects.get)(id=course_id)
    await callback.message.delete()
    await _render_group_list(callback.message, course)
    await callback.answer()


# ─── Guruh qo'shish ─────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_add_"), state="*")
async def group_add_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    course_id = int(callback.data.split("_")[-1])
    await state.update_data(course_id=course_id)
    await callback.message.edit_text(
        "➕ Yangi guruh\n\n📝 Guruh nomini yuboring:\n\n❌ Bekor qilish uchun /cancel"
    )
    await AddGroupState.waiting_for_name.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=AddGroupState.waiting_for_name, user_id=ADMINS)
async def group_add_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Guruh nomi bo'sh bo'lishi mumkin emas. Qaytadan yuboring yoki /cancel")
        return

    from base_app.models import Group

    if await sync_to_async(Group.objects.filter(name=name).exists)():
        await message.answer("❌ Bu nomli guruh allaqachon mavjud. Boshqa nom kiriting yoki /cancel")
        return

    await state.update_data(name=name)

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(InlineKeyboardButton("⏭ Keyinroq ulayman", callback_data="groupmgmt_skiplink"))
    await message.answer(
        "🔗 Endi shu guruhni Telegram guruhiga ulaymiz.\n\n"
        "1️⃣ Botni o'sha Telegram guruhga admin qilib qo'shing\n"
        "2️⃣ Guruh ichida <code>/groupid</code> deb yozing — bot chat ID sini yuboradi\n"
        "3️⃣ Shu ID’ni (masalan <code>-1001234567890</code>) shu yerga yuboring\n\n"
        "Hozircha ulamasangiz ham bo'ladi — keyin guruh tafsilotidan ulashingiz mumkin.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await AddGroupState.waiting_for_telegram_id.set()


@dp.callback_query_handler(lambda c: c.data == "groupmgmt_skiplink", state=AddGroupState.waiting_for_telegram_id)
async def group_add_skip_link(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    await state.update_data(telegram_group_id=None)
    await callback.answer()
    await _ask_strategy_fields(callback.message, state)


@dp.message_handler(IsPrivate(), state=AddGroupState.waiting_for_telegram_id, user_id=ADMINS)
async def group_add_telegram_id(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not (text.lstrip("-").isdigit()):
        await message.answer(
            "❌ Noto'g'ri format. Guruh ID raqam bo'lishi kerak (masalan -1001234567890).\n"
            "Qaytadan yuboring yoki ⏭ Keyinroq tugmasini bosing."
        )
        return
    await state.update_data(telegram_group_id=text)
    await _ask_strategy_fields(message, state)


async def _ask_strategy_fields(target, state: FSMContext):
    """Kurs strategiyasiga qarab keyingi qadamni so'raydi (score/capacity/role)."""
    from base_app.models import Course

    data = await state.get_data()
    course = await sync_to_async(Course.objects.get)(id=data["course_id"])

    if course.registration_strategy == 'score_range':
        await target.answer(
            "📊 Ball oralig'i — minimal ball (masalan <code>27</code>).\n"
            "Cheklov bo'lmasa <code>-</code> yuboring:",
            parse_mode="HTML",
        )
        await AddGroupState.waiting_for_score_min.set()
    elif course.registration_strategy == 'role':
        keyboard = InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            InlineKeyboardButton(TARGET_ROLE_LABELS['student'], callback_data="groupmgmt_addrole_student"),
            InlineKeyboardButton(TARGET_ROLE_LABELS['teacher'], callback_data="groupmgmt_addrole_teacher"),
        )
        await target.answer("🎓 Bu guruh kimlar uchun?", reply_markup=keyboard)
        await AddGroupState.waiting_for_target_role.set()
    else:  # capacity
        await target.answer("🔢 Guruh sig'imi (nechta studentdan keyin to'lgan hisoblansin)? Masalan: <code>50</code>", parse_mode="HTML")
        await AddGroupState.waiting_for_max_students.set()


@dp.message_handler(IsPrivate(), state=AddGroupState.waiting_for_score_min, user_id=ADMINS)
async def group_add_score_min(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        await state.update_data(score_min=None)
    elif text.isdigit():
        await state.update_data(score_min=int(text))
    else:
        await message.answer("❌ Faqat raqam yoki <code>-</code> yuboring:", parse_mode="HTML")
        return

    await message.answer(
        "📊 Ball oralig'i — maksimal ball (masalan <code>35</code>).\n"
        "Cheklov bo'lmasa <code>-</code> yuboring:",
        parse_mode="HTML",
    )
    await AddGroupState.waiting_for_score_max.set()


@dp.message_handler(IsPrivate(), state=AddGroupState.waiting_for_score_max, user_id=ADMINS)
async def group_add_score_max(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        await state.update_data(score_max=None)
    elif text.isdigit():
        await state.update_data(score_max=int(text))
    else:
        await message.answer("❌ Faqat raqam yoki <code>-</code> yuboring:", parse_mode="HTML")
        return

    await _create_group_from_state(message, state)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_addrole_"), state=AddGroupState.waiting_for_target_role)
async def group_add_role(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    role = callback.data[len("groupmgmt_addrole_"):]
    await state.update_data(target_role=role)
    await callback.message.edit_text(f"✅ {TARGET_ROLE_LABELS[role]}")
    await callback.answer()
    await callback.message.answer("🔢 Guruh sig'imi (nechta studentdan keyin to'lgan hisoblansin)? Masalan: <code>50</code>", parse_mode="HTML")
    await AddGroupState.waiting_for_max_students.set()


@dp.message_handler(IsPrivate(), state=AddGroupState.waiting_for_max_students, user_id=ADMINS)
async def group_add_max_students(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Musbat raqam kiriting:")
        return
    await state.update_data(max_students=int(text))
    await _create_group_from_state(message, state)


async def _create_group_from_state(target, state: FSMContext):
    from base_app.models import Group, Course

    data = await state.get_data()
    course = await sync_to_async(Course.objects.get)(id=data["course_id"])

    group = await sync_to_async(Group.objects.create)(
        course=course,
        name=data["name"],
        telegram_group_id=data.get("telegram_group_id"),
        score_min=data.get("score_min"),
        score_max=data.get("score_max"),
        max_students=data.get("max_students") or 30,
        target_role=data.get("target_role"),
    )

    link_status = "🔗 Telegram guruhiga ulandi" if group.telegram_group_id else "❌ Telegram guruhiga hali ulanmagan"
    await target.answer(
        f"✅ Guruh yaratildi!\n\n"
        f"👥 Nomi: {group.name}\n"
        f"📚 Kurs: {course.name}\n"
        f"{link_status}\n\n"
        f"👥 Guruhlarni boshqarish orqali keyinroq ham tahrirlashingiz mumkin.",
    )
    await state.finish()


# ─── Guruh tafsiloti / tahrirlash ──────────────────────────────────────────

async def _render_group_detail(target, group):
    course = await sync_to_async(lambda: group.course)()
    count = await sync_to_async(group.enrolled_students.count)()

    lines = [
        f"👥 <b>{group.name}</b>\n",
        f"📚 Kurs: {course.name}",
        f"👤 Studentlar: {count} ta",
        f"🔗 Telegram ID: {group.telegram_group_id or '— ulanmagan'}",
    ]

    keyboard = InlineKeyboardMarkup(row_width=1)
    if course.registration_strategy == 'score_range':
        lines.append(f"📊 Ball oralig'i: {group.score_min if group.score_min is not None else '—'} – {group.score_max if group.score_max is not None else '—'}")
        keyboard.add(InlineKeyboardButton("📊 Ball oralig'ini o'zgartirish", callback_data=f"groupmgmt_editscore_{group.id}"))
    elif course.registration_strategy == 'role':
        role_label = TARGET_ROLE_LABELS.get(group.target_role, "— belgilanmagan")
        lines.append(f"🎓 Rol: {role_label}")
        lines.append(f"🔢 Sig'im: {group.max_students}")
        keyboard.add(InlineKeyboardButton("🎓 Rolni o'zgartirish", callback_data=f"groupmgmt_editrole_{group.id}"))
        keyboard.add(InlineKeyboardButton("🔢 Sig'imni o'zgartirish", callback_data=f"groupmgmt_editmax_{group.id}"))
    else:
        lines.append(f"🔢 Sig'im: {group.max_students}")
        keyboard.add(InlineKeyboardButton("🔢 Sig'imni o'zgartirish", callback_data=f"groupmgmt_editmax_{group.id}"))

    keyboard.add(
        InlineKeyboardButton("✏️ Nomini o'zgartirish", callback_data=f"groupmgmt_rename_{group.id}"),
        InlineKeyboardButton("🔗 Telegram guruhini ulash/o'zgartirish", callback_data=f"groupmgmt_link_{group.id}"),
        InlineKeyboardButton("🗑 O'chirish", callback_data=f"groupmgmt_delconfirm_{group.id}"),
        InlineKeyboardButton("⬅️ Orqaga", callback_data=f"groupmgmt_back_{course.id}"),
    )

    await target.answer("\n".join(lines), parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_detail_"), state="*")
async def group_detail(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group

    group_id = int(callback.data.split("_")[-1])
    group = await sync_to_async(Group.objects.select_related('course').get)(id=group_id)
    await callback.message.delete()
    await _render_group_detail(callback.message, group)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_rename_"), state="*")
async def group_rename_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(edit_group_id=group_id)
    await callback.message.answer("✏️ Guruhning yangi nomini yuboring:\n\n❌ Bekor qilish uchun /cancel")
    await EditGroupState.waiting_for_new_name.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=EditGroupState.waiting_for_new_name, user_id=ADMINS)
async def group_rename_finish(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if not new_name:
        await message.answer("❌ Guruh nomi bo'sh bo'lishi mumkin emas. Qaytadan yuboring yoki /cancel")
        return

    from base_app.models import Group

    data = await state.get_data()
    group_id = data["edit_group_id"]

    if await sync_to_async(Group.objects.filter(name=new_name).exclude(id=group_id).exists)():
        await message.answer("❌ Bu nomli guruh allaqachon mavjud. Boshqa nom kiriting yoki /cancel")
        return

    group = await sync_to_async(Group.objects.select_related('course').get)(id=group_id)
    old_name = group.name
    group.name = new_name
    await sync_to_async(group.save)()

    await state.finish()
    await message.answer(f"✅ Guruh nomi o'zgartirildi: {old_name} → {new_name}")
    await _render_group_detail(message, group)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_link_"), state="*")
async def group_link_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(edit_group_id=group_id)
    await callback.message.answer(
        "🔗 Telegram guruh ID sini yuboring.\n\n"
        "1️⃣ Botni o'sha guruhga admin qilib qo'shing\n"
        "2️⃣ Guruh ichida <code>/groupid</code> deb yozing\n"
        "3️⃣ Bot yuborgan ID’ni shu yerga yuboring (masalan <code>-1001234567890</code>)\n\n"
        "❌ Bekor qilish uchun /cancel",
        parse_mode="HTML",
    )
    await EditGroupState.waiting_for_new_telegram_id.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=EditGroupState.waiting_for_new_telegram_id, user_id=ADMINS)
async def group_link_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.lstrip("-").isdigit():
        await message.answer("❌ Noto'g'ri format. Guruh ID raqam bo'lishi kerak. Qaytadan yuboring yoki /cancel")
        return

    from base_app.models import Group

    data = await state.get_data()
    group = await sync_to_async(Group.objects.select_related('course').get)(id=data["edit_group_id"])
    group.telegram_group_id = text
    await sync_to_async(group.save)()

    await state.finish()
    await message.answer(f"✅ <b>{group.name}</b> Telegram guruhiga ulandi.", parse_mode="HTML")
    await _render_group_detail(message, group)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_editmax_"), state="*")
async def group_edit_max_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(edit_group_id=group_id)
    await callback.message.answer("🔢 Yangi sig'imni yuboring (musbat raqam):\n\n❌ Bekor qilish uchun /cancel")
    await EditGroupState.waiting_for_new_max_students.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=EditGroupState.waiting_for_new_max_students, user_id=ADMINS)
async def group_edit_max_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if not text.isdigit() or int(text) <= 0:
        await message.answer("❌ Musbat raqam kiriting:")
        return

    from base_app.models import Group

    data = await state.get_data()
    group = await sync_to_async(Group.objects.select_related('course').get)(id=data["edit_group_id"])
    group.max_students = int(text)
    group.is_full = False
    await sync_to_async(group.save)()

    await state.finish()
    await message.answer(f"✅ Sig'im yangilandi: {group.max_students}")
    await _render_group_detail(message, group)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_editscore_"), state="*")
async def group_edit_score_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    group_id = int(callback.data.split("_")[-1])
    await state.update_data(edit_group_id=group_id)
    await callback.message.answer(
        "📊 Yangi minimal ball (cheklov bo'lmasa <code>-</code>):",
        parse_mode="HTML",
    )
    await EditGroupState.waiting_for_new_score_min.set()
    await callback.answer()


@dp.message_handler(IsPrivate(), state=EditGroupState.waiting_for_new_score_min, user_id=ADMINS)
async def group_edit_score_min_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        await state.update_data(new_score_min=None)
    elif text.isdigit():
        await state.update_data(new_score_min=int(text))
    else:
        await message.answer("❌ Faqat raqam yoki <code>-</code> yuboring:", parse_mode="HTML")
        return

    await message.answer("📊 Yangi maksimal ball (cheklov bo'lmasa <code>-</code>):", parse_mode="HTML")
    await EditGroupState.waiting_for_new_score_max.set()


@dp.message_handler(IsPrivate(), state=EditGroupState.waiting_for_new_score_max, user_id=ADMINS)
async def group_edit_score_max_finish(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text == "-":
        score_max = None
    elif text.isdigit():
        score_max = int(text)
    else:
        await message.answer("❌ Faqat raqam yoki <code>-</code> yuboring:", parse_mode="HTML")
        return

    from base_app.models import Group

    data = await state.get_data()
    group = await sync_to_async(Group.objects.select_related('course').get)(id=data["edit_group_id"])
    group.score_min = data.get("new_score_min")
    group.score_max = score_max
    await sync_to_async(group.save)()

    await state.finish()
    await message.answer(f"✅ Ball oralig'i yangilandi: {group.score_min if group.score_min is not None else '—'} – {group.score_max if group.score_max is not None else '—'}")
    await _render_group_detail(message, group)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_editrole_"), state="*")
async def group_edit_role_start(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return
    group_id = int(callback.data.split("_")[-1])
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(TARGET_ROLE_LABELS['student'], callback_data=f"groupmgmt_setrole_{group_id}:student"),
        InlineKeyboardButton(TARGET_ROLE_LABELS['teacher'], callback_data=f"groupmgmt_setrole_{group_id}:teacher"),
    )
    await callback.message.edit_text("🎓 Bu guruh kimlar uchun?", reply_markup=keyboard)
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_setrole_"), state="*")
async def group_edit_role_finish(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group

    payload = callback.data[len("groupmgmt_setrole_"):]
    group_id_str, role = payload.split(":", 1)
    group = await sync_to_async(Group.objects.select_related('course').get)(id=int(group_id_str))
    group.target_role = role
    await sync_to_async(group.save)()

    await callback.answer(f"✅ Rol o'zgartirildi: {TARGET_ROLE_LABELS[role]}")
    await _render_group_detail(callback.message, group)


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_delconfirm_"), state="*")
async def group_delete_confirm(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group

    group_id = int(callback.data.split("_")[-1])
    group = await sync_to_async(Group.objects.get)(id=group_id)
    count = await sync_to_async(group.enrolled_students.count)()

    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("✅ Ha, o'chirish", callback_data=f"groupmgmt_delyes_{group_id}"),
        InlineKeyboardButton("❌ Yo'q", callback_data=f"groupmgmt_detail_{group_id}"),
    )
    warn = f"\n\n⚠️ Bu guruhda hozir {count} ta student bor — ular guruhsiz qoladi!" if count else ""
    await callback.message.edit_text(
        f"⚠️ Rostdan ham <b>{group.name}</b> guruhini o'chirmoqchimisiz?{warn}\n\n"
        f"Bu amalni ortga qaytarib bo'lmaydi.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("groupmgmt_delyes_"), state="*")
async def group_delete_execute(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("❌ Sizda bu huquq yo'q.", show_alert=True)
        return

    from base_app.models import Group

    group_id = int(callback.data.split("_")[-1])
    group = await sync_to_async(Group.objects.select_related('course').get)(id=group_id)
    group_name = group.name

    await sync_to_async(group.delete)()

    await callback.message.edit_text(f"✅ <b>{group_name}</b> guruhi o'chirildi.", parse_mode="HTML")
    await callback.answer()


# ─── /groupid — guruh ichida chat ID’ni bilish uchun ───────────────────────

@dp.message_handler(commands=["groupid"])
async def group_id_command(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        return
    await message.answer(f"🆔 Bu guruhning chat ID’si:\n<code>{message.chat.id}</code>", parse_mode="HTML")
