from aiogram import types
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp,bot
from aiogram.dispatcher.filters import Text
from aiogram.utils import executor
from states.register_state import RegisterState
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message



# --- START ---
@dp.message_handler(commands=["start"], state="*")
async def cmd_start_all_states(message: types.Message, state: FSMContext):
    """Student allaqachon ro'yxatdan o'tganmi tekshiramiz"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro‘yxatdan o‘tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return

    # Agar topilmasa ro‘yxatdan o‘tadi
    await message.answer("Assalomu alaykum! Ro‘yxatdan o‘tish uchun F.I.Sh kiriting:")
    await RegisterState.full_name.set()

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message, state: FSMContext):
    """Student allaqachon ro'yxatdan o'tganmi tekshiramiz"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro‘yxatdan o‘tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return

    # Agar topilmasa ro‘yxatdan o‘tadi
    await message.answer("Assalomu alaykum! Ro‘yxatdan o‘tish uchun F.I.Sh kiriting:")
    await RegisterState.full_name.set()

# F.I.Sh qabul qilish
@dp.message_handler(state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)

    # Guruhlarni va ularning a'zolar sonini olish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()

        # Har bir guruh uchun a'zolar sonini tekshiramiz
        selected_group = None
        for g in groups:
            group_id = g["id"]
            async with session.get(f"{API_BASE_URL}/students/?group_id={group_id}") as resp2:
                students_in_group = await resp2.json()
                if len(students_in_group) < 50:
                    selected_group = group_id
                    break

    if selected_group is None:
        await message.answer("❌ Hech bir guruhda bo'sh joy yo'q. Admin bilan bog'laning.")
        try:
            await state.finish()
        except Exception as e:
            pass
        return

    # Avtomatik tanlangan guruhga ro'yxatdan o'tkazamiz
    data = await state.get_data()
    full_name = data["full_name"]
    payload = {
        "telegram_id": str(message.from_user.id),
        "full_name": full_name,
        "group_id": selected_group
    }

    # Guruh linkini olish (guruh obyektidan)
    group_obj = next((g for g in groups if g["id"] == selected_group), None)
    group_link = group_obj.get("invite_link") if group_obj else None
    umumiy_link = "https://t.me/+yIsZnSKlj9lmMTEy"  # umumiy guruh linki
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro‘yxatdan o‘tdingiz! Sizning guruh - {group_name}. Guruhga qo'shilib oling. Endi vazifalarni yuborishingiz mumkin 👇"
                if group_link:
                    msg += f"\n\nGuruhga qo'shilish uchun link: {group_link}"
                    msg += f"\n\nUmumiy guruhga qo'shilish uchun link: {umumiy_link}"
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro‘yxatdan o‘tishda xatolik bo‘ldi.")
    try:
        await state.finish()
    except Exception as e:
        pass


# Guruh tanlash
@dp.callback_query_handler(lambda c: c.data.startswith("group_"), state=RegisterState.group)
async def process_group(callback: types.CallbackQuery, state: FSMContext):
    group_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    full_name = data["full_name"]

    payload = {
        "telegram_id": str(callback.from_user.id),
        "full_name": full_name,
        "group_id": group_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                await callback.message.answer(
                    "✅ Ro‘yxatdan o‘tdingiz!\nEndi vazifalarni yuborishingiz mumkin 👇",
                    reply_markup=vazifa_key
                )
            else:
                await callback.message.answer("❌ Ro‘yxatdan o‘tishda xatolik bo‘ldi.")
    await state.finish()
    await callback.answer()


# --- Vazifa yuborish ---
@dp.message_handler(Text(equals="📤 Vazifa yuborish"))
async def send_task(message: types.Message):
    telegram_id = message.from_user.id

    # Studentni tekshirish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{telegram_id}/") as resp:
            if resp.status != 200:
                await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            student_data = await resp.json()
            group_id = student_data.get("group", {}).get("id")
            
        # Guruh ma'lumotlarini olish
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
            
        group_obj = next((g for g in groups if g["id"] == group_id), None)
        group_link = group_obj.get("invite_link") if group_obj else None
        umumiy_link = "https://t.me/+yIsZnSKlj9lmMTEy"
        
        # Guruhlarga qo'shilganligini tekshirish
        try:
            # O'z guruhiga qo'shilganmi
            group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
            if group_member.status in ["left", "kicked"]:
                await message.answer(
                    f"❌ Siz o'z guruhingizga qo'shilmagansiz!\n\n"
                    f"Guruhga qo'shilish uchun: {group_link}"
                )
                return
        except Exception as e:
            # Guruh ID mavjud emas yoki boshqa xatolik
            pass
            
        try:
            # Umumiy guruhga qo'shilganmi (bu yerda umumiy guruh chat_id ni qo'ying)
            GENERAL_GROUP_ID = "-1002319099734"  # Umumiy guruh ID sini bu yerga qo'ying
            general_member = await bot.get_chat_member(GENERAL_GROUP_ID, telegram_id)
            if general_member.status in ["left", "kicked"]:
                await message.answer(
                    f"❌ Siz umumiy guruhga qo'shilmagansiz!\n\n"
                    f"Umumiy guruhga qo'shilish uchun: {umumiy_link}"
                )
                return
        except Exception as e:
            # Umumiy guruhga qo'shilmagan
            await message.answer(
                f"❌ Siz umumiy guruhga qo'shilmagansiz!\n\n"
                f"Umumiy guruhga qo'shilish uchun: {umumiy_link}"
            )
            return

    async with aiohttp.ClientSession() as session:
        # 1️⃣ Barcha mavzular
        async with session.get(f"{API_BASE_URL}/topics/") as resp:
            topics = await resp.json()

        # 2️⃣ Student yuborgan vazifalar
        async with session.get(f"{API_BASE_URL}/tasks/?student_id={telegram_id}") as resp:
            submitted_tasks = await resp.json()

    submitted_topic_ids = {task["topic"]["id"] for task in submitted_tasks}

    # 3️⃣ Faqat yubormagan mavzularni filter qilamiz
    available_topics = [t for t in topics if t["id"] not in submitted_topic_ids]

    if not available_topics:
        await message.answer("✅ Siz barcha mavzular uchun vazifa yuborgansiz!")
        return

    kb = types.InlineKeyboardMarkup()
    for t in available_topics:
        kb.add(types.InlineKeyboardButton(
            text=t["title"], callback_data=f"topic_{t['id']}"
        ))

    await message.answer("📚 Mavzuni tanlang:", reply_markup=kb)
    await TaskState.topic.set()
    

@dp.callback_query_handler(lambda c: c.data.startswith("topic_"), state=TaskState.topic)
async def process_topic(callback: types.CallbackQuery, state: FSMContext):
    topic_id = int(callback.data.split("_")[1])
    await state.update_data(topic_id=topic_id)
    await callback.message.answer("📎 Endi faylni yuboring (rasm yoki hujjat).")
    await TaskState.file.set()
    await callback.answer()


@dp.message_handler(content_types=["document", "photo"], state=TaskState.file)
async def process_file(message: types.Message, state: FSMContext):
    data = await state.get_data()
    topic_id = data["topic_id"]

    if message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        file_id = message.photo[-1].file_id
        file_type = "photo"

    payload = {
        "student_id": message.from_user.id,  # telegram_id
        "topic_id": topic_id,
        "file_link": file_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/tasks/submit/", json=payload) as resp:
            if resp.status == 201:
                data = await resp.json()
                task_id = data["id"]
                student_name = data["student"]["full_name"]
                group_name = data["student"]["group"]["name"]
                topic_title = data["topic"]["title"]

                # ✅ Studenta javob
                await message.answer("✅ Vazifangiz yuborildi!", reply_markup=vazifa_key)

                # ✅ Admin uchun inline keyboard
                kb = InlineKeyboardMarkup(row_width=3)
                kb.add(
                    InlineKeyboardButton("3️⃣", callback_data=f"grade_{task_id}_3"),
                    InlineKeyboardButton("4️⃣", callback_data=f"grade_{task_id}_4"),
                    InlineKeyboardButton("5️⃣", callback_data=f"grade_{task_id}_5"),
                )

                caption = (
                    f"📥 Yangi vazifa!\n\n"
                    f"👤 Student: {student_name}\n"
                    f"👥 Guruh: {group_name}\n"
                    f"📚 Mavzu: {topic_title}\n"
                )

    
                if file_type == "document":
                    await bot.send_document(ADMINS[0], file_id, caption=caption, reply_markup=kb)
                else:
                    await bot.send_photo(ADMINS[0], file_id, caption=caption, reply_markup=kb)

            else:
                await message.answer("❌ Vazifa yuborishda xatolik bo‘ldi.")

    await state.finish()
    
    

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
                    print("❌ Caption o‘zgartirishda xato:", e)

                await callback.answer("✅ Baho qo‘yildi", show_alert=True)

            else:
                await callback.answer("❌ Xatolik yuz berdi", show_alert=True)

# --- Haftalik report ---
async def send_weekly_reports():
    async with aiohttp.ClientSession() as session:
        # Guruhlarni olib kelamiz
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
        for g in groups:
            chat_id = g.get("telegram_group_id")
            group_id = g["id"]

            if not chat_id:
                continue  # telegram_group_id yo‘q bo‘lsa tashlab ketamiz

            # PDF reportni olib kelamiz
            async with session.get(f"{API_BASE_URL}/reports/{group_id}/weekly/pdf/") as resp:
                if resp.status == 200:
                    pdf_bytes = await resp.read()
                    await bot.send_document(
                        chat_id,
                        ("weekly_report.pdf", pdf_bytes),
                        caption=f"📊 {g['name']} guruhining haftalik hisobot"
                    )
                else:
                    await bot.send_message(chat_id, "❌ Reportni olishda xatolik yuz berdi")
                    

#--- Vazifa topshirmaganlarga eslatma ---
async def send_unsubmitted_warnings():
    from base_app.models import Student, Topic, Task
    active_topics = await sync_to_async(list)(Topic.objects.filter(is_active=True))
    students = await sync_to_async(list)(Student.objects.all())

    for student in students:
        submitted = await sync_to_async(list)(
            Task.objects.filter(student=student, topic__in=active_topics)
        )
        submitted_topic_ids = [t.topic_id for t in submitted]

        unsubmitted = [t for t in active_topics if t.id not in submitted_topic_ids]

        if unsubmitted:
            msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo‘yicha vazifa topshirmagansiz!\n"
            msg += "\n".join([f"- {t.title}" for t in unsubmitted])
            await safe_send_message(student.telegram_id, msg)

            if len(unsubmitted) >= 3:
                admin_msg = f"🚨 {student.full_name} {len(unsubmitted)} ta vazifa topshirmagan."
                admin_msg += f"\nTelegram ID: <code>{student.telegram_id}</code>"
                admin_msg += f"\nMavzular:\n" + "\n".join([f"- {t.title}" for t in unsubmitted])

                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(
                    text="Chatga o'tish",
                    url=f"tg://user?id={student.telegram_id}"
                ))

                await bot.send_message(
                    ADMINS[0],
                    admin_msg,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
from asgiref.sync import sync_to_async


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


