from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from states.task_state import TaskState
from keyboards.default.vazifa_keyboard import vazifa_key
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message

# Global umumiy guruh linki (bir marta yaratiladi)
GENERAL_GROUP_INVITE_LINK = None
GENERAL_GROUP_ID = "-1003295943458"


# --- START with Invite Code ---
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start yoki /start abc12345 (invite code bilan deep linking)
    """
    # Avval state ni tozalaymiz
    current_state = await state.get_state()
    if current_state:
        try:
            await state.finish()
        except Exception as e:
            pass
        
    
    # Deep linking - invite code bilan kelganmi?
    args = message.get_args()
    
    # Admin bo'lsa, invite code so'ramaslik
    if str(message.from_user.id) in ADMINS:
        await message.answer(
            f"👋 Admin salom!\n\n"
            f"Buyruqlar:\n"
            f"/generate_invite - Yangi invite code yaratish\n\n"
            f"Invite code yaratganingizdan so'ng, uni foydalanuvchilarga yuboring."
        )
        return
    
    # Student allaqachon ro'yxatdan o'tganmi tekshiramiz
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro'yxatdan o'tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return
    
    # Agar invite code bilan kelgan bo'lsa
    if args:
        # Deep linking - validatsiya keyinroq (process_fish da)
        await state.update_data(invite_code=args, validated=False)
        await message.answer(
            "Assalomu alaykum! 👋\n\n"
            f"Invite code qabul qilindi: <code>{args}</code>\n\n"
            "Endi ro'yxatdan o'tish uchun F.I.Sh kiriting:",
            parse_mode="HTML"
        )
        await RegisterState.full_name.set()
    else:
        # Invite code yo'q - so'raymiz
        await message.answer(
            "Assalomu alaykum! 👋\n\n"
            "Ro'yxatdan o'tish uchun invite code kiriting:\n\n"
            "💡 Invite code yo'qmi? Admin bilan bog'laning."
        )
        await RegisterState.invite_code.set()


# Invite code qabul qilish (agar deep linking bo'lmasa)
@dp.message_handler(state=RegisterState.invite_code)
async def process_invite_code(message: types.Message, state: FSMContext):
    invite_code = message.text.strip()
    
    # Invite code ni tekshirish
    async with aiohttp.ClientSession() as session:
        payload = {
            "code": invite_code,
            "user_id": str(message.from_user.id)
        }
        async with session.post(f"{API_BASE_URL}/invites/validate/", json=payload) as resp:
            if resp.status == 200:
                await state.update_data(invite_code=invite_code, validated=True)
                await message.answer(
                    "✅ Invite code qabul qilindi!\n\n"
                    "Endi F.I.Sh kiriting:"
                )
                await RegisterState.full_name.set()
            else:
                error_data = await resp.json()
                error_msg = error_data.get("error", "Noto'g'ri invite code")
                await message.answer(
                    f"❌ {error_msg}\n\n"
                    "Iltimos, qaytadan to'g'ri invite code kiriting:"
                )
                return


# F.I.Sh qabul qilish
@dp.message_handler(state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    
    # Invite code mavjudligini tekshiramiz
    data = await state.get_data()
    invite_code = data.get("invite_code")
    
    if not invite_code:
        await message.answer("❌ Xatolik: Invite code topilmadi. Iltimos, /start dan qayta boshlang.")
        try:
            await state.finish()
        except Exception:
            pass
        return
    
    # Invite code ni validatsiya qilamiz (agar deep linking bo'lsa)
    if "invite_code" in data and not data.get("validated"):
        async with aiohttp.ClientSession() as session:
            payload = {
                "code": invite_code,
                "user_id": str(message.from_user.id)
            }
            async with session.post(f"{API_BASE_URL}/invites/validate/", json=payload) as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", "Noto'g'ri invite code")
                    await message.answer(
                        f"❌ {error_msg}\n\n"
                        "Iltimos, /start dan qayta boshlang."
                    )
                    try:
                        await state.finish()
                    except Exception:
                        pass
                    return
                await state.update_data(validated=True)

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
    full_name = data["full_name"]
    payload = {
        "telegram_id": str(message.from_user.id),
        "full_name": full_name,
        "group_id": selected_group
    }

    # Guruh linkini yaratish - har bir user uchun unique, 1 martalik
    group_obj = next((g for g in groups if g["id"] == selected_group), None)
    
    # O'z guruhi uchun unique invite link yaratish
    group_invite_link = None
    if group_obj and group_obj.get("telegram_group_id"):
        try:
            # 1 martalik invite link yaratish (member_limit=1)
            print(f"Guruh uchun invite link yaratilmoqda (chat_id={group_obj.get('telegram_group_id')})...")
            group_chat_invite = await bot.create_chat_invite_link(
                chat_id=group_obj.get("telegram_group_id"),
                member_limit=1  # Faqat 1 kishi qo'shilishi mumkin
            )
            group_invite_link = group_chat_invite.invite_link
        except Exception as e:
            print(f"Guruh invite link yaratishda xatolik (chat_id={group_obj.get('telegram_group_id')}): {e}")
            # Agar xatolik bo'lsa, eski linkni ishlatamiz
            group_invite_link = group_obj.get("invite_link")
    elif group_obj:
        # telegram_group_id bo'sh bo'lsa, eski linkni ishlatamiz
        group_invite_link = group_obj.get("invite_link")
        if not group_invite_link:
            print(f"⚠️ Guruh {group_obj.get('name')} uchun telegram_group_id va invite_link yo'q!")
    
    # Umumiy guruh uchun ham 1 martalik link yaratish
    umumiy_invite_link = None
    GENERAL_GROUP_ID = "-1003295943458"
    try:
        # 1 martalik invite link yaratish (member_limit=1)
        general_chat_invite = await bot.create_chat_invite_link(
            chat_id=GENERAL_GROUP_ID,
            member_limit=1  # Faqat 1 kishi qo'shilishi mumkin
        )
        print(general_chat_invite.invite_link)
        umumiy_invite_link = general_chat_invite.invite_link
    except Exception as e:
        print(f"❌ XATOLIK: Umumiy guruh uchun link yaratib bo'lmadi (chat_id={GENERAL_GROUP_ID}): {e}")
        # Link yaratib bo'lmasa, userni xabardor qilamiz
        await message.answer(
            "❌ Umumiy guruh linki yaratishda xatolik yuz berdi.\n"
            "Admin bilan bog'laning."
        )
        try:
            await state.finish()
        except Exception:
            pass
        return
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro'yxatdan o'tdingiz! Sizning guruh - {group_name}.\n\n"
                msg += "📚 Quyidagi guruhlarga HOZIR qo'shiling:\n"
                if group_invite_link:
                    msg += f"🔹 O'z guruhingiz: {group_invite_link}\n"
                if umumiy_invite_link:
                    msg += f"🔹 Umumiy guruh: {umumiy_invite_link}\n\n"
                msg += "⚠️ HAR BIR LINK FAQAT 1 MARTA ISHLATILADI!\n"
                msg += "⚠️ Linklar tez eskiradi - DARHOL bosing!\n"
                msg += "⚠️ Vazifa yuborishdan oldin IKKALA guruhga ham qo'shilishingiz shart!"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass


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
                    # Yangi 1 martalik link yaratish
                    group_invite = await bot.create_chat_invite_link(
                        chat_id=group_obj.get("telegram_group_id"),
                        member_limit=1
                    )
                    msg += f"🔹 O'z guruhingiz: {group_invite.invite_link}\n"
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


