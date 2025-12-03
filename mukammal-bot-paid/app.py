from aiogram import executor

from loader import dp
import middlewares, filters, handlers
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from handlers.users.scheduled_tasks import send_weekly_reports, send_unsubmitted_warnings
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp

import os
import sys
import django

# Loyihaning root papkasi (manage.py joylashgan katalog)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

# Django settingsni ko‘rsatamiz
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

async def on_startup(dispatcher):
    # Birlamchi komandalar (/start va /help)
    await set_default_commands(dispatcher)

    # Bot ishga tushgani haqida adminga xabar berish
    await on_startup_notify(dispatcher)

    # Scheduler sozlash
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    
    # PRODUCTION rejimi:
    # Har dushanba ertalab 9:00 da haftalik report
    # scheduler.add_job(send_weekly_reports, "cron", day_of_week="mon", hour=9, minute=0)
    scheduler.add_job(send_weekly_reports, "cron", day_of_week="tue", hour=23, minute=0)
    
    # Har 3 kunda 1 marta eslatma
    scheduler.add_job(send_unsubmitted_warnings, "interval", days=3)
    
    # TEST rejimi (faqat test paytida yoqing):
    # scheduler.add_job(send_weekly_reports, "cron", minute="*/2")
    # scheduler.add_job(send_unsubmitted_warnings, "interval", minutes=2)
    
    scheduler.start()


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
