from aiogram import executor

from loader import dp
import middlewares, filters, handlers
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from handlers.users.scheduled_tasks import send_weekly_reports, send_unsubmitted_warnings, send_deadline_results
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp
import asyncio
import logging

import os
import sys
import django

# Loyihaning root papkasi (manage.py joylashgan katalog)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Django settingsni ko‘rsatamiz
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
# Logging konfiguratsiyasi
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/www/vazifa_bot/mukammal-bot-paid/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
async def on_startup(dispatcher):
    # Birlamchi komandalar (/start va /help)
    await set_default_commands(dispatcher)

    # Bot ishga tushgani haqida adminga xabar berish
    await on_startup_notify(dispatcher)
    
    logger.info("🤖 Bot ishga tushdi")

    # Scheduler sozlash
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    
    # PRODUCTION rejimi:
    # Haftada 2 marta: chorshanba va yakshanba 13:00 da haftalik report
    # DISABLED: Guruhga avtomatik yuborilmasligi kerak
    scheduler.add_job(send_weekly_reports, "cron", day_of_week="wed", hour=13, minute=0, id="weekly_report_wed")
    scheduler.add_job(send_weekly_reports, "cron", day_of_week="sun", hour=13, minute=0, id="weekly_report_sun")
    logger.info("✅ Haftalik report schedulerlari qo'shildi (Chorshanba va Yakshanba 13:00)")
    
    # Har 3 kunda 1 marta eslatma
    scheduler.add_job(send_unsubmitted_warnings, "interval", days=3, id="unsubmitted_warnings")
    logger.info("✅ Eslatma scheduleri qo'shildi (har 3 kunda)")
    
    # Har kuni kechqurun 21:00 da deadline tugagan mavzular uchun batafsil natijalarni yuborish
    scheduler.add_job(send_deadline_results, "cron", hour=21, minute=0, id="deadline_results")
    logger.info("✅ Deadline natijalar scheduleri qo'shildi (har kuni 21:00)")
    
    # TEST rejimi (faqat test paytida yoqing):
    # scheduler.add_job(send_weekly_reports, "cron", minute="*/2", id="test_weekly_report")
    # scheduler.add_job(send_unsubmitted_warnings, "interval", minutes=5, id="test_unsubmitted_warnings")
    # scheduler.add_job(send_deadline_results, "cron", minute="*/5", id="test_deadline_results")  # Har 5 daqiqada test
    # logger.info("⚠️ TEST rejimida schedulerlar yoqildi")
    
    scheduler.start()
    logger.info("🚀 Scheduler ishga tushdi")


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
