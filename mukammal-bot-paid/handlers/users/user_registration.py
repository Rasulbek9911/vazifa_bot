import asyncio
import logging
import os
import sys
import time

import django
from aiogram import types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

sys.path.insert(0, '/var/www/vazifa_bot')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from base_app.models import Group, Student
from django.db import close_old_connections
from asgiref.sync import sync_to_async

from data.config import ADMINS, ATTESTATSIYA_ADMIN
from keyboards.default.vazifa_keyboard import admin_key, cancel_key, build_vazifa_keyboard
from loader import dp, bot
from states.register_state import RegisterState
from filters.is_private import IsPrivate

GROUP_MEMBER_LIMIT = 200
INVITE_EXPIRE_SECONDS = 24 * 3600  # 24 soat

# ---------------------------------------------------------------------------
# O'zbekiston viloyat → tumanlar ma'lumotlari
# ---------------------------------------------------------------------------
REGIONS = {
    "Toshkent shahri": [
        "Bektemir", "Chilonzor", "Hamza", "Mirobod", "Mirzo Ulug'bek",
        "Sergeli", "Shayxontohur", "Olmazor", "Uchtepa", "Yakkasaroy",
        "Yunusobod", "Yashnobod",
    ],
    "Toshkent viloyati": [
        "Angren", "Bekobod", "Bo'ka", "Bo'stonliq", "Chirchiq", "Chinoz",
        "Keles", "Ohangaron", "Parkent", "Piskent", "Quyichirchiq",
        "Toshkent tumani", "Urtachirchiq", "Yuqorichirchiq", "Zangiota", "Yangiyul",
    ],
    "Samarqand viloyati": [
        "Samarqand shahri", "Bulung'ur", "Ishtixon", "Jomboy", "Kattaqo'rg'on",
        "Narpay", "Nurobod", "Oqdaryo", "Pastdarg'om", "Payariq",
        "Qo'shrabot", "Toyloq", "Urgut",
    ],
    "Buxoro viloyati": [
        "Buxoro shahri", "Vobkent", "G'ijduvon", "Jondor", "Kogon",
        "Olot", "Peshku", "Qorovulbozor", "Romitan", "Shofirkon",
        "Qorako'l",
    ],
    "Farg'ona viloyati": [
        "Farg'ona shahri", "Oltiariq", "Bag'dod", "Beshariq", "Buvayda",
        "Dang'ara", "Furqat", "Qo'qon", "Marg'ilon", "Quva",
        "Rishton", "So'x", "Toshloq", "Uchko'prik", "O'zbekiston",
        "Yozyovon",
    ],
    "Andijon viloyati": [
        "Andijon shahri", "Asaka", "Baliqchi", "Bo'z", "Buloqboshi",
        "Jalaquduq", "Izboskan", "Qo'rg'ontepa", "Marhamat", "Oltinkol",
        "Paxtaobod", "Shahrixon", "Ulugnor", "Xo'jaobod",
    ],
    "Namangan viloyati": [
        "Namangan shahri", "Chortoq", "Chust", "Kosonsoy", "Mingbuloq",
        "Norin", "Pop", "To'raqo'rg'on", "Uchqo'rg'on", "Yangiqo'rg'on",
    ],
    "Qashqadaryo viloyati": [
        "Qarshi shahri", "Chiroqchi", "Dehqonobod", "G'uzor", "Kasbi",
        "Kitob", "Koson", "Mirishkor", "Muborak", "Nishon",
        "Shahrisabz", "Yakkabog'",
    ],
    "Surxondaryo viloyati": [
        "Termiz shahri", "Angor", "Bandixon", "Boysun", "Denov",
        "Jarqo'rg'on", "Muzrabot", "Oltinsoy", "Qiziriq", "Qumqo'rg'on",
        "Sariosiyo", "Sherobod", "Sho'rchi", "Uzun",
    ],
    "Xorazm viloyati": [
        "Urganch shahri", "Bog'ot", "Gurlan", "Xiva", "Xonqa",
        "Hazorasp", "Qo'shko'pir", "Shovot", "Tuproqqal'a", "Yangiariq",
        "Yangibozor",
    ],
    "Jizzax viloyati": [
        "Jizzax shahri", "Arnasoy", "Baxmal", "Do'stlik", "Forish",
        "G'allaorol", "Mirzacho'l", "Paxtakor", "Sharof Rashidov",
        "Yangiobod", "Zafarobod", "Zarbdor", "Zo'rdor",
    ],
    "Sirdaryo viloyati": [
        "Guliston shahri", "Baxt", "Boyovut", "Havast", "Mirzaobod",
        "Oqoltin", "Sardoba", "Sayxunobod", "Shirin", "Xovos",
    ],
    "Navoiy viloyati": [
        "Navoiy shahri", "Karmana", "Konimex", "Navbahor", "Nurota",
        "Qiziltepa", "Tomdi", "Uchquduq", "Xatirchi",
    ],
    "Qoraqalpog'iston": [
        "Nukus shahri", "Amudaryo", "Beruniy", "Chimboy", "Ellikkala",
        "Kegeyli", "Mo'ynoq", "Nukus tumani", "Qanliko'l", "Qo'ng'irot",
        "Qorao'zak", "Shumanay", "Taxtako'pir", "To'rtko'l", "Xo'jayli",
    ],
}

ADMIN_CONTACT = "@A_Fayziev"


# ---------------------------------------------------------------------------
# DB yordamchi funksiyalar
# ---------------------------------------------------------------------------

async def get_student(telegram_id: int) -> dict:
    def _get():
        close_old_connections()
        try:
            s = Student.objects.select_related('registered_course').get(telegram_id=str(telegram_id))
            return {
                "exists": True,
                "full_name": s.full_name,
                "viloyat": s.viloyat,
                "tuman": s.tuman,
                "phone": s.phone,
                "math_score": s.math_score,
                "groups": [{"id": g.id, "name": g.name} for g in s.groups.all()],
                "registered_course_id": s.registered_course_id,
                "registered_course_name": s.registered_course.name if s.registered_course_id else None,
                "role": s.role,
            }
        except Student.DoesNotExist:
            return {"exists": False}

    return await asyncio.to_thread(_get)


def _mark_group_full(group_id: int):
    close_old_connections()
    Group.objects.filter(id=group_id).update(is_full=True)


async def _pick_available_group(candidates: list) -> dict | None:
    """
    Har bir nomzod guruhning jonli Telegram a'zolar sonini tekshiradi
    (admin/owner/botlar hisobga olinmaydi). Birinchi bo'sh joy topilgan guruhga
    1-martalik 24 soatlik taklif havolasi yaratadi. `mark_full=True` bo'lgan
    nomzodlar to'lganda `is_full=True` deb belgilanadi (keyingi tekshiruvlarda
    Telegram API'ga bekorga murojaat qilinmasligi uchun).
    """
    for g in candidates:
        try:
            total = await bot.get_chat_member_count(g["tgid"])
            admins = await bot.get_chat_administrators(g["tgid"])
            regular_members = total - len(admins)

            logging.info(
                f"Guruh '{g['name']}': jami={total}, adminlar={len(admins)}, oddiy={regular_members}, limit={g['limit']}"
            )

            if regular_members < g["limit"]:
                expire_ts = int(time.time()) + INVITE_EXPIRE_SECONDS
                invite = await bot.create_chat_invite_link(
                    chat_id=g["tgid"],
                    member_limit=1,
                    expire_date=expire_ts,
                )
                return {
                    "id": g["id"],
                    "name": g["name"],
                    "invite_link": invite.invite_link,
                    "count": regular_members,
                }
            elif g.get("mark_full"):
                await asyncio.to_thread(_mark_group_full, g["id"])
        except Exception as e:
            logging.warning(f"Guruh '{g['name']}' tekshirishda xatolik: {e}")
            continue

    return None


async def find_available_group(course_id: int, score: int = None, role: str = None) -> dict | None:
    """
    Berilgan kursning ro'yxatdan o'tish strategiyasiga (registration_strategy) qarab
    mos bo'sh guruhni topadi:
      - score_range: ball oralig'iga (score_min/score_max) qarab (eski, ishlab turgan mantiq)
      - capacity:    guruhlar ketma-ket to'ldiriladi (max_students yetguncha)
      - role:        student/o'qituvchi (target_role) ga mos guruh
    """
    from base_app.models import Course

    def _get_course():
        close_old_connections()
        try:
            return Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return None

    course = await asyncio.to_thread(_get_course)
    if course is None:
        return None

    strategy = course.registration_strategy

    if strategy == 'capacity':
        def _get_candidates():
            close_old_connections()
            qs = Group.objects.filter(
                course_id=course_id,
                is_full=False,
                telegram_group_id__isnull=False,
            ).exclude(telegram_group_id='').order_by('id')
            return [
                {"id": g.id, "name": g.name, "tgid": g.telegram_group_id, "limit": g.max_students, "mark_full": True}
                for g in qs
            ]
        candidates = await asyncio.to_thread(_get_candidates)
        return await _pick_available_group(candidates)

    if strategy == 'role':
        def _get_candidates():
            close_old_connections()
            qs = Group.objects.filter(
                course_id=course_id,
                target_role=role,
                is_full=False,
                telegram_group_id__isnull=False,
            ).exclude(telegram_group_id='').order_by('id')
            return [
                {"id": g.id, "name": g.name, "tgid": g.telegram_group_id, "limit": g.max_students, "mark_full": True}
                for g in qs
            ]
        candidates = await asyncio.to_thread(_get_candidates)
        return await _pick_available_group(candidates)

    # score_range (default) — eski, ishlab turgan mantiq: faqat course bo'yicha filtr qo'shildi
    def _get_candidates():
        close_old_connections()
        if score is not None and score > 26:
            qs = Group.objects.filter(
                course_id=course_id,
                score_min__gte=27,
                telegram_group_id__isnull=False,
            ).exclude(telegram_group_id='').order_by('id')
        else:
            qs = Group.objects.filter(
                course_id=course_id,
                score_max__lte=26,
                telegram_group_id__isnull=False,
            ).exclude(telegram_group_id='').order_by('id')
        return [
            {"id": g.id, "name": g.name, "tgid": g.telegram_group_id, "limit": GROUP_MEMBER_LIMIT, "mark_full": False}
            for g in qs
        ]
    candidates = await asyncio.to_thread(_get_candidates)
    return await _pick_available_group(candidates)


async def save_student(telegram_id: int, data: dict, group_id: int):
    def _save():
        close_old_connections()
        student, _ = Student.objects.get_or_create(telegram_id=str(telegram_id))
        student.full_name  = data["full_name"]
        student.viloyat    = data["viloyat"]
        student.tuman      = data["tuman"]
        student.phone      = data["phone"]
        student.math_score = data.get("math_score")
        student.registered_course_id = data.get("course_id")
        student.role = data.get("role")
        student.save()
        group = Group.objects.get(id=group_id)
        student.groups.add(group)

    await asyncio.to_thread(_save)


async def update_student_extra(telegram_id: int, data: dict):
    """Mavjud student uchun qo'shimcha ma'lumotlarni yangilash."""
    def _upd():
        close_old_connections()
        Student.objects.filter(telegram_id=str(telegram_id)).update(
            viloyat=data["viloyat"],
            tuman=data["tuman"],
            phone=data["phone"],
            math_score=data.get("math_score"),
            registered_course_id=data.get("course_id"),
            role=data.get("role"),
        )

    await asyncio.to_thread(_upd)


# ---------------------------------------------------------------------------
# Inline keyboard yordamchilari
# ---------------------------------------------------------------------------

def viloyat_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = [
        InlineKeyboardButton(text=name, callback_data=f"vil:{name}")
        for name in REGIONS
    ]
    kb.add(*buttons)
    return kb


def tuman_keyboard(viloyat: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    tumanlar = REGIONS.get(viloyat, [])
    buttons = [
        InlineKeyboardButton(text=t, callback_data=f"tum:{t}")
        for t in tumanlar
    ]
    kb.add(*buttons)
    kb.add(InlineKeyboardButton(text="⬅️ Orqaga", callback_data="vil:back"))
    return kb


def phone_keyboard() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton(text="📱 Raqamni yuborish", request_contact=True))
    kb.add(KeyboardButton(text="❌ Bekor qilish"))
    return kb


def role_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(text="🎓 Talaba", callback_data="regrole_student"),
        InlineKeyboardButton(text="🧑‍🏫 O'qituvchi", callback_data="regrole_teacher"),
    )
    return kb


# ---------------------------------------------------------------------------
# KURS TANLASH (ro'yxatdan o'tishning 1-navbatdagi qadami)
# ---------------------------------------------------------------------------

async def _ask_course(target, state: FSMContext):
    """
    Faol kurslar ro'yxatini ko'rsatadi. Faqat bitta faol kurs bo'lsa, savol
    berilmay avtomatik tanlanadi (bitta-kursli serverlarda oqim o'zgarmaydi).
    """
    from base_app.models import Course

    courses = await sync_to_async(list)(Course.objects.filter(is_active=True).order_by('name'))

    if not courses:
        await target.answer(
            "⚠️ Hozircha faol kurs mavjud emas.\n\n"
            f"📞 Iltimos, admin bilan bog'laning:\n{ADMIN_CONTACT}",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.finish()
        return

    if len(courses) == 1:
        course = courses[0]
        await state.update_data(course_id=course.id)
        await _after_course_chosen(target, state, course)
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for c in courses:
        kb.add(InlineKeyboardButton(text=c.name, callback_data=f"regcourse_{c.id}"))
    await target.answer("📚 <b>Qaysi kursga ro'yxatdan o'tmoqchisiz?</b>", parse_mode="HTML", reply_markup=kb)
    await RegisterState.course.set()


async def _after_course_chosen(target, state: FSMContext, course):
    await target.answer(
        f"✅ Kurs: <b>{course.name}</b>\n\n🗺 <b>Viloyatingizni tanlang:</b>",
        parse_mode="HTML",
        reply_markup=viloyat_keyboard(),
    )
    await RegisterState.viloyat.set()


@dp.callback_query_handler(lambda c: c.data.startswith("regcourse_"), state=RegisterState.course)
async def step_course(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from base_app.models import Course

    course_id = int(callback.data.split("_")[-1])
    course = await sync_to_async(Course.objects.get)(id=course_id)
    await state.update_data(course_id=course_id)
    await _after_course_chosen(callback.message, state, course)


# ---------------------------------------------------------------------------
# RO'YXATDAN O'TISHNI YAKUNLASH (guruhga biriktirish)
# ---------------------------------------------------------------------------

async def _finalize_registration(send_msg, user_id: int, state: FSMContext, score: int = None, role: str = None):
    """
    Kurs strategiyasidan qat'i nazar ro'yxatdan o'tishning so'nggi qadami:
    guruh qidiradi, topilsa student+guruhni saqlaydi, topilmasa admin bilan
    bog'lanishni so'raydi. `send_msg` — Message yoki CallbackQuery.message
    (ikkalasida ham .answer() bor).
    """
    await state.update_data(math_score=score, role=role)
    data = await state.get_data()
    course_id = data.get("course_id")

    await send_msg.answer("⏳ Ma'lumotlar tekshirilmoqda...", reply_markup=ReplyKeyboardRemove())

    group = await find_available_group(course_id, score=score, role=role)

    if group is None:
        await send_msg.answer(
            f"⚠️ Afsuski, hozircha sizga mos bo'sh guruh mavjud emas.\n\n"
            f"📞 Iltimos, admin bilan bog'laning:\n{ADMIN_CONTACT}",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        if data.get("is_existing"):
            await update_student_extra(user_id, data)
        await state.finish()
        return

    try:
        if data.get("is_existing"):
            await update_student_extra(user_id, data)

            def _add_group():
                close_old_connections()
                s = Student.objects.get(telegram_id=str(user_id))
                g = Group.objects.get(id=group["id"])
                s.groups.add(g)

            await asyncio.to_thread(_add_group)
        else:
            await save_student(user_id, data, group["id"])
    except Exception as e:
        logging.error(f"save_student error for {user_id}: {e}")
        await send_msg.answer(
            "❌ Ma'lumotlarni saqlashda xatolik yuz berdi.\n"
            "Iltimos, admin bilan bog'laning: " + ADMIN_CONTACT,
        )
        await state.finish()
        return

    if role:
        role_label = "Talaba" if role == "student" else "O'qituvchi"
        detail_line = f"🎓 Rol: {role_label}\n"
    elif score is not None:
        detail_line = f"📊 Ball: {score}/35\n"
    else:
        detail_line = ""

    await send_msg.answer(
        f"✅ <b>Ro'yxatdan muvaffaqiyatli o'tdingiz!</b>\n\n"
        f"👤 Ism: {data['full_name']}\n"
        f"🗺 Viloyat: {data['viloyat']}\n"
        f"🏘 Tuman: {data['tuman']}\n"
        f"{detail_line}\n"
        f"👥 Guruhingiz: <b>{group['name']}</b>\n\n"
        f"🔗 Guruhga qo'shilish uchun:\n{group['invite_link']}\n\n"
        f"Guruhga qo'shilgach vazifa yuborishingiz mumkin bo'ladi.",
        parse_mode="HTML",
        reply_markup=await build_vazifa_keyboard(user_id),
    )
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("regrole_"), state=RegisterState.role)
async def step_role(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    role = callback.data.split("_", 1)[1]  # "student" yoki "teacher"
    role_label = "Talaba" if role == "student" else "O'qituvchi"
    await callback.message.edit_text(f"✅ Rol: {role_label}")
    await _finalize_registration(callback.message, callback.from_user.id, state, role=role)


# ---------------------------------------------------------------------------
# CANCEL
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), Text(equals="❌ Bekor qilish", ignore_case=True), state="*")
async def cancel_registration(message: types.Message, state: FSMContext):
    cur = await state.get_state()
    if cur is None:
        return
    await state.finish()
    await message.answer(
        "❌ Bekor qilindi.\n\nQaytadan boshlash uchun /start ni bosing.",
        reply_markup=ReplyKeyboardRemove(),
    )


# ---------------------------------------------------------------------------
# START
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()

    if str(message.from_user.id) in ADMINS:
        await message.answer("👋 Salom, Admin!", reply_markup=admin_key)
        return

    student = await get_student(message.from_user.id)

    if student["exists"]:
        # Barcha ma'lumotlar to'ldirilganmi? (math_score faqat "Ball oralig'i bo'yicha"
        # strategiyali kurslarda so'raladi, shuning uchun to'liqlik mezoni sifatida
        # math_score o'rniga "kurs tanlangani" ishlatiladi)
        has_extra = all([
            student.get("viloyat"),
            student.get("tuman"),
            student.get("phone"),
            student.get("registered_course_id") is not None,
        ])
        if has_extra:
            groups = student.get("groups", [])
            if groups:
                g_text = "\n".join(f"   • {g['name']}" for g in groups)
                await message.answer(
                    f"👋 Xush kelibsiz, {student['full_name']}!\n\n"
                    f"👥 Guruhlar:\n{g_text}\n\n"
                    f"📝 Vazifa yuborish uchun pastdagi tugmalardan foydalaning.",
                    reply_markup=await build_vazifa_keyboard(message.from_user.id),
                )
            else:
                # Ro'yxatdan o'tgan, lekin guruh yo'q — qayta urinib ko'ramiz
                # (masalan, avval mos guruh bo'lmagan, admin keyin guruh qo'shgan bo'lishi mumkin)
                score = student.get("math_score")
                course_id = student.get("registered_course_id")
                role = student.get("role")

                group = await find_available_group(course_id, score=score, role=role)

                if role:
                    role_label = "Talaba" if role == "student" else "O'qituvchi"
                    detail_line = f"🎓 Rol: {role_label}\n"
                elif score is not None:
                    detail_line = f"📊 Ball: {score}/35\n"
                else:
                    detail_line = ""

                if group:
                    # Avtomatik guruhga biriktirish
                    def _assign_group():
                        close_old_connections()
                        s = Student.objects.get(telegram_id=str(message.from_user.id))
                        g = Group.objects.get(id=group["id"])
                        s.groups.add(g)

                    await asyncio.to_thread(_assign_group)

                    await message.answer(
                        f"👋 Xush kelibsiz, {student['full_name']}!\n\n"
                        f"✅ Siz <b>{group['name']}</b> guruhiga biriktirilgiz!\n\n"
                        f"🔗 Guruh havolasi:\n{group['invite_link']}\n\n"
                        f"📝 Vazifa yuborish uchun pastdagi tugmalardan foydalaning.",
                        parse_mode="HTML",
                        reply_markup=await build_vazifa_keyboard(message.from_user.id),
                    )

                    # Adminga xabar
                    from data.config import ADMINS as ADMIN_IDS
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(
                                int(admin_id),
                                f"✅ <b>Avtomatik guruhga biriktirildi</b>\n\n"
                                f"👤 {student['full_name']} (<code>{message.from_user.id}</code>)\n"
                                f"{detail_line}"
                                f"👥 Guruh: <b>{group['name']}</b>",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                else:
                    # Mos guruh yo'q — admin hal qiladi
                    await message.answer(
                        f"👋 Xush kelibsiz, {student['full_name']}!\n\n"
                        f"⚠️ Sizga mos bo'sh guruh topilmadi.\n\n"
                        f"📞 Iltimos, admin bilan bog'laning:\n"
                        f"{ADMIN_CONTACT}",
                        parse_mode="HTML",
                        reply_markup=ReplyKeyboardRemove(),
                    )

                    from data.config import ADMINS as ADMIN_IDS
                    for admin_id in ADMIN_IDS:
                        try:
                            await bot.send_message(
                                int(admin_id),
                                f"🔔 <b>Guruhsiz student</b>\n\n"
                                f"👤 {student['full_name']} (<code>{message.from_user.id}</code>)\n"
                                f"{detail_line}"
                                f"❌ Mos bo'sh guruh topilmadi\n\n"
                                f"➕ 👥 Guruhlarni boshqarish (yoki Django admin) orqali qo'lda biriktiring.",
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
            return

        # Mavjud user, lekin qo'shimcha ma'lumotlar to'ldirilmagan
        await state.update_data(
            full_name=student["full_name"],
            is_existing=True,
        )
        await message.answer(
            f"👋 Xush kelibsiz, {student['full_name']}!\n\n"
            "Bir necha qo'shimcha ma'lumot kerak.",
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )
        await _ask_course(message, state)
        return

    # Yangi user — to'liq forma
    await message.answer(
        "👋 Assalomu alaykum!\n\n"
        "Ro'yxatdan o'tish uchun bir necha savol beramiz.\n\n"
        "📝 <b>To'liq ismingizni kiriting:</b>\n"
        "<i>Masalan: Karimov Jasur Aliyevich</i>",
        parse_mode="HTML",
        reply_markup=cancel_key,
    )
    await RegisterState.full_name.set()


# ---------------------------------------------------------------------------
# 1-QADAM: F.I.Sh
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), state=RegisterState.full_name)
async def step_full_name(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return

    name = message.text.strip()
    if len(name) < 5:
        await message.answer("❌ Ism juda qisqa. Iltimos, to'liq F.I.Sh kiriting:")
        return
    if len(name) > 100:
        await message.answer("❌ Ism juda uzun. Qaytadan kiriting:")
        return

    await state.update_data(full_name=name)
    await message.answer("✅ Yaxshi!", reply_markup=ReplyKeyboardRemove())
    await _ask_course(message, state)


# ---------------------------------------------------------------------------
# 2-QADAM: Viloyat (inline callback)
# ---------------------------------------------------------------------------

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("vil:"), state=RegisterState.viloyat)
async def step_viloyat(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    value = callback.data[4:]

    if value == "back":
        # yangi user → ismga qayt, mavjud user → bu yo'lga kelmaydi
        data = await state.get_data()
        if data.get("is_existing"):
            await callback.message.edit_text("❌ Bekor qilindi.")
            await state.finish()
        else:
            await callback.message.edit_text(
                "📝 <b>To'liq ismingizni kiriting:</b>",
                parse_mode="HTML",
            )
            await RegisterState.full_name.set()
        return

    await state.update_data(viloyat=value)
    await callback.message.edit_text(
        f"✅ Viloyat: <b>{value}</b>\n\n🏘 <b>Tumaning/shahringizni tanlang:</b>",
        parse_mode="HTML",
        reply_markup=tuman_keyboard(value),
    )
    await RegisterState.tuman.set()


# ---------------------------------------------------------------------------
# 3-QADAM: Tuman (inline callback)
# ---------------------------------------------------------------------------

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("tum:"), state=RegisterState.tuman)
async def step_tuman(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    tuman = callback.data[4:]
    data = await state.get_data()

    await state.update_data(tuman=tuman)
    await callback.message.edit_text(
        f"✅ Viloyat: <b>{data['viloyat']}</b>\n"
        f"✅ Tuman: <b>{tuman}</b>\n\n"
        f"📱 <b>Telefon raqamingizni yuboring:</b>",
        parse_mode="HTML",
    )
    await callback.message.answer(
        "👇 Tugmani bosing yoki raqamni qo'lda kiriting (+998XXXXXXXXX):",
        reply_markup=phone_keyboard(),
    )
    await RegisterState.phone.set()


@dp.callback_query_handler(lambda c: c.data == "vil:back", state=RegisterState.tuman)
async def step_tuman_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.edit_text(
        "🗺 <b>Viloyatingizni tanlang:</b>",
        parse_mode="HTML",
        reply_markup=viloyat_keyboard(),
    )
    await RegisterState.viloyat.set()


# ---------------------------------------------------------------------------
# 4-QADAM: Telefon raqam
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), content_types=types.ContentType.CONTACT, state=RegisterState.phone)
async def step_phone_contact(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    await state.update_data(phone=phone)
    await _after_phone(message, state)


@dp.message_handler(IsPrivate(), state=RegisterState.phone)
async def step_phone_text(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return

    phone = message.text.strip()
    if not _is_valid_phone(phone):
        await message.answer(
            "❌ Noto'g'ri format. Iltimos, +998XXXXXXXXX ko'rinishida kiriting:"
        )
        return

    await state.update_data(phone=phone)
    await _after_phone(message, state)


def _is_valid_phone(phone: str) -> bool:
    import re
    return bool(re.match(r"^\+?998\d{9}$", phone.replace(" ", "").replace("-", "")))


async def _after_phone(message: types.Message, state: FSMContext):
    """
    Telefondan keyingi qadam kurs strategiyasiga bog'liq:
      - role:        "Talaba/O'qituvchi" so'raladi
      - score_range: matematika balli so'raladi
      - capacity:    hech narsa so'ralmaydi, to'g'ridan-to'g'ri guruh qidiriladi
    """
    from base_app.models import Course

    data = await state.get_data()
    course = await sync_to_async(Course.objects.get)(id=data["course_id"])
    strategy = course.registration_strategy

    if strategy == 'role':
        await message.answer("✅ Telefon raqam saqlandi!", reply_markup=ReplyKeyboardRemove())
        await message.answer("🧑‍🎓 <b>Siz kimsiz?</b>", parse_mode="HTML", reply_markup=role_keyboard())
        await RegisterState.role.set()
    elif strategy == 'score_range':
        await message.answer(
            "✅ Telefon raqam saqlandi!\n\n"
            "📊 <b>Oxirgi attestatsiya imtihonida matematika qismidan "
            "nechta to'g'ri javob topgansiz?</b>\n\n"
            "Jami 35 ta savol. <b>Faqat raqam kiriting (1–35):</b>",
            parse_mode="HTML",
            reply_markup=cancel_key,
        )
        await RegisterState.math_score.set()
    else:  # capacity
        await message.answer("✅ Telefon raqam saqlandi!", reply_markup=ReplyKeyboardRemove())
        await _finalize_registration(message, message.from_user.id, state)


# ---------------------------------------------------------------------------
# 5-QADAM: Math score → guruh tanlash
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), state=RegisterState.math_score)
async def step_math_score(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer("❌ Bekor qilindi.", reply_markup=ReplyKeyboardRemove())
        return

    text = message.text.strip()
    if not text.isdigit():
        await message.answer("❌ Faqat raqam kiriting (1–35):")
        return

    score = int(text)
    if not (1 <= score <= 35):
        await message.answer("❌ Raqam 1 dan 35 gacha bo'lishi kerak:")
        return

    await _finalize_registration(message, message.from_user.id, state, score=score)


# ---------------------------------------------------------------------------
# PROFIL
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), Text(equals="👤 Profil"), state="*")
async def show_profile(message: types.Message, state: FSMContext):
    try:
        await state.finish()
    except Exception:
        pass

    student = await get_student(message.from_user.id)
    if not student["exists"]:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
        return

    groups = student.get("groups", [])
    g_text = "\n".join(f"   • {g['name']}" for g in groups) if groups else "Guruh biriktirilmagan"

    text = (
        f"📋 <b>Profil</b>\n\n"
        f"👤 <b>Ism:</b> {student['full_name']}\n"
        f"🗺 <b>Viloyat:</b> {student['viloyat'] or '—'}\n"
        f"🏘 <b>Tuman:</b> {student['tuman'] or '—'}\n"
        f"📱 <b>Telefon:</b> {student['phone'] or '—'}\n"
        f"📊 <b>Math ball:</b> {student['math_score'] if student['math_score'] is not None else '—'}/35\n\n"
        f"👥 <b>Guruhlar:</b>\n{g_text}"
    )

    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("✏️ Ismni o'zgartirish", callback_data="change_name"))

    await message.answer(text, parse_mode="HTML", reply_markup=kb)


@dp.callback_query_handler(Text(equals="change_name"), state="*")
async def request_name_change(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await callback.message.answer(
        "✏️ Yangi ism familiyangizni kiriting:\n"
        "(Misol: Karimov Jasur)\n\nBekor qilish uchun /start ni bosing."
    )
    await RegisterState.change_name.set()


@dp.message_handler(IsPrivate(), state=RegisterState.change_name)
async def process_name_change(message: types.Message, state: FSMContext):
    new_name = message.text.strip()
    if len(new_name) < 3:
        await message.answer("❌ Ism juda qisqa. Qaytadan kiriting:")
        return
    if len(new_name) > 100:
        await message.answer("❌ Ism juda uzun. Qaytadan kiriting:")
        return

    telegram_id = message.from_user.id

    def _update():
        close_old_connections()
        Student.objects.filter(telegram_id=str(telegram_id)).update(full_name=new_name)

    await asyncio.to_thread(_update)

    keyboard = admin_key if str(telegram_id) in ADMINS else await build_vazifa_keyboard(telegram_id)
    await message.answer(
        f"✅ Ismingiz o'zgartirildi!\n\n👤 Yangi ism: {new_name}",
        reply_markup=keyboard,
    )
    await state.finish()


# ---------------------------------------------------------------------------
# NATIJALARIM
# ---------------------------------------------------------------------------

@dp.message_handler(IsPrivate(), Text(equals="📊 Natijalarim"), state="*")
async def show_results(message: types.Message, state: FSMContext):
    import aiohttp
    from data.config import API_BASE_URL

    try:
        await state.finish()
    except Exception:
        pass

    telegram_id = message.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{telegram_id}/results/") as resp:
            if resp.status == 404:
                err = await resp.json()
                if "no groups" in err.get("error", "").lower():
                    await message.answer(
                        "⚠️ Sizga guruh biriktirilmagan.\n\n"
                        f"📞 Admin bilan bog'laning: {ADMIN_CONTACT}"
                    )
                else:
                    await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            elif resp.status != 200:
                await message.answer("❌ Ma'lumot olishda xatolik. Qayta urinib ko'ring.")
                return
            data = await resp.json()

    full_name = data.get("full_name", "N/A")
    results = data.get("results", [])

    if not results:
        await message.answer(f"👤 {full_name}\n\n📊 Natijalar hali yo'q")
        return

    lines = (
        "<b>📊 NATIJALARIM</b>\n\n"
        f"<b>👤 {full_name}</b>\n\n"
        "<pre>"
        "┌────────────────────────────┬──────┐\n"
        "│ Mavzu                      │ Ball │\n"
        "├────────────────────────────┼──────┤\n"
    )
    for r in results:
        title = r.get("topic_title", "N/A")[:25]
        grade = r.get("grade", 0)
        lines += f"│ {title:<26} │ {grade:>4} │\n"
    lines += "└────────────────────────────┴──────┘</pre>"

    await message.answer(lines, parse_mode="HTML")
