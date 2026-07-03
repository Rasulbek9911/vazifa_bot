"""
Reyting (tanga) handler: 🏆 Reyting tugmasi
"""
import aiohttp
from aiogram import types
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from asgiref.sync import sync_to_async
from filters.is_private import IsPrivate


MEDAL = {1: "🥇", 2: "🥈", 3: "🥉"}


def _build_leaderboard_text(data: dict, course_name: str) -> str:
    top10 = data.get("top10", [])
    my_rank = data.get("my_rank")
    my_coins = data.get("my_coins", 0)
    my_streak = data.get("my_streak", 0)
    my_longest = data.get("my_longest_streak", 0)

    lines = [f"🏆 <b>Reyting — {course_name}</b>\n"]

    if not top10:
        lines.append("Hozircha hech kim tanga to'plamagan.")
    else:
        for e in top10:
            medal = MEDAL.get(e["rank"], f"{e['rank']}.")
            lines.append(
                f"{medal} {e['full_name']} — "
                f"<b>{e['total_coins']}</b> 🪙  "
                f"🔥{e['current_streak']}"
            )

    lines.append("")
    if my_rank is not None:
        lines.append(
            f"📍 Sizning o'rningiz: <b>{my_rank}</b>\n"
            f"💰 Tangalaringiz: <b>{my_coins}</b> 🪙\n"
            f"🔥 Joriy streak: <b>{my_streak}</b>  |  Rekord: <b>{my_longest}</b>"
        )
    elif my_coins > 0:
        lines.append(
            f"💰 Sizning tangalaringiz: <b>{my_coins}</b> 🪙\n"
            f"🔥 Joriy streak: <b>{my_streak}</b>  |  Rekord: <b>{my_longest}</b>"
        )

    return "\n".join(lines)


@dp.message_handler(IsPrivate(), lambda msg: msg.text == "🏆 Reyting")
async def show_rating_menu(message: types.Message):
    telegram_id = message.from_user.id

    # Adminlar uchun boshqacha yo'nalish
    if str(telegram_id) in ADMINS:
        await _show_admin_rating_menu(message)
        return

    # Student kurslarini olish
    from base_app.models import Student
    try:
        student = await sync_to_async(Student.objects.select_related().get)(telegram_id=str(telegram_id))
    except Exception:
        await message.answer("❌ Siz ro'yxatdan o'tmagansiz!")
        return

    @sync_to_async
    def get_courses(st):
        courses = {}
        for grp in st.groups.select_related('course').all():
            if grp.course and grp.course.is_active:
                courses[grp.course.id] = grp.course.name
        return courses

    courses = await get_courses(student)

    if not courses:
        await message.answer(
            "⚠️ Sizga faol kurs biriktirilmagan.\n\n"
            "📞 Admin bilan bog'laning: @A_Fayziev"
        )
        return

    if len(courses) == 1:
        course_id, course_name = next(iter(courses.items()))
        await _send_leaderboard(message, course_id, course_name, str(telegram_id))
    else:
        kb = types.InlineKeyboardMarkup()
        for cid, cname in courses.items():
            kb.add(types.InlineKeyboardButton(
                text=f"📚 {cname}",
                callback_data=f"rating_course_{cid}"
            ))
        await message.answer("📚 Qaysi kurs reytingini ko'rmoqchisiz?", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("rating_course_"))
async def rating_course_selected(callback: types.CallbackQuery):
    course_id = int(callback.data.split("_")[2])
    telegram_id = str(callback.from_user.id)

    from base_app.models import Course
    try:
        course = await sync_to_async(Course.objects.get)(id=course_id)
        course_name = course.name
    except Exception:
        await callback.answer("❌ Kurs topilmadi", show_alert=True)
        return

    await callback.answer()
    await _send_leaderboard(callback.message, course_id, course_name, telegram_id, edit=True)


async def _send_leaderboard(message, course_id, course_name, telegram_id, edit=False):
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE_URL}/coins/leaderboard/?course_id={course_id}&telegram_id={telegram_id}"
        async with session.get(url) as resp:
            if resp.status != 200:
                await message.answer("❌ Reyting ma'lumotlarini olishda xatolik!")
                return
            data = await resp.json()

    text = _build_leaderboard_text(data, course_name)
    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML")
        except Exception:
            await message.answer(text, parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# ── Tangalarim ────────────────────────────────────────────────────────────

@dp.message_handler(IsPrivate(), lambda msg: msg.text == "🪙 Tangalarim")
async def show_my_coins(message: types.Message):
    telegram_id = str(message.from_user.id)

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/coins/my/?telegram_id={telegram_id}") as resp:
            if resp.status == 404:
                await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            elif resp.status != 200:
                await message.answer("❌ Ma'lumot olishda xatolik.")
                return
            data = await resp.json()

    wallets = data.get("wallets", [])
    full_name = data.get("full_name", "")

    if not wallets:
        await message.answer(
            "🪙 Hali tanga to'planmagan.\n\n"
            "Vazifa topshirganingizda avtomatik tanga beriladi!"
        )
        return

    lines = [f"🪙 <b>Tangalarim — {full_name}</b>\n"]

    # Har bir kurs uchun rank ham olamiz
    async with aiohttp.ClientSession() as session:
        for w in wallets:
            url = f"{API_BASE_URL}/coins/leaderboard/?course_id={w['course_id']}&telegram_id={telegram_id}"
            async with session.get(url) as resp2:
                lb = await resp2.json() if resp2.status == 200 else {}

            my_rank = lb.get("my_rank")
            rank_text = f"#{my_rank}" if my_rank else "600+"

            streak_bar = "🔥" * min(w["current_streak"], 10)
            if w["current_streak"] > 10:
                streak_bar += f"+{w['current_streak'] - 10}"

            lines.append(
                f"📚 <b>{w['course_name']}</b>\n"
                f"  💰 Jami: <b>{w['total_coins']}</b> 🪙\n"
                f"  🔥 Streak: <b>{w['current_streak']}</b>  |  Rekord: <b>{w['longest_streak']}</b>\n"
                f"  {streak_bar}\n"
                f"  📍 Reyting o'rni: <b>{rank_text}</b>"
            )

    await message.answer("\n\n".join(lines), parse_mode="HTML")


# ── Admin reyting menyusi ──────────────────────────────────────────────────

async def _show_admin_rating_menu(message: types.Message):
    from base_app.models import Course
    courses = await sync_to_async(list)(Course.objects.filter(is_active=True))

    kb = types.InlineKeyboardMarkup()
    for c in courses:
        kb.add(types.InlineKeyboardButton(
            text=f"📚 {c.name}",
            callback_data=f"adm_rating_course_{c.id}"
        ))
    await message.answer("📊 Admin reyting — kursni tanlang:", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data.startswith("adm_rating_course_"), user_id=ADMINS)
async def adm_rating_course(callback: types.CallbackQuery):
    course_id = int(callback.data.split("_")[3])

    from base_app.models import Course
    try:
        course = await sync_to_async(Course.objects.get)(id=course_id)
    except Exception:
        await callback.answer("❌ Kurs topilmadi", show_alert=True)
        return

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🪙 Tanga bo'yicha", callback_data=f"adm_top_coins_{course_id}"),
        types.InlineKeyboardButton("🔥 Streak bo'yicha", callback_data=f"adm_top_streak_{course_id}"),
    )
    kb.add(
        types.InlineKeyboardButton(
            "📅 Davr bo'yicha filter",
            callback_data=f"adm_top_period_{course_id}"
        )
    )
    await callback.message.edit_text(
        f"📚 <b>{course.name}</b> — saralash turini tanlang:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("adm_top_coins_"), user_id=ADMINS)
async def adm_top_coins(callback: types.CallbackQuery):
    course_id = int(callback.data.split("_")[3])
    await callback.answer("⏳ Yuklanmoqda...")
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE_URL}/coins/admin-leaderboard/?course_id={course_id}&sort=coins"
        async with session.get(url) as resp:
            data = await resp.json()
    await _send_admin_top(callback.message, data, "🪙 Tanga bo'yicha Top 50", edit=True)


@dp.callback_query_handler(lambda c: c.data.startswith("adm_top_streak_"), user_id=ADMINS)
async def adm_top_streak(callback: types.CallbackQuery):
    course_id = int(callback.data.split("_")[3])
    await callback.answer("⏳ Yuklanmoqda...")
    async with aiohttp.ClientSession() as session:
        url = f"{API_BASE_URL}/coins/admin-leaderboard/?course_id={course_id}&sort=streak"
        async with session.get(url) as resp:
            data = await resp.json()
    await _send_admin_top(callback.message, data, "🔥 Streak bo'yicha Top 50", edit=True)


@dp.callback_query_handler(lambda c: c.data.startswith("adm_top_period_"), user_id=ADMINS)
async def adm_top_period_start(callback: types.CallbackQuery):
    from aiogram.dispatcher import FSMContext
    course_id = int(callback.data.split("_")[3])
    from states.admin_rating_state import AdminRatingState
    state = dp.current_state(user=callback.from_user.id, chat=callback.message.chat.id)
    await state.update_data(rating_course_id=course_id)
    await state.set_state(AdminRatingState.waiting_period)
    await callback.message.answer(
        "📅 Davr kiriting (format: <code>YYYY-MM-DD YYYY-MM-DD</code>)\n"
        "Misol: <code>2026-04-01 2026-05-06</code>\n\n"
        "❌ Bekor qilish: /cancel",
        parse_mode="HTML"
    )
    await callback.answer()


@dp.message_handler(IsPrivate(), state="AdminRatingState:waiting_period", user_id=ADMINS)
async def adm_top_period_filter(message: types.Message, state: FSMContext):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("❌ Format: <code>YYYY-MM-DD YYYY-MM-DD</code>", parse_mode="HTML")
        return

    from_date, to_date = parts
    data = await state.get_data()
    course_id = data.get('rating_course_id')

    async with aiohttp.ClientSession() as session:
        url = (
            f"{API_BASE_URL}/coins/admin-leaderboard/"
            f"?course_id={course_id}&sort=coins&from={from_date}&to={to_date}"
        )
        async with session.get(url) as resp:
            if resp.status != 200:
                await message.answer("❌ Ma'lumot olishda xatolik!")
                await state.finish()
                return
            result = await resp.json()

    await _send_admin_top(
        message, result,
        f"📅 {from_date} — {to_date} davri | 🪙 Top 50"
    )
    await state.finish()


async def _send_admin_top(message, data: dict, title: str, edit=False):
    results = data.get("results", [])
    sort_by = data.get("sort_by", "coins")

    lines = [f"<b>{title}</b>\n"]
    if not results:
        lines.append("Ma'lumot topilmadi.")
    else:
        for e in results:
            medal = MEDAL.get(e["rank"], f"{e['rank']}.")
            if sort_by == "streak":
                lines.append(
                    f"{medal} {e['full_name']} — "
                    f"🔥 rekord: <b>{e['longest_streak']}</b>  "
                    f"(joriy: {e['current_streak']})  "
                    f"💰 {e['total_coins']} 🪙"
                )
            else:
                period_coins = e.get("period_coins", e.get("total_coins", 0))
                lines.append(
                    f"{medal} {e['full_name']} — "
                    f"<b>{period_coins}</b> 🪙  "
                    f"🔥{e.get('max_streak_in_period', e.get('longest_streak', 0))}"
                )

    text = "\n".join(lines)

    # Telegram xabar uzunligi cheki uchun bo'lib yuboramiz
    if len(text) > 4000:
        text = text[:4000] + "\n..."

    if edit:
        try:
            await message.edit_text(text, parse_mode="HTML")
            return
        except Exception:
            pass
    await message.answer(text, parse_mode="HTML")
