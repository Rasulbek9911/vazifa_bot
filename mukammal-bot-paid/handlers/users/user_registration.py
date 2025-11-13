"""
User registration flow: start command, full name processing
No invite code required - direct registration
Both channels use approval links
"""
from aiogram import types
import aiohttp
from aiogram.dispatcher import FSMContext
from data.config import ADMINS, API_BASE_URL, GENERAL_CHANNEL_ID, GENERAL_CHANNEL_INVITE_LINK
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
                    f"👋 Salom, {data['full_name']}!\nSiz allaqachon ro'yxatdan o'tgansiz ✅",
                    reply_markup=vazifa_key
                )
                return
    
    # Ro'yxatdan o'tish jarayonini boshlash
    await message.answer(
        "Assalomu alaykum! 👋\n\n"
        "Ro'yxatdan o'tish uchun F.I.Sh kiriting:"
    )
    await RegisterState.full_name.set()


# F.I.Sh qabul qilish va ro'yxatdan o'tkazish
@dp.message_handler(state=RegisterState.full_name)
async def process_fish(message: types.Message, state: FSMContext):
    """F.I.Sh qabul qilish va avtomatik ro'yxatdan o'tkazish"""
    await state.update_data(full_name=message.text)
    data = await state.get_data()
    
    # Kanallarni va ularning a'zolar sonini olish
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()

        # Har bir kanal uchun a'zolar sonini tekshiramiz (700 foydalanuvchi + 3 admin = 703 limit)
        selected_group = None
        for g in groups:
            group_id = g["id"]
            async with session.get(f"{API_BASE_URL}/students/?group_id={group_id}") as resp2:
                students_in_group = await resp2.json()
                if len(students_in_group) < 700:
                    selected_group = group_id
                    break

    if selected_group is None:
        await message.answer("❌ Hech bir kanalda bo'sh joy yo'q. Admin bilan bog'laning.")
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

    # Guruh linkini olish - endi kanal bo'lgani uchun approval link
    group_obj = next((g for g in groups if g["id"] == selected_group), None)
    
    # O'z kanal uchun approval link (databazadan)
    group_invite_link = None
    if group_obj:
        # Kanal uchun approval link faqat databazada saqlangan linkdan olinadi
        group_invite_link = group_obj.get("invite_link")
        if not group_invite_link:
            # Agar link yo'q bo'lsa, adminlarga xabar beramiz
            await message.answer("❌ Diqqat: Kanalingiz uchun approval link o'rnatilmagan. Admin bilan bog'laning.")
            admin_msg = (
                "🚨 Diqqat: Kanal uchun approval link o'rnatilmagan!\n\n"
                f"Kanal nomi: {group_obj['name']}\n"
                f"Kanal ID: {group_obj.get('telegram_group_id', 'N/A')}\n"
            )
            for admin_id in ADMINS:
                try:
                    await bot.send_message(int(admin_id), admin_msg)
                except Exception:
                    pass
    
    # Umumiy kanal uchun approval link
    umumiy_invite_link = GENERAL_CHANNEL_INVITE_LINK
        
    
    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as resp:
            if resp.status == 201:
                group_name = group_obj["name"] if group_obj else ""
                msg = f"✅ Ro'yxatdan o'tdingiz! Sizning kanal - {group_name}.\n\n"
                
                # Linklar haqida xabar berish
                msg += "📚 Quyidagi kanallarga qo'shiling:\n"
                
                # O'z kanali linki
                if group_invite_link:
                    msg += f"🔹 O'z kanalingiz: {group_invite_link}\n"
                    msg += f"   (So'rov yuboring, admin tasdiqlaydi)\n"
                
                # Umumiy kanal linki
                if umumiy_invite_link:
                    msg += f"🔹 Umumiy kanal: {umumiy_invite_link}\n"
                    msg += f"   (So'rov yuboring, admin tasdiqlaydi)\n"
                
                msg += "\n⚠️ Vazifa yuborishdan oldin kanallarga qo'shilishingiz shart!\n"
                
                await message.answer(msg, reply_markup=vazifa_key)
            else:
                await message.answer("❌ Ro'yxatdan o'tishda xatolik bo'ldi.")
    
    try:
        await state.finish()
    except Exception as e:
        pass
