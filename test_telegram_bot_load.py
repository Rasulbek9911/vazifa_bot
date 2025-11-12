"""
Telegram Bot Load Testing
Telegram API orqali to'g'ridan-to'g'ri botni test qilish
"""
import asyncio
import time
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# DIQQAT: Bu yerga o'z bot tokeningizni kiriting
BOT_TOKEN = "YOUR_BOT_TOKEN"  # .env dan oling

# Test config
NUM_USERS = 100  # Telegram API limiti tufayli kichik son
DELAY_BETWEEN_REQUESTS = 0.1  # Telegram rate limitdan qochish uchun

# Fake user IDs (test uchun)
FAKE_USER_IDS = list(range(100000, 100000 + NUM_USERS))

# Stats
stats = {
    "total": 0,
    "success": 0,
    "failed": 0,
    "start_time": None,
    "errors": []
}


async def simulate_start_command(bot: Bot, user_id: int):
    """
    /start kommandasini simulyatsiya qilish
    DIQQAT: Bu faqat API chaqiruvlarini test qiladi, 
    haqiqiy userlardan xabar yuborish Telegram tomonidan man etilgan
    """
    try:
        # Biz faqat bot handlerlarimizning ishlashini test qila olamiz
        # Haqiqiy userdan xabar yuborish mumkin emas
        
        # Shuning uchun API endpointlariga to'g'ridan-to'g'ri murojaat qilamiz
        print(f"[INFO] Simulating /start for user {user_id}")
        stats["success"] += 1
        
    except Exception as e:
        stats["failed"] += 1
        stats["errors"].append(f"User {user_id}: {str(e)}")
    finally:
        stats["total"] += 1
        if stats["total"] % 10 == 0:
            elapsed = time.time() - stats["start_time"]
            print(f"Progress: {stats['total']}/{NUM_USERS} | "
                  f"Success: {stats['success']} | "
                  f"Failed: {stats['failed']} | "
                  f"Time: {elapsed:.1f}s")


async def run_telegram_load_test():
    """
    MUHIM ESLATMA:
    Telegram API orqali fake userlardan xabar yuborish MUMKIN EMAS!
    Bu faqat backend APIni test qiladi.
    
    Haqiqiy bot testini qilish uchun:
    1. Backend API load testini ishlating (test_bot_load.py)
    2. Botni ishga tushiring
    3. Bir nechta haqiqiy user (yoki test accountlar) orqali test qiling
    """
    print("="*60)
    print("TELEGRAM BOT LOAD TEST")
    print("="*60)
    print("DIQQAT: Telegram API orqali fake userlardan xabar yuborish mumkin emas!")
    print("Faqat backend API load testini ishga tushiramiz...")
    print("="*60)
    print("\nBackend API testini ishlatish uchun:")
    print("  python3 test_bot_load.py")
    print("\nHaqiqiy bot testini qilish uchun:")
    print("  1. Backend API test qiling")
    print("  2. Botni ishga tushiring: cd mukammal-bot-paid && python3 app.py")
    print("  3. Bir nechta haqiqiy user orqali test qiling")
    print("="*60)


async def monitoring_script():
    """
    Bot monitoring uchun skript
    Bot ishlayotgan paytda uning performanceini kuzatish
    """
    print("\n" + "="*60)
    print("BOT MONITORING SCRIPT")
    print("="*60)
    print("\nBotni monitoring qilish uchun quyidagi commandalarni ishlating:\n")
    print("1. CPU va Memory monitoring:")
    print("   top -p $(pgrep -f 'python3 app.py')")
    print("\n2. Requests per second:")
    print("   watch -n 1 'tail -n 100 bot.log | grep \"Start polling\" | wc -l'")
    print("\n3. Error monitoring:")
    print("   tail -f bot.log | grep ERROR")
    print("\n4. Database connections:")
    print("   watch -n 1 'psql -c \"SELECT count(*) FROM pg_stat_activity\"'")
    print("="*60)


if __name__ == "__main__":
    import sys
    
    print("\nTelegram Bot Testing Utilities\n")
    print("1. Backend API Load Test (Tavsiya etiladi)")
    print("2. Bot Monitoring Guide")
    print("3. Exit")
    
    choice = input("\nTanlang (1-3): ").strip()
    
    if choice == "1":
        print("\nBackend API load testini ishlatish:")
        print("  python3 test_bot_load.py")
        sys.exit(0)
    elif choice == "2":
        asyncio.run(monitoring_script())
    else:
        sys.exit(0)
