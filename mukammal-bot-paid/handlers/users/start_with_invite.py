from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL
from loader import dp, bot
from states.register_state import RegisterState
from keyboards.default.vazifa_keyboard import vazifa_key


# --- START with Invite Code ---
@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    """
    /start yoki /start abc12345 (invite code bilan deep linking)
    """
    # Avval state ni tozalaymiz
    current_state = await state.get_state()
    if current_state:
        await state.finish()
    
    # Deep linking - invite code bilan kelganmi?
    args = message.get_args()
    
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
        await state.update_data(invite_code=args)
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
                await state.update_data(invite_code=invite_code)
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
        await state.finish()
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
                    await state.finish()
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

    # Guruh linkini olish (guruh obyektidan)
    group_obj = next((g for g in groups if g["id"] == selected_group), None)
    group_link = group_obj.get("invite_link") if group_obj else None
    umumiy_link = "https://t.me/+yIsZnSKlj9lmMTEy"  # umumiy guruh linki
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro'yxatdan o'tdingiz! Sizning guruh - {group_name}.\n\n"
                msg += "📚 Guruhga qo'shilib oling:\n"
                if group_link:
                    msg += f"🔹 O'z guruhingiz: {group_link}\n"
                msg += f"🔹 Umumiy guruh: {umumiy_link}\n\n"
                msg += "⚠️ Vazifa yuborishdan oldin IKKALA guruhga ham qo'shilishingiz shart!"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass


# --- Admin: Invite code yaratish ---
@dp.message_handler(commands=["generate_invite"])
async def generate_invite(message: types.Message):
    """Admin faqat invite code yaratishi mumkin"""
    if str(message.from_user.id) not in ADMINS:
        await message.answer("❌ Sizda bu buyruqni ishlatish huquqi yo'q.")
        return
    
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
