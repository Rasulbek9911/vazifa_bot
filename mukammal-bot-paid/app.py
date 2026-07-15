from aiogram import executor

from loader import dp, bot
import middlewares, filters, handlers
from utils.notify_admins import on_startup_notify
from utils.set_bot_commands import set_default_commands
from utils.scheduler_instance import scheduler, apply_job, DEFAULT_SCHEDULE
from asgiref.sync import sync_to_async
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

    from base_app.models import ScheduleConfig
    from django.db import close_old_connections
    close_old_connections()
    configs = await sync_to_async(list)(ScheduleConfig.objects.all())
    config_map = {c.job_key: c for c in configs}

    for job_key, defaults in DEFAULT_SCHEDULE.items():
        cfg = config_map.get(job_key)
        if cfg is None:
            weekdays, hour, minute, enabled = defaults['weekdays'], defaults['hour'], defaults['minute'], True
        else:
            weekdays, hour, minute, enabled = cfg.weekdays, cfg.hour, cfg.minute, cfg.enabled

        if enabled:
            apply_job(job_key, weekdays, hour, minute)
            logger.info(f"✅ '{job_key}' scheduleri qo'shildi ({weekdays or 'har kuni'} {hour:02d}:{minute:02d})")
        else:
            logger.info(f"⏸ '{job_key}' scheduleri o'chirilgan (Sozlamalar orqali yoqish mumkin)")

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
