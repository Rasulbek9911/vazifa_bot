"""
User registration flow: start command, invite code validation, full name processing
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key


# Global constants
GENERAL_GROUP_ID = "-1003295943458"
# Umumiy kanal uchun doimiy approval link (qo'lda tasdiqlash bilan)
GENERAL_GROUP_INVITE_LINK = "https://t.me/+6TLsK-8Z7PJhNWY6"


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
            group_chat_id = group_obj.get("telegram_group_id")
            print(f"Guruh uchun invite link yaratilmoqda (chat_id={group_chat_id})...")
            
            # Guruh turini tekshirish
            try:
                chat_info = await bot.get_chat(group_chat_id)
                print(f"   📋 Guruh nomi: {chat_info.title}")
                print(f"   📋 Guruh turi: {chat_info.type}")
                is_group_channel = chat_info.type == "channel"
            except Exception as e:
                print(f"   ⚠️ Guruh ma'lumotini olishda xatolik: {e}")
                is_group_channel = False
            
            if is_group_channel:
                # Bu ham channel ekan - member_limit ishlamaydi
                print(f"   ⚠️ Bu CHANNEL - member_limit ishlamaydi!")
                print(f"   ℹ️ Oddiy link yaratiladi...")
                group_chat_invite = await bot.create_chat_invite_link(
                    chat_id=group_chat_id
                )
            else:
                # Bu supergroup - member_limit ishlaydi
                print(f"   ✅ Bu SUPERGROUP - member_limit=1 ishlatiladi")
                group_chat_invite = await bot.create_chat_invite_link(
                    chat_id=group_chat_id,
                    member_limit=1  # Faqat 1 kishi qo'shilishi mumkin
                )
            
            group_invite_link = group_chat_invite.invite_link
            print(f"✅ Guruh invite link yaratildi: {group_invite_link}")
        except Exception as e:
            print(f"❌ Guruh invite link yaratishda xatolik (chat_id={group_obj.get('telegram_group_id')}): {e}")
            # Agar xatolik bo'lsa, eski linkni ishlatamiz
            group_invite_link = group_obj.get("invite_link")
    elif group_obj:
        # telegram_group_id bo'sh bo'lsa, eski linkni ishlatamiz
        group_invite_link = group_obj.get("invite_link")
        if not group_invite_link:
            print(f"⚠️ Guruh {group_obj.get('name')} uchun telegram_group_id va invite_link yo'q!")
    
    # Umumiy guruh uchun ham 1 martalik link yaratish
    umumiy_invite_link = None
    
    # Avval user allaqachon guruhda ekanligini tekshiramiz
    user_already_in_general = False
    try:
        user_member = await bot.get_chat_member(GENERAL_GROUP_ID, message.from_user.id)
        if user_member.status not in ["left", "kicked"]:
            user_already_in_general = True
            print(f"✅ User allaqachon umumiy guruhda: {user_member.status}")
    except Exception as e:
        print(f"⚠️ User umumiy guruhda emasligini tekshirdik: {e}")
    
    if user_already_in_general:
        # User allaqachon guruhda - link yaratmaslik
        print(f"ℹ️ User allaqachon umumiy guruhda, link yaratilmaydi")
    else:
        try:
            # Avval botning statusini tekshiramiz
            print(f"🔍 Umumiy guruhdagi bot statusini tekshirish... (chat_id={GENERAL_GROUP_ID})")
            try:
                bot_member = await bot.get_chat_member(GENERAL_GROUP_ID, bot.id)
                print(f"   Bot statusi: {bot_member.status}")
                if bot_member.status == "administrator":
                    # Bot adminligining ruxsatlarini ko'ramiz
                    print(f"   ✅ Bot administrator")
                    if hasattr(bot_member, 'can_invite_users'):
                        print(f"   📋 can_invite_users: {bot_member.can_invite_users}")
                    if hasattr(bot_member, 'can_manage_chat'):
                        print(f"   📋 can_manage_chat: {bot_member.can_manage_chat}")
                else:
                    print(f"   ⚠️ Bot admin emas! Status: {bot_member.status}")
            except Exception as status_err:
                print(f"   ⚠️ Bot statusini tekshirib bo'lmadi: {status_err}")
            
            # Guruh haqida ma'lumot olish
            is_channel = False
            try:
                chat_info = await bot.get_chat(GENERAL_GROUP_ID)
                print(f"   📋 Guruh nomi: {chat_info.title}")
                print(f"   📋 Guruh turi: {chat_info.type}")
                
                # Username borligini tekshirish (public kanal bo'lsa)
                if hasattr(chat_info, 'username') and chat_info.username:
                    print(f"   🌐 PUBLIC kanal! Username: @{chat_info.username}")
                    print(f"   ℹ️ Public link: https://t.me/{chat_info.username}")
                else:
                    print(f"   🔒 PRIVATE kanal (username yo'q)")
                
                # Channel ekanligini tekshirish
                if chat_info.type == "channel":
                    is_channel = True
                    print(f"   ℹ️ Bu CHANNEL - invite link strategiyasi ishlatiladi")
                
                # join_by_request borligini tekshirish (faqat supergroup uchun)
                if hasattr(chat_info, 'join_by_request') and not is_channel:
                    print(f"   ⚠️ Join by request: {chat_info.join_by_request}")
                    if chat_info.join_by_request:
                        print(f"   ❌ MUAMMO: 'Approve new members' YOQIQ!")
                        print(f"   ❌ Guruh sozlamalarida 'Approve new members' ni O'CHIRING!")
            except Exception as info_err:
                print(f"   ⚠️ Guruh ma'lumotini ololmadik: {info_err}")
            
            # Invite link yaratish
            print(f"🔗 Umumiy guruh uchun invite link...")
            if is_channel:
                # PRIVATE kanal uchun - export_chat_invite_link (primary link)
                try:
                    umumiy_invite_link = await bot.export_chat_invite_link(chat_id=GENERAL_GROUP_ID)
                    print(f"   🔒 PRIVATE kanal - primary link olindi")
                    print(f"   ⚠️ Admin so'rovlarni qo'lda tasdiqlashi kerak!")
                    print(f"   ✅ Link: {umumiy_invite_link}")
                except Exception as export_err:
                    print(f"   ❌ Primary link olishda xatolik: {export_err}")
                    # Fallback - doimiy linkni ishlatamiz
                    umumiy_invite_link = GENERAL_GROUP_INVITE_LINK
                    print(f"   ℹ️ Doimiy link ishlatiladi: {umumiy_invite_link}")
            else:
                # Supergroup uchun - member_limit bilan (1 martalik)
                general_chat_invite = await bot.create_chat_invite_link(
                    chat_id=GENERAL_GROUP_ID,
                    member_limit=1  # Faqat 1 kishi qo'shilishi mumkin
                )
                umumiy_invite_link = general_chat_invite.invite_link
                print(f"   ✅ Supergroup uchun 1 martalik link yaratildi: {umumiy_invite_link}")
            
            print(f"✅ Umumiy guruh invite link tayyor!")
        except Exception as e:
            print(f"❌ XATOLIK: Umumiy guruh uchun link yaratib bo'lmadi (chat_id={GENERAL_GROUP_ID})")
            print(f"   Xato turi: {type(e).__name__}")
            print(f"   Xato matni: {str(e)}")
            import traceback
            print(f"   Traceback:\n{traceback.format_exc()}")
            
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
                
                # Linklar haqida xabar berish
                msg += "📚 Quyidagi guruhlarga qo'shiling:\n"
                
                # O'z guruhi linki
                if group_invite_link:
                    msg += f"🔹 O'z guruhingiz: {group_invite_link}\n"
                
                # Umumiy kanal linki (har doim)
                if not user_already_in_general:
                    msg += f"🔹 Umumiy kanal: {GENERAL_GROUP_INVITE_LINK}\n"
                    msg += f"   (So'rov yuboring, admin tasdiqlaydi)\n"
                
                msg += "\n⚠️ Vazifa yuborishdan oldin guruhlarga qo'shilishingiz shart!\n"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass
