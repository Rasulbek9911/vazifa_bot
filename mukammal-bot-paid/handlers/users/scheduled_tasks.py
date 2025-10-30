"""
Scheduled tasks: weekly reports, unsubmitted task warnings
"""
import aiohttp
from data.config import ADMINS, API_BASE_URL
from loader import bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from asgiref.sync import sync_to_async
from utils.safe_send_message import safe_send_message


# --- Haftalik report ---
async def send_weekly_reports():
    """Har hafta guruh bo'yicha PDF report yuborish"""
    async with aiohttp.ClientSession() as session:
        # Guruhlarni olib kelamiz
        async with session.get(f"{API_BASE_URL}/groups/") as resp:
            groups = await resp.json()
        for g in groups:
            chat_id = g.get("telegram_group_id")
            group_id = g["id"]

            if not chat_id:
                continue  # telegram_group_id yo'q bo'lsa tashlab ketamiz

            # PDF reportni olib kelamiz
            async with session.get(f"{API_BASE_URL}/reports/{group_id}/weekly/pdf/") as resp:
                if resp.status == 200:
                    pdf_bytes = await resp.read()
                    await bot.send_document(
                        chat_id,
                        ("weekly_report.pdf", pdf_bytes),
                        caption=f"📊 {g['name']} guruhining haftalik hisobot"
                    )
                else:
                    await bot.send_message(chat_id, "❌ Reportni olishda xatolik yuz berdi")
                    

# --- Vazifa topshirmaganlarga eslatma ---
async def send_unsubmitted_warnings():
    """Active mavzular bo'yicha vazifa topshirmagan studentlarga eslatma yuborish"""
    from base_app.models import Student, Topic, Task
    active_topics = await sync_to_async(list)(Topic.objects.filter(is_active=True))
    students = await sync_to_async(list)(Student.objects.all())

    for student in students:
        submitted = await sync_to_async(list)(
            Task.objects.filter(student=student, topic__in=active_topics)
        )
        submitted_topic_ids = [t.topic_id for t in submitted]

        unsubmitted = [t for t in active_topics if t.id not in submitted_topic_ids]

        if unsubmitted:
            msg = f"⚠️ Siz {len(unsubmitted)} ta mavzu bo'yicha vazifa topshirmagansiz!\n"
            msg += "\n".join([f"- {t.title}" for t in unsubmitted])
            await safe_send_message(student.telegram_id, msg)

            if len(unsubmitted) >= 3:
                admin_msg = f"🚨 {student.full_name} {len(unsubmitted)} ta vazifa topshirmagan."
                admin_msg += f"\nTelegram ID: <code>{student.telegram_id}</code>"
                admin_msg += f"\nMavzular:\n" + "\n".join([f"- {t.title}" for t in unsubmitted])

                kb = InlineKeyboardMarkup()
                kb.add(InlineKeyboardButton(
                    text="Chatga o'tish",
                    url=f"tg://user?id={student.telegram_id}"
                ))

                await bot.send_message(
                    ADMINS[0],
                    admin_msg,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
