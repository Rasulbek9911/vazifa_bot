#!/usr/bin/env python3
"""
Haftalik report funksiyasini manual test qilish
"""
import asyncio
import sys
import os
import django
import logging

# Django sozlash
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from handlers.users.scheduled_tasks import send_weekly_reports

async def main():
    print("🧪 Haftalik report test boshlandi...")
    await send_weekly_reports()
    print("✅ Test yakunlandi")

if __name__ == "__main__":
    asyncio.run(main())
