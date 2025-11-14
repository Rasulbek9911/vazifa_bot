"""
User registration flow: start command, full name processing
No invite code required - direct registration
Single group with approval link (50 user limit, excluding admins/owners/bots)
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key


# --- START - Direct Registration (No Invite Code) ---
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start - to'g'ridan-to'g'ri ro'yxatdan o'tish (invite code yo'q)
    """
    # Avval state ni tozalaymiz
    current_state = await state.get_state()
    if current_state:
        try:
            await state.finish()
        except Exception as e:
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
                await message.answer(
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro'yxatdan o'tgansiz, vazifalarni yuborishingiz mumkin.",
                    reply_markup=vazifa_key
                )
                return
    
    # Ro'yxatdan o'tish jarayonini boshlash
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Ro'yxatdan o'tish uchun Ism familiyangizni kiriting: \n(Misol: Fayziyev Aslbek)"
    )
    await RegisterState.full_name.set()


# F.I.Sh qabul qilish va ro'yxatdan o'tkazish
@dp.message_handler(state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    """F.I.Sh qabul qilish va avtomatik ro'yxatdan o'tkazish"""
    await state.update_data(full_name=message.text)
    data = await state.get_data()
    
    # Barcha guruhlarni olish va bo'sh guruhni topish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
        
        if not groups:
            await message.answer("❌ Guruh topilmadi. Admin bilan bog'laning.")
            try:
                await state.finish()
            except Exception as e:
                pass
            return
        
        # Har bir guruhni tekshirib, bo'sh guruhni topamiz
        selected_group = None
        group_obj = None
        real_member_count = 0
        
        for grp in groups:
            grp_id = grp["id"]
            grp_telegram_id = grp.get("telegram_group_id")
            
            # Database dan studentlar sonini tekshirish
            async with session.get(f"{API_BASE_URL}/students/?group_id={grp_id}") as resp2:
                students_in_db = await resp2.json()
            
            # Agar Telegram group ID bo'lsa, haqiqiy a'zolar sonini tekshiramiz
            # Faqat oddiy userlarni sanaymiz (adminlar, ownerlar, botlar emas)
            member_count = len(students_in_db)  # Default: DB dan
            
            if grp_telegram_id:
                try:
                    # Guruh a'zolarini olish
                    chat_members_count = await bot.get_chat_members_count(grp_telegram_id)
                    
                    # Adminlar, ownerlar va botlarni sanash
                    non_user_count = 0
                    try:
                        # Chat administratorlarini olish
                        admins = await bot.get_chat_administrators(grp_telegram_id)
                        non_user_count = len(admins)  # Adminlar va ownerlar
                    except Exception as e:
                        non_user_count = 3  # Default: ~3 admin
                    
                    # Haqiqiy user soni = Jami a'zolar - Adminlar/Ownerlar/Botlar
                    member_count = max(0, chat_members_count - non_user_count)
                except Exception as e:
                    pass
                    # Xatolik bo'lsa, DB dan foydalanamiz
                    member_count = len(students_in_db)
            
            # 50 dan kam bo'lsa, bu guruhni tanlaymiz
            if member_count < 50:
                selected_group = grp_id
                group_obj = grp
                real_member_count = member_count
                break
        
        # Agar hech bir bo'sh guruh topilmasa
        if selected_group is None:
            await message.answer(
                "❌ Barcha guruhlar to'lgan.\n\n"
                "Admin bilan bog'laning."
            )
            try:
                await state.finish()
            except Exception as e:
                pass
            return
        
        group_id = selected_group

    # Avtomatik tanlangan guruhga ro'yxatdan o'tkazamiz
    full_name = data["full_name"]
    payload = {
        "telegram_id": str(message.from_user.id),
        "full_name": full_name,
        "group_id": selected_group
    }

    # Guruh linkini tekshirish - approval link
    if not group_obj:
        await message.answer("❌ Guruh topilmadi. Admin bilan bog'laning.")
        try:
            await state.finish()
        except Exception as e:
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
        except Exception:
            pass
        return
    
    # Bot admin bo'lsa, yangi invite link yaratadi
    try:
        # Bot guruhda admin ekanligini tekshirish
        bot_info = await bot.get_me()
        bot_member = await bot.get_chat_member(group_telegram_id, bot_info.id)
        
        if bot_member.status in ["administrator", "creator"]:
            # Yangi invite link yaratish (member_limit=1 - faqat 1 kishi uchun)
            try:
                invite_link_obj = await bot.create_chat_invite_link(
                    group_telegram_id,
                    member_limit=1  # 1 marta ishlatiladi
                )
                group_invite_link = invite_link_obj.invite_link
                
                # Databazaga yangi linkni saqlash
                async with aiohttp.ClientSession() as session:
                    update_payload = {"invite_link": group_invite_link}
                    try:
                        async with session.patch(
                            f"{API_BASE_URL}/groups/{group_id}/",
                            json=update_payload
                        ) as resp:
                            pass
                    except Exception as e:
                        pass
            except Exception as e:
                print(f"[DEBUG] Invite link yaratishda xatolik: {e}")
                # Eski linkni ishlatishga harakat qilamiz
                pass
    except Exception as e:
        print(f"[DEBUG] Bot admin status tekshirishda xatolik: {e}")
    
    # Ro'yxatdan o'tkazish
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"]
                msg = f"✅ Ro'yxatdan o'tdingiz!\n\n"
                msg += f"👥 Guruh: {group_name}\n"
                msg += f"👤 Hozirgi a'zolar: {real_member_count + 1}/50\n\n"
                msg += "📚 Guruhga qo'shiling:\n"
                msg += f"🔗 {group_invite_link}\n"
                msg += "   (So'rov yuboring, admin tasdiqlaydi)\n\n"
                msg += "⚠️ Vazifa yuborishdan oldin guruhga qo'shilishingiz shart!\n"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass
