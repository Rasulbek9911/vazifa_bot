"""
User registration flow: start command, full name processing
No invite code required - direct registration
Single group with approval link (200 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key
from filters.is_private import IsPrivate


# --- START - Direct Registration (No Invite Code) ---
@dp.message_handler(IsPrivate(), commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start - to'g'ridan-to'g'ri ro'yxatdan o'tish (invite code yo'q)
    """
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
                                        await message.answer(
                                            f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n"
                                            f"👥 Guruh: {data.get('group_name')}\n\n"
                                            f"Endi vazifa yuborishingiz mumkin.",
                                            reply_markup=vazifa_key
                                        )
                                        try:
                                            await state.finish()
                                        except (KeyError, Exception):
                                            pass
                                        return
                                    elif resp2.status == 400:
                                        error_data = await resp2.json()
                                        error_msg = error_data.get("error", "Ro'yxatdan o'tishda xatolik bo'ldi")
                                        await message.answer(f"⚠️ {error_msg}")
                                        try:
                                            await state.finish()
                                        except (KeyError, Exception):
                                            pass
                                        return
                                       
                    except Exception:
                        pass
            
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
    except Exception:
        pass
    
    # Admin bo'lsa, oddiy salom xabari
    if str(message.from_user.id) in ADMINS:
        await message.answer("👋 Admin salom!")
        return
    
    # Student allaqachon ro'yxatdan o'tganmi tekshiramiz
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/students/{message.from_user.id}/") as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Guruhga qo'shilganligini ham tekshiramiz
                group_id = data.get("group", {}).get("id")
                if group_id:
                    async with session.get(f"{API_BASE_URL}/groups/") as resp_groups:
                        groups = await resp_groups.json()
                    
                    group_obj = next((g for g in groups if g["id"] == group_id), None)
                    
                    if group_obj and group_obj.get("telegram_group_id"):
                        try:
                            member = await bot.get_chat_member(
                                group_obj.get("telegram_group_id"), 
                                message.from_user.id
                            )
                            
                            # Agar guruhda bo'lsa, vazifa keyboard beramiz
                            if member.status in ["member", "administrator", "creator"]:
                                await message.answer(
                                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro'yxatdan o'tgansiz, vazifalarni yuborishingiz mumkin.",
                                    reply_markup=vazifa_key
                                )
                                return
                        except Exception:
                            pass
                
                # Agar guruhga qo'shilmagan bo'lsa, oddiy salom
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\n"
                    f"Vazifa yuborish uchun guruhga qo'shiling."
                )
                return
            elif resp.status == 404:
                # User DBda yo'q - ehtimol guruhga qo'shilgan, lekin DBga yozilmagan
                # Guruhlardan birida borligini tekshiramiz
                async with session.get(f"{API_BASE_URL}/groups/") as resp_groups:
                    groups = await resp_groups.json()
                
                for grp in groups:
                    grp_telegram_id = grp.get("telegram_group_id")
                    if grp_telegram_id:
                        try:
                            member = await bot.get_chat_member(grp_telegram_id, message.from_user.id)
                            if member.status in ["member", "administrator", "creator"]:
                                # User guruhda bor! Ism familiyasini so'raymiz
                                await message.answer(
                                    "👋 Salom! Siz guruhda ko'rinasiz, lekin ro'yxatdan o'tmagansiz.\n\n"
                                    "Ro'yxatdan o'tish uchun Ism familiyangizni kiriting:\n"
                                    "(Misol: Fayziyev Aslbek)"
                                )
                                # Guruh ma'lumotlarini state ga saqlaymiz
                                await state.update_data(
                                    auto_register=True,
                                    group_id=grp["id"],
                                    group_name=grp["name"]
                                )
                                await RegisterState.full_name.set()
                                return
                        except Exception:
                            continue
    
    # Ro'yxatdan o'tish jarayonini boshlash
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Ro'yxatdan o'tish uchun Ism familiyangizni kiriting: \n(Misol: Fayziyev Aslbek)"
    )
    await RegisterState.full_name.set()


# F.I.Sh qabul qilish va ro'yxatdan o'tkazish
@dp.message_handler(IsPrivate(), state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    """F.I.Sh qabul qilish va avtomatik ro'yxatdan o'tkazish"""
    await state.update_data(full_name=message.text)
    data = await state.get_data()
    
    # Agar user allaqachon guruhda bo'lsa (auto_register=True), to'g'ridan-to'g'ri DBga yozamiz
    if data.get("auto_register"):
        group_id = data.get("group_id")
        group_name = data.get("group_name")
        
        payload = {
            "telegram_id": str(message.from_user.id),
            "full_name": message.text,
            "group_id": group_id
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
                if resp.status == 201:
                    await message.answer(
                        f"✅ Ro'yxatdan muvaffaqiyatli o'tdingiz!\n\n"
                        f"👥 Guruh: {group_name}\n\n"
                        f"Endi vazifa yuborishingiz mumkin.",
                        reply_markup=vazifa_key
                    )
                elif resp.status == 400:
                    error_data = await resp.json()
                    error_msg = error_data.get("error", "Ro'yxatdan o'tishda xatolik bo'ldi")
                    await message.answer(f"⚠️ {error_msg}")
                else:
                    await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
        
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
        return
    
    # Barcha guruhlarni olish va bo'sh guruhni topish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
        
        if not groups:
            await message.answer("❌ Guruh topilmadi. Admin bilan bog'laning.")
            try:
                await state.finish()
            except (KeyError, Exception):
                pass
            return
        
        # ✨ YANGI: Faqat milliy_sert kurs turidagi va is_full=False guruhlarni ID bo'yicha tartiblash
        # Course_type='milliy_sert' va is_full=False, eng kichik ID dan boshlab to'ldirish
        all_available_groups = [g for g in groups if not g.get('is_full') and g.get('course_type') == 'milliy_sert']
        all_available_groups.sort(key=lambda x: x['id'])
        
        if not all_available_groups:
            await message.answer(
                "❌ Barcha Milliy Sertifikat guruhlari to'lgan!\n\n"
                "Admin bilan bog'laning."
            )
            try:
                await state.finish()
            except (KeyError, Exception):
                pass
            return
        
        # Birinchi bo'sh guruhni topish (ketma-ket to'ldirish)
        selected_group = None
        group_obj = None
        min_member_count = 0
        
        for grp in all_available_groups:
            grp_id = grp["id"]
            grp_telegram_id = grp.get("telegram_group_id")
            
            if not grp_telegram_id:
                continue  # Telegram ID bo'lmasa, o'tkazib yuboramiz
            
            try:
                # Guruh a'zolari sonini tekshirish
                chat_members_count = await bot.get_chat_member_count(grp_telegram_id)
                
                # Adminlar sonini hisoblash
                admins = await bot.get_chat_administrators(grp_telegram_id)
                admin_count = len(admins)
                
                # Oddiy a'zolar soni (adminlardan tashqari)
                regular_members = chat_members_count - admin_count
                
                # Birinchi bo'sh guruhni topamiz (200 dan kam bo'lishi kerak)
                if regular_members < 200:
                    selected_group = grp_id
                    group_obj = grp
                    min_member_count = regular_members
                    break  # Birinchi bo'sh guruhni topganimizdan keyin to'xtaymiz
                else:
                    # Guruh to'lgan, is_full=True qilamiz
                    try:
                        async with aiohttp.ClientSession() as session_update:
                            await session_update.patch(
                                f"{API_BASE_URL}/groups/{grp_id}/",
                                json={"is_full": True}
                            )
                    except:
                        pass
            except Exception as e:
                continue
        
        # Agar hech bir bo'sh guruh topilmasa
        if selected_group is None:
            await message.answer(
                "❌ Barcha guruhlar to'lgan (200/200).\n\n"
                "Admin bilan bog'laning."
            )
            try:
                await state.finish()
            except (KeyError, Exception):
                pass
            return

    # Guruh linkini tekshirish
    if not group_obj:
        await message.answer("❌ Guruh topilmadi. Admin bilan bog'laning.")
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
        return

    group_invite_link = group_obj.get("invite_link")
    group_telegram_id = group_obj.get("telegram_group_id")

    # Agar link yo'q yoki noto'g'ri bo'lsa, bot o'zi yangi link yaratadi (agar admin bo'lsa)
    if not group_invite_link or not group_telegram_id:
        await message.answer("❌ Diqqat: Guruh uchun link o'rnatilmagan. Admin bilan bog'laning.")
        admin_msg = (
            "🚨 Diqqat: Guruh uchun link o'rnatilmagan!\n\n"
            f"Guruh nomi: {group_obj['name']}\n"
            f"Guruh ID: {group_telegram_id or 'N/A'}\n"
        )
        for admin_id in ADMINS:
            try:
                await bot.send_message(int(admin_id), admin_msg)
            except Exception:
                pass
        try:
            await state.finish()
        except (KeyError, Exception):
            pass
        return

    # Bot admin bo'lsa, avval guruh a'zolari sonini tekshiramiz
    try:
        bot_info = await bot.get_me()
        bot_member = await bot.get_chat_member(group_telegram_id, bot_info.id)
        
        if bot_member.status in ["administrator", "creator"]:
            # Guruh a'zolari sonini tekshirish (adminlardan tashqari)
            try:
                chat_members_count = await bot.get_chat_member_count(group_telegram_id)
                
                # Adminlar sonini hisoblash
                admins = await bot.get_chat_administrators(group_telegram_id)
                admin_count = len(admins)
                
                # Oddiy a'zolar soni (adminlardan tashqari)
                regular_members = chat_members_count - admin_count
                
                print(f"📊 Guruh statistikasi: Jami={chat_members_count}, Adminlar={admin_count}, Oddiy a'zolar={regular_members}")
                
                # Agar 200 dan oshgan bo'lsa, keyingi guruhni topamiz
                if regular_members >= 200:
                    # Barcha guruhlarni tekshirib, bo'sh guruhni topamiz
                    next_group = None
                    async with aiohttp.ClientSession() as session3:
                        async with session3.get(f"{API_BASE_URL}/groups/") as resp:
                            all_groups = await resp.json()
                    
                    for grp in all_groups:
                        if grp.get("telegram_group_id"):
                            try:
                                grp_count = await bot.get_chat_member_count(grp["telegram_group_id"])
                                grp_admins = await bot.get_chat_administrators(grp["telegram_group_id"])
                                grp_regular = grp_count - len(grp_admins)
                                
                                if grp_regular < 200:
                                    next_group = grp
                                    break
                            except Exception as e:
                                continue
                    
                    if next_group:
                        # Keyingi guruhga o'tkazamiz
                        await message.answer(
                            f"⚠️ Tanlagan guruhingiz to'lgan ({regular_members}/200)!\n\n"
                            f"✅ Sizni '{next_group['name']}' guruhiga o'tkazyapmiz.\n\n"
                            f"Davom etamizmi?"
                        )
                        
                        # State ni yangilaymiz
                        await state.update_data(group_id=next_group["id"])
                        selected_group = next_group["id"]
                        group_telegram_id = next_group["telegram_group_id"]
                        
                        # Yangi guruh uchun link yaratamiz
                        # (pastda yana tekshiriladi, shuning uchun return qilmaymiz)
                    else:
                        # Hech qanday bo'sh guruh yo'q
                        await message.answer(
                            f"❌ Kechirasiz, barcha guruhlar to'lgan!\n\n"
                            f"Iltimos, admin bilan bog'laning."
                        )
                        try:
                            await state.finish()
                        except:
                            pass
                        return
            except Exception as e:
                pass
            
            # Yangi guruh uchun yana bir marta a'zolar sonini tekshiramiz
            try:
                chat_members_count = await bot.get_chat_member_count(group_telegram_id)
                admins = await bot.get_chat_administrators(group_telegram_id)
                admin_count = len(admins)
                regular_members = chat_members_count - admin_count
                
                if regular_members >= 200:
                    await message.answer(
                        f"❌ Kechirasiz, bu guruh ham to'lgan!\n\n"
                        f"Iltimos, admin bilan bog'laning."
                    )
                    try:
                        await state.finish()
                    except:
                        pass
                    return
            except Exception as e:
                pass
            
            # Guruh to'lmagan bo'lsa, 1 martalik link yaratamiz
            try:
                invite_link_obj = await bot.create_chat_invite_link(
                    group_telegram_id,
                    member_limit=1
                )
                group_invite_link = invite_link_obj.invite_link
                
                # Databazaga yangi linkni saqlash
                async with aiohttp.ClientSession() as session2:
                    update_payload = {"invite_link": group_invite_link}
                    try:
                        await session2.patch(
                            f"{API_BASE_URL}/groups/{selected_group}/",
                            json=update_payload
                        )
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass

    # Userga link beramiz - lekin DBga yozmaymiz!
    group_name = group_obj["name"]
    msg = f"✅ Guruh topildi!\n\n"
    msg += f"👥 Guruh: {group_name}\n"
    msg += f"👤 Hozirgi a'zolar: {min_member_count}/200\n\n"
    msg += "📚 Guruhga qo'shiling:\n"
    msg += f"🔗 {group_invite_link}\n\n"
    msg += "⚠️ Guruhga qo'shilgandan so'ng /start ni qayta bosing!\n"
    msg += "Avtomatik ro'yxatdan o'tasiz va vazifa yuborishingiz mumkin bo'ladi.\n"
    
    await message.answer(msg, reply_markup=None)
    
    # User ma'lumotlarini state ga saqlaymiz (link olganini belgilash uchun)
    await state.update_data(
        pending_registration=True,
        full_name=message.text,
        group_id=selected_group,
        group_name=group_name,
        user_id=message.from_user.id
    )
    # State ni finish qilmaymiz - bu orqali user link olganini bilamiz
