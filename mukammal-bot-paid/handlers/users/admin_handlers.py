"""
Admin-specific handlers: invite generation, topic management, grading
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message


# --- Admin: Invite code yaratish ---
@dp.message_handler(commands=["generate_invite"], state="*")
async def generate_invite(message: types.Message, state: FSMContext):
    """Admin faqat invite code yaratishi mumkin"""
    if str(message.from_user.id) not in ADMINS:
        await message.answer("❌ Sizda bu buyruqni ishlatish huquqi yo'q.")
        return
    
    # Hozirgi state ni to'xtatish (agar admin ro'yxatdan o'tish jarayonida bo'lsa)
    current_state = await state.get_state()
    if current_state:
        try:
            await state.finish()
        except:
            pass
    
    async with aiohttp.ClientSession() as session:
        payload = {"admin_id": str(message.from_user.id)}
        async with session.post(f"{API_BASE_URL}/invites/create/", json=payload) as resp:
            if resp.status == 201:
                data = await resp.json()
                invite_code = data["code"]
                bot_username = (await bot.get_me()).username
                invite_link = f"https://t.me/{bot_username}?start={invite_code}"
                
                await message.answer(
                    f"✅ Yangi invite yaratildi!\n\n"
                    f"📝 Invite code: <code>{invite_code}</code>\n"
                    f"🔗 Bot linki: {invite_link}\n\n"
                    f"⚠️ Bu link faqat 1 marta ishlatiladi!",
                    parse_mode="HTML"
                )
            else:
                await message.answer("❌ Invite yaratishda xatolik yuz berdi.")


# --- Baho qo'yish ---
@dp.callback_query_handler(lambda c: c.data.startswith("grade_"))
async def set_grade(callback: types.CallbackQuery):
    _, task_id, grade = callback.data.split("_")
    payload = {"grade": int(grade)}

    async with aiohttp.ClientSession() as session:
        async with session.patch(f"{API_BASE_URL}/tasks/{task_id}/", json=payload) as resp:
            if resp.status == 200:
                task = await resp.json()
                student_id = task["student"]["telegram_id"]
                student_name = task["student"]["full_name"]
                group_name = task["student"]["group"]["name"]
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


@dp.message_handler(commands=["topics"])
async def show_all_topics(message: types.Message):
    import html
    from base_app.models import Topic
    topics = await sync_to_async(list)(Topic.objects.all())

    if not topics:
        await message.answer("❌ Hozircha mavzular mavjud emas.")
        return

    text = "📌 Barcha mavzular:\n\n"
    for t in topics:
        status = "✅ Active" if t.is_active else "❌ Inactive"
        title = html.escape(t.title)  # xavfli belgilarni qochirdik
        text += f"<b>{t.id}.</b> {title} — {status}\n"

    text += "\n🔹 Biror mavzuni active qilish uchun: <code>/activate &lt;id&gt;</code>"

    await message.answer(text, parse_mode="HTML")


@dp.message_handler(commands=["activate"])
async def activate_topic(message: types.Message):
    from base_app.models import Topic, Student

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
        topic = await sync_to_async(Topic.objects.get)(id=topic_id)
    except Topic.DoesNotExist:
        await message.answer("❌ Bunday ID li mavzu topilmadi.")
        return

    # ✅ is_active = True qilamiz
    topic.is_active = True
    await sync_to_async(topic.save)()

    await message.answer(
        f"✅ <b>{topic.title}</b> mavzu <b>Active</b> qilindi!\n"
        "👥 Endi barcha studentlarga xabar yuboriladi.",
        parse_mode="HTML"
    )

    # 👥 Barcha studentlarga xabar yuboramiz
    students = await sync_to_async(list)(Student.objects.all())
    notify_text = f"📚 Yangi mavzu active qilindi:\n<b>{topic.title}</b>\n\n" \
                  "📤 Vazifani yuborishingiz mumkin!"

    for student in students:
        await safe_send_message(student.telegram_id, notify_text)
