from aiogram import executor

from loader import dp, bot
import middlewares, filters, handlers
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from handlers.users.scheduled_tasks import send_weekly_reports, send_unsubmitted_warnings, send_deadline_results, send_attendance_csv, send_followup_reminders
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging

import os
import sys
import django

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

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
    await set_default_commands(dispatcher)
    await on_startup_notify(dispatcher)

    # Webhookni o'chirish (polling rejimi uchun)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("🤖 Polling rejimi ishga tushdi")

    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")

    scheduler.add_job(send_weekly_reports, "cron", day_of_week="wed", hour=13, minute=0, id="weekly_report_wed")
    scheduler.add_job(send_weekly_reports, "cron", day_of_week="sun", hour=13, minute=0, id="weekly_report_sun")
    logger.info("✅ Haftalik report schedulerlari qo'shildi (Chorshanba va Yakshanba 13:00)")

    scheduler.add_job(send_unsubmitted_warnings, "cron", day_of_week="mon,thu", hour=21, minute=0, id="unsubmitted_warnings")
    logger.info("✅ Eslatma scheduleri qo'shildi (Dushanba va Payshanba 21:00)")

    scheduler.add_job(send_deadline_results, "cron", hour=21, minute=0, id="deadline_results")
    logger.info("✅ Deadline natijalar scheduleri qo'shildi (har kuni 21:00)")

    scheduler.add_job(send_attendance_csv, "cron", day_of_week="sun", hour=7, minute=0, id="attendance_csv")
    logger.info("✅ Davomat CSV scheduleri qo'shildi (Yakshanba 07:00)")

    scheduler.add_job(send_followup_reminders, "cron", day_of_week="tue,fri", hour=21, minute=0, id="followup_reminders")
    logger.info("✅ Followup eslatma scheduleri qo'shildi (Seshanba va Juma 21:00)")

    scheduler.start()
    logger.info("🚀 Scheduler ishga tushdi")


async def on_shutdown(dispatcher):
    logger.warning("🔴 Bot o'chirilmoqda...")


if __name__ == '__main__':
    executor.start_polling(
        dispatcher=dp,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
    )
