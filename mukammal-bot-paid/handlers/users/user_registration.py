"""
User registration flow: start command, invite code validation, full name processing
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL, GENERAL_GROUP_ID, GENERAL_GROUP_INVITE_LINK
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key


# General channel/group ID is configured in data.config


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
            group_chat_id = group_obj.get("telegram_group_id")
            
            # Guruh turini tekshirish
            try:
                chat_info = await bot.get_chat(group_chat_id)
                is_group_channel = chat_info.type == "channel"
            except:
                is_group_channel = False
            
            if is_group_channel:
                # Channel - oddiy link
                group_chat_invite = await bot.create_chat_invite_link(chat_id=group_chat_id)
            else:
                # Supergroup - 1 martalik link
                group_chat_invite = await bot.create_chat_invite_link(
                    chat_id=group_chat_id,
                    member_limit=1
                )
            
            group_invite_link = group_chat_invite.invite_link
        except Exception as e:
            # Xatolik bo'lsa, eski linkni ishlatamiz
            group_invite_link = group_obj.get("invite_link")
    elif group_obj:
        group_invite_link = group_obj.get("invite_link")
    
    # Umumiy guruh uchun invite link
    umumiy_invite_link = None
    user_already_in_general = False
    
    try:
        user_member = await bot.get_chat_member(GENERAL_GROUP_ID, message.from_user.id)
        if user_member.status not in ["left", "kicked"]:
            user_already_in_general = True
    except:
        pass
    
    if not user_already_in_general:
        try:
            # Guruh turini aniqlash
            is_channel = False
            try:
                chat_info = await bot.get_chat(GENERAL_GROUP_ID)
                is_channel = chat_info.type == "channel"
            except:
                pass
            
            if is_channel:
                # Channel - primary link
                try:
                    umumiy_invite_link = await bot.export_chat_invite_link(chat_id=GENERAL_GROUP_ID)
                except:
                    # Fallback - doimiy link
                    umumiy_invite_link = GENERAL_GROUP_INVITE_LINK
            else:
                # Supergroup - 1 martalik link
                general_chat_invite = await bot.create_chat_invite_link(
                    chat_id=GENERAL_GROUP_ID,
                    member_limit=1
                )
                umumiy_invite_link = general_chat_invite.invite_link
        except:
            # Xatolik - doimiy linkni ishlatamiz
            umumiy_invite_link = GENERAL_GROUP_INVITE_LINK
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro'yxatdan o'tdingiz! Sizning guruh - {group_name}.\n\n"
                
                # Linklar haqida xabar berish
                msg += "📚 Quyidagi guruhlarga qo'shiling:\n"
                
                # O'z guruhi linki
                if group_invite_link:
                    msg += f"🔹 O'z guruhingiz: {group_invite_link}\n"
                
                # Umumiy kanal linki (har doim, agar mavjud bo'lsa)
                if not user_already_in_general and umumiy_invite_link:
                    msg += f"🔹 Umumiy kanal: {umumiy_invite_link}\n"
                    msg += f"   (So'rov yuboring, bot auto-approve qiladi)\n"
                
                msg += "\n⚠️ Vazifa yuborishdan oldin guruhlarga qo'shilishingiz shart!\n"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass
