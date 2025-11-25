"""
Auto-approve join requests for general channel/group
"""
from aiogram import types
from loader import dp, bot
from data.config import GENERAL_GROUP_ID, API_BASE_URL
import aiohttp


@dp.chat_join_request_handler()
async def approve_join_request(update: types.ChatJoinRequest):
    """
    Umumiy kanal/guruhga qo'shilish so'rovini avtomatik tasdiqlash
    """
    try:
        # Faqat umumiy kanal/guruh uchun
        if update.chat.id == int(GENERAL_GROUP_ID):
            # User ro'yxatdan o'tganmi tekshirish
            user_id = update.from_user.id
            user_name = update.from_user.first_name or update.from_user.username or f"User {user_id}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{API_BASE_URL}/students/{user_id}/") as resp:
                    if resp.status == 200:
                        # Ro'yxatdan o'tgan bo'lsa - approve qilamiz
                        await bot.approve_chat_join_request(
                            chat_id=update.chat.id,
                            user_id=user_id
                        )
                        print(f"✅ Join request approved for user {user_name} ({user_id})")
                    else:
                        # Ro'yxatdan o'tmagan - rad qilamiz
                        await bot.decline_chat_join_request(
                            chat_id=update.chat.id,
                            user_id=user_id
                        )
                        print(f"❌ Join request declined for user {user_name} ({user_id}) - not registered")
                        
                        # Foydalanuvchiga xabar yuborish
                        try:
                            await bot.send_message(
                                user_id,
                                "❌ Kanalga qo'shilish rad etildi.\n\n"
                                "Avval /start buyrug'i bilan ro'yxatdan o'ting."
                            )
                        except:
                            pass
    except Exception as e:
        print(f"❌ Error approving join request: {e}")
