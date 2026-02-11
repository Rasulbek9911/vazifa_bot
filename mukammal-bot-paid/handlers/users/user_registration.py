"""
User registration flow: start command, full name processing
No invite code required - direct registration
Single group with approval link (200 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
import asyncio
import logging
import os
import sys
import django

# Django setup
sys.path.insert(0, '/var/www/vazifa_bot')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from base_app.models import Group, Student
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key, admin_key, cancel_key
from filters.is_private import IsPrivate
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# Helper functions for database access
async def fetch_groups_from_db():
    """Database'dan barcha guruhlarni olish"""
    try:
        groups = await asyncio.to_thread(
            lambda: list(Group.objects.filter(telegram_group_id__isnull=False).values(
                'id', 'name', 'telegram_group_id', 'invite_link', 'is_full', 'course_type'
            ))
        )
        return groups
    except Exception as e:
        logging.error(f"Error fetching groups from database: {e}")
        return []


async def fetch_student_from_db(telegram_id):
    """Database'dan student ma'lumotlarini olish"""
    try:
        def get_student():
            try:
                student = Student.objects.prefetch_related('groups').get(telegram_id=str(telegram_id))
                groups_data = [{'id': g.id, 'name': g.name} for g in student.groups.all()]
                return {
                    'exists': True,
                    'full_name': student.full_name,
                    'telegram_id': student.telegram_id,
                    'all_groups': groups_data
                }
            except Student.DoesNotExist:
                return {'exists': False}
        
        return await asyncio.to_thread(get_student)
    except Exception as e:
        logging.error(f"Error fetching student from database: {e}")
        return {'exists': False}


async def register_student_to_db(telegram_id, full_name, group_id):
    """Student'ni database'ga yozish"""
    try:
        def do_register():
            student, created = Student.objects.get_or_create(
                telegram_id=str(telegram_id),
                defaults={'full_name': full_name}
            )
            if not created:
                student.full_name = full_name
                student.save()
            
            group = Group.objects.get(id=group_id)
            student.groups.add(group)
            return True
        
        return await asyncio.to_thread(do_register)
    except Exception as e:
        logging.error(f"Error registering student to database: {e}")
        return False


# --- CANCEL HANDLER ---
@dp.message_handler(IsPrivate(), Text(equals="❌ Bekor qilish", ignore_case=True), state="*")
async def cancel_registration(message: types.Message, state: FSMContext):
    """Ro'yxatdan o'tishni bekor qilish"""
    current_state = await state.get_state()
    if current_state is None:
        return
    
    await state.finish()
    await message.answer(
        "❌ Ro'yxatdan o'tish bekor qilindi.\n\n"
        "Qaytadan boshlash uchun /start ni bosing.",
        reply_markup=types.ReplyKeyboardRemove()
    )


# --- START - Direct Registration (No Invite Code) ---
@dp.message_handler(IsPrivate(), commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start - to'g'ridan-to'g'ri ro'yxatdan o'tish (invite code yo'q)
    """
    # Admin bo'lsa, to'g'ridan-to'g'ri admin panel ko'rsatamiz
    if str(message.from_user.id) in ADMINS:
        await message.answer(
            "👋 Salom, Admin!\n\n"
            "Admin funksiyalaridan foydalanishingiz mumkin.",
            reply_markup=admin_key
        )
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
        return
    
    # Avval har qanday holatda bo'lsa ham, pending_registration ni tekshiramiz
    try:
        data = await state.get_data()
        has_pending = data.get("pending_registration")
        
        # Agar pending_registration yo'q bo'lsa, har qanday boshqa stateni tozalaymiz
        if not has_pending:
            try:
                await state.finish()
            except (KeyError, Exception):
                pass
        
        if has_pending:
            # User link olgan, guruhga qo'shilganini tekshiramiz
            user_id = data.get("user_id")
            full_name = data.get("full_name")
            group_id = data.get("group_id")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/groups/") as resp:
                    groups = await resp.json()
                
                group_obj = next((g for g in groups if g["id"] == group_id), None)
                
                if group_obj and group_obj.get("telegram_group_id"):
                    try:
                        member = await bot.get_chat_member(
                            group_obj.get("telegram_group_id"), 
                            user_id
                        )
                        
                        # Agar guruhga qo'shilgan bo'lsa, DBga yozamiz
                        if member.status in ["member", "administrator", "creator"]:
                            payload = {
                                "telegram_id": str(user_id),
                                "full_name": full_name,
                                "group_id": group_id
                            }
                            
                            async with aiohttp.ClientSession() as session2:
                                async with session2.post(f"{API_BASE_URL}/students/register/", json=payload) as resp2:
                                    if resp2.status == 201:
                                        # Admin yoki oddiy user ekanligini tekshiramiz
                                        keyboard = admin_key if str(user_id) in ADMINS else vazifa_key
                                        await message.answer(
                                            f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n"
                                            f"👥 Guruh: {data.get('group_name')}\n\n"
                                            f"Endi vazifa yuborishingiz mumkin.",
                                            reply_markup=keyboard
                                        )
                                        try:
                                            await state.finish()
                                        except (KeyError, Exception):
                                            pass
                                        return
                                    elif resp2.status == 400:
                                        error_data = await resp2.json()
                                        error_msg = error_data.get("error", "Ro'yxatdan o'tishda xatolik bo'ldi")
                                        
                                        # Agar user allaqachon ro'yxatdan o'tgan bo'lsa
                                        if "allaqachon ro'yxatdan o'tgan" in error_msg.lower() or "already exists" in error_msg.lower():
                                            keyboard = admin_key if str(user_id) in ADMINS else vazifa_key
                                            await message.answer(
                                                f"✅ Siz allaqachon ro'yxatdan o'tgansiz!\n\n"
                                                f"👥 Guruh: {data.get('group_name')}\n\n"
                                                f"Endi vazifa yuborishingiz mumkin.",
                                                reply_markup=keyboard
                                            )
                                        else:
                                            await message.answer(f"⚠️ {error_msg}")
                                        
                                        try:
                                            await state.finish()
                                        except (KeyError, Exception):
                                            pass
                                        return
                                       
                    except Exception as e:
                        # Agar bot chat membershipni tekshira olmasa (masalan, bot admin emas)
                        # DBda user borligini tekshiramiz
                        async with aiohttp.ClientSession() as check_session:
                            async with check_session.get(f"{API_BASE_URL}/students/{user_id}/") as check_resp:
                                if check_resp.status == 200:
                                    # User allaqachon DBda bor
                                    student_info = await check_resp.json()
                                    keyboard = admin_key if str(user_id) in ADMINS else vazifa_key
                                    
                                    # Barcha guruhlarni ko'rsatish
                                    all_groups_info = student_info.get('all_groups', [])
                                    if all_groups_info:
                                        groups_text = "\n".join([f"   • {g['name']}" for g in all_groups_info])
                                        await message.answer(
                                            f"✅ Siz allaqachon ro'yxatdan o'tgansiz!\n\n"
                                            f"👥 Guruhlar:\n{groups_text}\n\n"
                                            f"Endi vazifa yuborishingiz mumkin.",
                                            reply_markup=keyboard
                                        )
                                    else:
                                        await message.answer(
                                            f"✅ Siz allaqachon ro'yxatdan o'tgansiz!\n\n"
                                            f"Endi vazifa yuborishingiz mumkin.",
                                            reply_markup=keyboard
                                        )
                                    try:
                                        await state.finish()
                                    except (KeyError, Exception):
                                        pass
                                    return
            
            # Agar hali qo'shilmagan bo'lsa, eslatma beramiz
            await message.answer(
                "⚠️ Siz hali guruhga qo'shilmagansiz!\n\n"
                "Avval guruh linkini bosib qo'shiling, keyin /start ni qayta bosing."
            )
            # State ni tozalaymiz, chunki guruhga qo'shilmagan
            try:
                await state.finish()
            except (KeyError, Exception):
                pass
            return
    except Exception as e:
        # Pending registration tekshirishda xatolik bo'lsa, logga yozamiz va davom etamiz
        logging.error(f"Error checking pending_registration for user {message.from_user.id}: {e}")
        # State ni tozalaymiz va oddiy ro'yxatdan o'tishga o'tamiz
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
    
    # Student allaqachon ro'yxatdan o'tganmi tekshiramiz (to'g'ridan-to'g'ri DB'dan)
    try:
        student_data = await fetch_student_from_db(message.from_user.id)
        
        if student_data.get('exists'):
            # User allaqachon ro'yxatdan o'tgan
            full_name = student_data.get('full_name')
            telegram_id = message.from_user.id
            
            # Ro'yxatdan o'tgan user - darhol keyboard bilan javob beramiz
            keyboard = admin_key if str(telegram_id) in ADMINS else vazifa_key
            
            all_groups_data = student_data.get("all_groups", [])
            if all_groups_data:
                groups_text = "\n".join([f"   • {g['name']}" for g in all_groups_data])
                
                await message.answer(
                    f"👋 Xush kelibsiz, {full_name}!\n\n"
                    f"👥 Guruhlar:\n{groups_text}\n\n"
                    f"📝 Vazifa yuborish uchun pastdagi tugmalardan foydalaning.",
                    reply_markup=keyboard
                )
            else:
                await message.answer(
                    f"👋 Xush kelibsiz, {full_name}!\n\n"
                    f"📝 Vazifa yuborish uchun pastdagi tugmalardan foydalaning.",
                    reply_markup=keyboard
                )
            return
        else:
            # User DBda yo'q - telegram guruhlarini tekshiramiz
            groups = await fetch_groups_from_db()
            
            if not groups:
                # Hech qanday guruh topilmadi
                logging.error(f"No groups found in database for user {message.from_user.id}")
                await message.answer(
                    "⚠️ Hozircha guruhlar mavjud emas.\n\n"
                    "Iltimos, keyinroq qayta urinib ko'ring yoki admin bilan bog'laning."
                )
                return
            
            # ⚡ Faqat telegram_group_id bor guruhlarni tekshirish
            groups_with_telegram = [g for g in groups if g.get("telegram_group_id")]
            
            async def check_new_user_membership(grp):
                """
                Yangi user uchun guruhga qo'shilganligini tekshirish.
                
                IMPORTANT: Agar user allaqachon telegram guruhida bo'lsa,
                guruh to'lganligini tekshirmaymiz va to'g'ridan-to'g'ri
                ro'yxatdan o'tish jarayoniga o'tkazamiz.
                Chunki user allaqachon guruhga qo'shilgan!
                """
                try:
                    member = await bot.get_chat_member(grp["telegram_group_id"], message.from_user.id)
                    if member.status in ["member", "administrator", "creator"]:
                        return {"id": grp["id"], "name": grp["name"]}
                except Exception:
                    pass
                return None
            
            # Parallel tekshirish (faqat telegram_group_id bor guruhlar)
            if groups_with_telegram:
                check_tasks = [check_new_user_membership(grp) for grp in groups_with_telegram]
                results = await asyncio.gather(*check_tasks)
                user_joined_groups = [grp for grp in results if grp is not None]
            else:
                user_joined_groups = []
            
            # ✅ User allaqachon telegram guruhida bo'lsa:
            # Guruh to'lganligini TEKSHIRMAYMIZ va to'g'ridan-to'g'ri ro'yxatdan o'tkazamiz
            # Sabab: User allaqachon guruhga qo'shilgan, joy olgan!
            if user_joined_groups:
                await message.answer(
                    "👋 Salom! Siz guruhda ko'rinasiz, lekin ro'yxatdan o'tmagansiz.\n\n"
                    "📝 Iltimos, to'liq ismingizni kiriting:\n"
                    "Masalan: <b>Fayziyev Aslbek Ismoil o'g'li</b>",
                    parse_mode="HTML",
                    reply_markup=cancel_key
                )
                # Barcha guruh ma'lumotlarini state ga saqlaymiz
                # Capacity check QILINMAYDI - user allaqachon telegram guruhida!
                await state.update_data(
                    auto_register_multi=True,
                    user_joined_groups=user_joined_groups
                )
                await RegisterState.full_name.set()
                return
    except Exception as e:
        # Database xatoliklari uchun
        logging.error(f"Database error in /start handler for user {message.from_user.id}: {e}")
        await message.answer(
            "⚠️ Ma'lumotlar bazasi bilan bog'lanishda xatolik yuz berdi.\n\n"
            "Iltimos, biroz kutib qaytadan /start buyrug'ini yuboring."
        )
        return
    
    # ⚠️ User hech qanday telegram guruhida YO'Q!
    # Bunday holatda user admin bilan bog'lanishi kerak
    # Bot avtomatik guruh link bermaydi
    await message.answer(
        "⚠️ Siz hech qanday guruhda yo'qsiz!\n\n"
        "📞 Ro'yxatdan o'tish uchun admin bilan bog'laning.\n"
        "Admin sizni kerakli guruhga qo'shadi.\n\n"
        "Guruhga qo'shilgandan so'ng /start ni qayta bosing va "
        "avtomatik ro'yxatdan o'tib, vazifa yuborishingiz mumkin bo'ladi.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    return


# F.I.Sh qabul qilish va ro'yxatdan o'tkazish
@dp.message_handler(IsPrivate(), state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    """F.I.Sh qabul qilish va avtomatik ro'yxatdan o'tkazish"""
    # Bekor qilish tugmasi bosilgan bo'lsa
    if message.text == "❌ Bekor qilish":
        await state.finish()
        await message.answer(
            "❌ Ro'yxatdan o'tish bekor qilindi.\n\n"
            "Qaytadan boshlash uchun /start ni bosing.",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return
    
    # Admin bo'lsa, ro'yxatdan o'tkazmaymiz
    if str(message.from_user.id) in ADMINS:
        await message.answer(
            "❌ Admin sifatida siz ro'yxatdan o'tishingiz shart emas.",
            reply_markup=admin_key
        )
        await state.finish()
        return
    
    await state.update_data(full_name=message.text)
    data = await state.get_data()
    
    # ✅ User telegram guruhida mavjud bo'lsa - to'g'ridan-to'g'ri ro'yxatdan o'tkazamiz
    # Capacity check QILINMAGAN, chunki user allaqachon telegram guruhida!
    if data.get("auto_register_multi"):
        user_joined_groups = data.get("user_joined_groups", [])
        
        if not user_joined_groups:
            await message.answer("❌ Siz hech qanday guruhda yo'qsiz!")
            await state.finish()
            return
        
        # Barchasiga ro'yxatdan o'tkazamiz (database'ga)
        # MUHIM: Guruh to'lganligini tekshirmaymiz, user allaqachon guruhda!
        try:
            for grp in user_joined_groups:
                await register_student_to_db(
                    telegram_id=message.from_user.id,
                    full_name=message.text,
                    group_id=grp["id"]
                )
            
            groups_text = "\n".join([f"   • {g['name']}" for g in user_joined_groups])
            await message.answer(
                f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n"
                f"👥 Guruhlar:\n{groups_text}\n\n"
                f"Endi vazifa yuborishingiz mumkin.",
                reply_markup=vazifa_key
            )
            await state.finish()
            return
        except Exception as e:
            logging.error(f"Database error during multi-group registration for user {message.from_user.id}: {e}")
            await message.answer(
                "⚠️ Ro'yxatdan o'tishda xatolik yuz berdi.\n\n"
                "Iltimos, qayta urinib ko'ring yoki admin bilan bog'laning."
            )
            await state.finish()
            return
    
    # Eski logika: Agar user allaqachon guruhda bo'lsa (auto_register=True), to'g'ridan-to'g'ri DBga yozamiz
    if data.get("auto_register"):
        group_id = data.get("group_id")
        group_name = data.get("group_name")
        
        try:
            await register_student_to_db(
                telegram_id=message.from_user.id,
                full_name=message.text,
                group_id=group_id
            )
            await message.answer(
                f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n"
                f"👥 Guruh: {group_name}\n\n"
                f"Endi vazifa yuborishingiz mumkin.",
                reply_markup=vazifa_key
            )
        except Exception as e:
            logging.error(f"Database error during registration for user {message.from_user.id}: {e}")
            await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
        
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
        return
    
    # ⚠️ IMPORTANT: Bu yerga hech qachon yetib kelmaslik kerak!
    # Chunki user guruhda bo'lmasa, /start handlerda to'xtatilgan bo'ladi.
    # Agar bu yerga yetib kelindi bo'lsa - bu xatolik!
    logging.error(f"Unexpected state in process_fish for user {message.from_user.id}: no auto_register flags set!")
    await message.answer(
        "❌ Xatolik yuz berdi!\n\n"
        "Iltimos, /start ni qayta bosing yoki admin bilan bog'laning."
    )
    try:
        await state.finish()
    except (KeyError, Exception):
        pass


# --- PROFILE HANDLER - View and Change Name ---
@dp.message_handler(IsPrivate(), Text(equals="👤 Profil"), state="*")
async def show_profile(message: types.Message, state: FSMContext):
    """Show user profile and option to change name"""
    telegram_id = message.from_user.id
    
    # Stateni tozalash
    try:
        await state.finish()
    except (KeyError, Exception):
        pass
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{telegram_id}/") as resp:
            if resp.status != 200:
                await message.answer("❌ Siz ro'yxatdan o'tmagansiz. /start ni bosing.")
                return
            
            student_data = await resp.json()
            full_name = student_data.get("full_name", "N/A")
            
            # ✨ YANGI: Barcha guruhlarni ko'rsatish
            all_groups = student_data.get("all_groups", [])
            
            if not all_groups:
                await message.answer("❌ Sizga guruh biriktirilmagan!")
                return
            
            # Guruhlar va kurslarni formatlash
            groups_text = ""
            for idx, grp in enumerate(all_groups, 1):
                group_name = grp.get("name", "N/A")
                course_type = grp.get("course_type", "N/A")
                course_display = "Milliy sertifikat" if course_type == "milliy_sert" else "Attestatsiya"
                groups_text += f"   {idx}. {group_name} ({course_display})\n"
            
            # Profile ma'lumotlarini ko'rsatish
            profile_text = (
                f"📋 <b>Profil ma'lumotlari</b>\n\n"
                f"👤 <b>Ism:</b> {full_name}\n"
                f"👥 <b>Guruhlar:</b>\n{groups_text}\n"
                f"Ismingizni o'zgartirish uchun pastdagi tugmani bosing."
            )
            
            # Inline keyboard for name change
            keyboard = InlineKeyboardMarkup(row_width=1)
            keyboard.add(
                InlineKeyboardButton(text="✏️ Ismni o'zgartirish", callback_data="change_name")
            )
            
            await message.answer(profile_text, parse_mode="HTML", reply_markup=keyboard)


@dp.callback_query_handler(Text(equals="change_name"), state="*")
async def request_name_change(callback: types.CallbackQuery, state: FSMContext):
    """Request new name from user"""
    await callback.answer()
    
    await callback.message.answer(
        "✏️ Yangi ism familiyangizni kiriting:\n"
        "(Misol: Fayziyev Aslbek)\n\n"
        "Bekor qilish uchun /start ni bosing."
    )
    
    await RegisterState.change_name.set()


@dp.message_handler(IsPrivate(), state=RegisterState.change_name)
async def process_name_change(message: types.Message, state: FSMContext):
    """Process the new name and update in database"""
    new_name = message.text.strip()
    telegram_id = message.from_user.id
    
    # Validate name
    if len(new_name) < 3:
        await message.answer("❌ Ism juda qisqa. Qaytadan kiriting:")
        return
    
    if len(new_name) > 100:
        await message.answer("❌ Ism juda uzun. Qaytadan kiriting:")
        return
    
    # Update name in database
    async with aiohttp.ClientSession() as session:
        payload = {"full_name": new_name}
        async with session.patch(f"{API_BASE_URL}/students/{telegram_id}/update_name/", json=payload) as resp:
            if resp.status == 200:
                keyboard = admin_key if str(telegram_id) in ADMINS else vazifa_key
                await message.answer(
                    f"✅ Ismingiz muvaffaqiyatli o'zgartirildi!\n\n"
                    f"👤 Yangi ism: {new_name}\n\n"
                    f"Davom etish uchun /start ni bosing.",
                    reply_markup=keyboard
                )
                await state.finish()
            else:
                error_data = await resp.json() if resp.content_type == 'application/json' else {}
                error_msg = error_data.get("error", "Ismni o'zgartirishda xatolik yuz berdi")
                await message.answer(f"❌ {error_msg}")
                await state.finish()
