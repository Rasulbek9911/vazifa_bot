"""
Admin-specific handlers: topic management, grading
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL, MILLIY_ADMIN, ATTESTATSIYA_ADMIN
from loader import dp, bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message
from states.broadcast_state import BroadcastState
from states.update_answers_state import UpdateAnswersState
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

    # ✨ Course bo'yicha grouping (backward compatibility bilan)
    def get_course_code(topic):
        if topic.course:
            return topic.course.code
        return topic.course_type or "attestatsiya"
    
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

    # Topic kursini aniqlaymiz (backward compatibility)
    if topic.course:
        topic_course_code = topic.course.code
        topic_course_name = topic.course.name
    else:
        topic_course_code = topic.course_type or "attestatsiya"
        topic_course_name = "Milliy Sertifikat" if topic_course_code == "milliy_sert" else "Attestatsiya"

    await message.answer(
        f"✅ <b>{topic.title}</b> mavzu <b>Active</b> qilindi!\n"
        f"📚 Kurs: {topic_course_name}\n"
        f"👥 Faqat {topic_course_name} kursidagi studentlarga xabar yuboriladi.",
        parse_mode="HTML"
    )

    # 👥 Faqat o'sha kursdagi studentlarga xabar yuboramiz
    students = await sync_to_async(list)(Student.objects.prefetch_related('groups', 'group__course').all())
    
    notify_text = f"📚 Yangi mavzu active qilindi:\n<b>{topic.title}</b>\n\n" \
                  "📤 Vazifani yuborishingiz mumkin!"
    
    notified_count = 0
    for student in students:
        # ✨ YANGI: Student barcha guruhlarini tekshiramiz
        all_groups = await sync_to_async(student.get_all_groups)()
        
        for grp in all_groups:
            if grp.course:
                student_course_code = grp.course.code
            else:
                student_course_code = grp.course_type or "attestatsiya"
            
            # Faqat o'sha kursdagi studentlarga yuboramiz
            if student_course_code == topic_course_code:
                await safe_send_message(student.telegram_id, notify_text)
                notified_count += 1
                break  # Bitta marta yuborish yetarli
    
    await message.answer(f"✅ {notified_count} ta studentga xabar yuborildi.", parse_mode="HTML")


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
    if re.match(r'^[abcd]+$', current_answers):
        # Format 1: faqat harflar (abc = 3 ta)
        answer_count = len(current_answers)
    else:
        # Format 2: raqam+harf(lar) (1a2b3c = 3 ta, 1ab2x3cd = 3 ta)
        answer_count = len(re.findall(r'\d+[abcdx]+', current_answers))
    
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
    if re.match(r'^[abcd]+$', new_answers):
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
    elif re.match(r'^(\d+[abcdx]+)+$', new_answers):
        # Javoblar sonini sanab ko'ramiz
        questions = re.findall(r'\d+[abcdx]+', new_answers)
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
            "Faqat a, b, c, d, x harflaridan foydalaning.\n"
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
    if re.match(r'^[abcd]+$', new_answers):
        # Format 1: faqat harflar (abc) -> har biri bitta to'g'ri javob
        correct_answers_list = [[ch] for ch in new_answers]
    else:
        # Format 2: raqam+harf(lar) (1a2b3c yoki 1ab2x3cd)
        # Har bir savolning to'g'ri javoblarini list qilib olamiz
        correct_answers_list = []
        for match in re.finditer(r'\d+([abcdx]+)', new_answers):
            answers = match.group(1)
            if answers == 'x':
                # 'x' = hech biri to'g'ri emas
                correct_answers_list.append(['x'])
            else:
                # Ko'p variant (ab, abcd, ...)
                correct_answers_list.append(list(answers))
    
    # Barcha bu mavzu bo'yicha test topshirgan studentlarning natijasini qayta hisoblaymiz
    tasks = await sync_to_async(list)(
        Task.objects.filter(topic_id=topic_id, task_type='test', test_code=test_code).select_related('student')
    )
    
    updated_count = 0
    grade_changes = []  # Baho o'zgarishlarini saqlaymiz
    
    for task in tasks:
        # Student javoblarini parse qilish
        student_answers = task.test_answers.lower()
        student_answers_list = []
        
        if re.match(r'^[abcdx]+$', student_answers):
            # Format 1: faqat harflar (abc -> [a, b, c])
            student_answers_list = list(student_answers)
        else:
            # Format 2: raqam+harf(lar) (1a2b3c -> [a, b, c] yoki 1ab2c3d -> [ab, c, d])
            # Student bir nechta harf yozgan bo'lishi mumkin
            for match in re.finditer(r'\d+([abcdx]+)', student_answers):
                student_answers_list.append(match.group(1))
        
        # Uzunliklarni tekshirish
        if not student_answers_list or len(student_answers_list) != answer_count:
            continue
            
        # Yangi bahoni hisoblaymiz
        old_grade = task.grade
        correct_count = 0
        bekor_count = 0  # Bekor qilingan savollar soni
        
        for i in range(answer_count):
            student_ans = student_answers_list[i]
            correct_ans_list = correct_answers_list[i]
            
            # Agar admin 'x' deb belgilagan bo'lsa (savol bekor qilindi)
            if correct_ans_list == ['x']:
                # Bu savol bekor, HAMMA studentlar ball oladi
                correct_count += 1
                bekor_count += 1
            # Oddiy holat: student javobi to'g'ri javoblar ichida bormi?
            elif student_ans in correct_ans_list:
                correct_count += 1
        
        new_grade = correct_count
        
        if old_grade != new_grade:
            task.grade = new_grade
            await sync_to_async(task.save)()
            updated_count += 1
            
            # Student ma'lumotlarini olamiz (task.student allaqachon select_related bilan yuklangan)
            student_full_name = task.student.full_name
            student_telegram_id = task.student.telegram_id
            
            # Baho farqini saqlaymiz
            diff = new_grade - old_grade
            grade_changes.append({
                'student': student_full_name,
                'old': old_grade,
                'new': new_grade,
                'diff': diff
            })
            
            # Studentga xabar yuboramiz
            change_symbol = "📈" if diff > 0 else "📉"
            bekor_msg = ""
            if bekor_count > 0:
                bekor_msg = f"\n\n🎁 {bekor_count} ta savol bekor qilindi (test xatosi tuzatildi)"
            
            await safe_send_message(
                student_telegram_id,
                f"{change_symbol} Test natijangiz o'zgardi!\n\n"
                f"📚 Mavzu: {topic_title}\n"
                f"❌ Eski baho: {old_grade}/{answer_count}\n"
                f"✅ Yangi baho: {new_grade}/{answer_count}\n"
                f"{'➕' if diff > 0 else '➖'} Farq: {abs(diff)} ball"
                f"{bekor_msg}"
            )
    
    # Adminga statistika
    stats_text = f"✅ Yangilash tugadi!\n\n"
    stats_text += f"📊 Statistika:\n"
    stats_text += f"• Qayta hisoblangan testlar: {updated_count} ta\n"
    stats_text += f"• Jami baholangan testlar: {len(tasks)} ta\n\n"
    
    if grade_changes:
        stats_text += f"📋 Baho o'zgargan studentlar ({len(grade_changes)} ta):\n"
        for change in grade_changes[:10]:  # Faqat birinchi 10 tasini ko'rsatamiz
            symbol = "📈" if change['diff'] > 0 else "📉"
            stats_text += f"{symbol} {change['student']}: {change['old']} → {change['new']} ({change['diff']:+d} ball)\n"
        
        if len(grade_changes) > 10:
            stats_text += f"\n... va yana {len(grade_changes) - 10} ta student"
    
    await message.answer(stats_text)
    
    # State ni tozalaymiz
    await state.finish()
