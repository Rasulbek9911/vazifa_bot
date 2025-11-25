from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
# RegisterState removed - registration now handled in user_registration.py
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message

# Global umumiy guruh linki
GENERAL_GROUP_INVITE_LINK = None
GENERAL_GROUP_ID = "-1003295943458"


# NOTE: /start and registration handlers moved to user_registration.py
# This file only contains task submission and scheduled functions


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
        GENERAL_GROUP_ID = "-1003295943458"
        
        # Guruhlarga qo'shilganligini tekshirish
        group_not_joined = False
        general_not_joined = False
        
        # O'z guruhiga qo'shilganmi tekshirish
        if group_obj and group_obj.get("telegram_group_id"):
            try:
                group_member = await bot.get_chat_member(group_obj.get("telegram_group_id"), telegram_id)
                if group_member.status in ["left", "kicked"]:
                    group_not_joined = True
            except Exception as e:
                # Guruhni tekshira olmasa, link beramiz (bot admin emas)
                print(f"⚠️ O'z guruhini tekshirib bo'lmadi (bot admin emasligidan): {e}")
                # Guruh linki bormi tekshirish, agar bor bo'lsa beramiz
                group_not_joined = bool(group_obj.get("invite_link"))
        else:
            # telegram_group_id bo'sh bo'lsa, link bermaslik
            group_not_joined = False
            
        # Umumiy guruh uchun tekshiruvni qayta yoqish
        try:
            # Umumiy guruhga qo'shilganmi
            general_member = await bot.get_chat_member(GENERAL_GROUP_ID, telegram_id)
            if general_member.status in ["left", "kicked"]:
                general_not_joined = True
        except Exception as e:
            # Umumiy guruhga qo'shilmagan
            print(f"⚠️ Umumiy guruhni tekshirib bo'lmadi: {e}")
            general_not_joined = True
        
        # Agar qo'shilmagan bo'lsa, yangi 1 martalik linklar yaratamiz
        if group_not_joined or general_not_joined:
            msg = "❌ Siz quyidagi guruhlarga qo'shilmagansiz:\n\n"
            
            if group_not_joined and group_obj and group_obj.get("telegram_group_id"):
                try:
                    # Avval guruh a'zolari sonini tekshiramiz
                    chat_members_count = await bot.get_chat_member_count(group_obj.get("telegram_group_id"))
                    admins = await bot.get_chat_administrators(group_obj.get("telegram_group_id"))
                    admin_count = len(admins)
                    regular_members = chat_members_count - admin_count
                    
                    print(f"📊 Guruh '{group_obj.get('name')}' statistikasi: Jami={chat_members_count}, Adminlar={admin_count}, Oddiy a'zolar={regular_members}")
                    
                    # Agar 50 dan oshgan bo'lsa, keyingi guruhni topamiz
                    if regular_members >= 50:
                        print(f"⚠️ Guruh to'lgan ({regular_members}/50), keyingi guruhni qidiryapmiz...")
                        msg += f"⚠️ Guruh '{group_obj.get('name')}' to'lgan ({regular_members}/50)!\n\n"
                        
                        # Barcha guruhlarni tekshirib, bo'sh guruhni topamiz
                        next_group = None
                        for grp in groups:
                            if grp["id"] != group_obj["id"] and grp.get("telegram_group_id"):
                                try:
                                    grp_count = await bot.get_chat_member_count(grp["telegram_group_id"])
                                    grp_admins = await bot.get_chat_administrators(grp["telegram_group_id"])
                                    grp_regular = grp_count - len(grp_admins)
                                    
                                    print(f"  Guruh '{grp['name']}': {grp_regular}/50")
                                    
                                    if grp_regular < 50:
                                        next_group = grp
                                        print(f"✅ Bo'sh guruh topildi: {grp['name']}")
                                        break
                                except Exception as e:
                                    print(f"  Guruh '{grp['name']}' tekshiruvida xatolik: {e}")
                                    continue
                        
                        if next_group:
                            # Keyingi guruhga link beramiz
                            try:
                                next_invite = await bot.create_chat_invite_link(
                                    chat_id=next_group["telegram_group_id"],
                                    member_limit=1
                                )
                                msg += f"✅ Bo'sh guruh topildi: '{next_group['name']}'\n"
                                msg += f"🔹 Yangi guruh linki: {next_invite.invite_link}\n"
                                msg += f"   (Ushbu guruhga o'tib, vazifa yuborishingiz mumkin)\n\n"
                            except Exception as e:
                                print(f"Keyingi guruh uchun link yaratishda xatolik: {e}")
                                msg += f"❌ Keyingi guruh uchun link yaratib bo'lmadi.\n\n"
                        else:
                            msg += f"❌ Barcha guruhlar to'lgan! Admin bilan bog'laning.\n\n"
                    else:
                        # Guruh to'lmagan bo'lsa, 1 martalik link yaratamiz
                        group_invite = await bot.create_chat_invite_link(
                            chat_id=group_obj.get("telegram_group_id"),
                            member_limit=1
                        )
                        msg += f"🔹 O'z guruhingiz ({regular_members}/50): {group_invite.invite_link}\n"
                except Exception as e:
                    print(f"O'z guruhi uchun link yaratishda xatolik (chat_id={group_obj.get('telegram_group_id')}): {e}")
                    if group_obj.get("invite_link"):
                        msg += f"🔹 O'z guruhingiz: {group_obj.get('invite_link')}\n"
                    else:
                        print(f"⚠️ Guruh {group_obj.get('name')} uchun zaxira link ham yo'q!")
            elif group_not_joined and group_obj:
                # telegram_group_id bo'sh, lekin eski link bor bo'lsa
                if group_obj.get("invite_link"):
                    msg += f"🔹 O'z guruhingiz: {group_obj.get('invite_link')}\n"
            
            if general_not_joined:
                try:
                    # Yangi 1 martalik link yaratish
                    general_invite = await bot.create_chat_invite_link(
                        chat_id=GENERAL_GROUP_ID,
                        member_limit=1
                    )
                    msg += f"🔹 Umumiy guruh: {general_invite.invite_link}\n"
                except Exception as e:
                    print(f"❌ XATOLIK: Umumiy guruh linki yaratib bo'lmadi (chat_id={GENERAL_GROUP_ID}): {e}")
                    msg += f"❌ Umumiy guruh linki yaratib bo'lmadi. Admin bilan bog'laning.\n"
            
            msg += "\n⚠️ Har bir link FAQAT 1 MARTA ishlatiladi!\n"
            msg += "⚠️ Iltimos, guruhlarga qo'shiling va qayta urinib ko'ring."
            
            await message.answer(msg)
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
                # 404 yoki xatolik bo'lsa, guruhga hech narsa yubormaymiz
                    

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


