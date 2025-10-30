"""
Guruh/kanal turini tekshirish
"""
import asyncio
from aiogram import Bot
from data.config import BOT_TOKEN

GENERAL_GROUP_ID = "-1003295943458"  # Yangi guruh ID

async def check_group():
    bot = Bot(token=BOT_TOKEN)
    
    try:
        # Guruh ma'lumotini olish
        chat_info = await bot.get_chat(GENERAL_GROUP_ID)
        
        print("\n" + "="*60)
        print("📋 GURUH MA'LUMOTLARI:")
        print("="*60)
        print(f"🆔 Chat ID: {chat_info.id}")
        print(f"📝 Nomi: {chat_info.title}")
        print(f"📁 Turi: {chat_info.type}")
        
        if hasattr(chat_info, 'username') and chat_info.username:
            print(f"🌐 Username: @{chat_info.username}")
            print(f"🔗 Public link: https://t.me/{chat_info.username}")
            print(f"⚠️  PUBLIC - har kim kira oladi!")
        else:
            print(f"🔒 PRIVATE - faqat invite link orqali")
        
        # Bot statusini tekshirish
        bot_member = await bot.get_chat_member(GENERAL_GROUP_ID, bot.id)
        print(f"\n🤖 Bot statusi: {bot_member.status}")
        
        if bot_member.status == "administrator":
            print(f"✅ Bot administrator")
            if hasattr(bot_member, 'can_invite_users'):
                print(f"   - can_invite_users: {bot_member.can_invite_users}")
            if hasattr(bot_member, 'can_manage_chat'):
                print(f"   - can_manage_chat: {bot_member.can_manage_chat}")
        
        print("\n" + "="*60)
        print("📊 TAHLIL:")
        print("="*60)
        
        if chat_info.type == "channel":
            print("❌ Bu CHANNEL - member_limit ishlamaydi!")
            print("❌ Har kim public link orqali kira oladi!")
            print("\n💡 YECHIM: Yangi SUPERGROUP yarating!")
        elif chat_info.type == "supergroup":
            print("✅ Bu SUPERGROUP - member_limit ishlaydi!")
            if hasattr(chat_info, 'username') and chat_info.username:
                print("⚠️  Lekin PUBLIC - har kim kira oladi!")
                print("\n💡 YECHIM 1: Guruhni PRIVATE qiling")
                print("💡 YECHIM 2: Public link bermang, faqat bot invite link bersin")
            else:
                print("✅ PRIVATE supergroup - juda yaxshi!")
                print("✅ Faqat invite link bilan kiriladi")
        
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"❌ XATOLIK: {e}")
    
    finally:
        await bot.close()

if __name__ == '__main__':
    asyncio.run(check_group())
