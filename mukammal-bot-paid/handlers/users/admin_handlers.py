"""
Admin-specific handlers: topic management, grading
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message
from states.broadcast_state import BroadcastState
from filters.is_private import IsPrivate


# --- Baho qo'yish ---
@dp.callback_query_handler(lambda c: c.data.startswith("grade_"))
async def set_grade(callback: types.CallbackQuery):
    # Only admins are allowed to grade
    if str(callback.from_user.id) not in ADMINS:
        await callback.answer("❌ Sizda baho qo'yish huquqi yo'q.", show_alert=True)
        return
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


@dp.message_handler(IsPrivate(), commands=["topics"], user_id=ADMINS)
async def show_all_topics(message: types.Message):
    import html
    from base_app.models import Topic
    topics = await sync_to_async(list)(Topic.objects.all())

    if not topics:
        await message.answer("❌ Hozircha mavzular mavjud emas.")
        return

    # ✨ YANGI: Course_type bo'yicha grouping
    milliy_sert_topics = [t for t in topics if t.course_type == 'milliy_sert']
    attestatsiya_topics = [t for t in topics if t.course_type == 'attestatsiya']
    
    text = "📌 Barcha mavzular:\n\n"
    
    if milliy_sert_topics:
        text += "🔹 <b>Milliy Sertifikat</b>:\n"
        for t in milliy_sert_topics:
            status = "✅ Active" if t.is_active else "❌ Inactive"
            title = html.escape(t.title)
            text += f"  <b>{t.id}.</b> {title} — {status}\n"
        text += "\n"
    
    if attestatsiya_topics:
        text += "🔹 <b>Attestatsiya</b>:\n"
        for t in attestatsiya_topics:
            status = "✅ Active" if t.is_active else "❌ Inactive"
            title = html.escape(t.title)
            text += f"  <b>{t.id}.</b> {title} — {status}\n"
        text += "\n"

    text += "🔹 Biror mavzuni active qilish uchun: <code>/activate &lt;id&gt;</code>"

    await message.answer(text, parse_mode="HTML")


@dp.message_handler(IsPrivate(), commands=["activate"])
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


# --- Barcha userlarga xabar yuborish ---
@dp.message_handler(IsPrivate(), commands=["broadcast"], user_id=ADMINS)
async def start_broadcast(message: types.Message):
    """Admin barcha userlarga xabar yuborish uchun"""
    await message.answer(
        "📢 Barcha userlarga yubormoqchi bo'lgan xabaringizni yuboring:\n\n"
        "⚠️ Xabar matn, rasm, video yoki hujjat bo'lishi mumkin.\n"
        "Bekor qilish uchun: /cancel"
    )
    await BroadcastState.message.set()


@dp.message_handler(IsPrivate(), state=BroadcastState.message, user_id=ADMINS, content_types=types.ContentTypes.ANY)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    """Broadcast xabarini qabul qilish va yuborish"""
    from base_app.models import Student
    
    # Barcha studentlarni olish
    students = await sync_to_async(list)(Student.objects.all())
    
    if not students:
        await message.answer("❌ Hech qanday student topilmadi.")
        try:
            await state.finish()
        except KeyError:
            pass
        return
    
    await message.answer(f"📤 Xabar {len(students)} ta userga yuborilmoqda...")
    
    success_count = 0
    fail_count = 0
    
    for student in students:
        try:
            # Message turini aniqlash va copy qilish
            await message.copy_to(student.telegram_id)
            success_count += 1
        except Exception as e:
            fail_count += 1
            print(f"Failed to send to {student.telegram_id}: {e}")
    
    # Natijani ko'rsatish
    result_text = (
        f"✅ Xabar yuborish tugadi!\n\n"
        f"📊 Natija:\n"
        f"✅ Muvaffaqiyatli: {success_count}\n"
        f"❌ Xato: {fail_count}\n"
        f"📝 Jami: {len(students)}"
    )
    
    await message.answer(result_text)
    try:
        await state.finish()
    except KeyError:
        pass


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
