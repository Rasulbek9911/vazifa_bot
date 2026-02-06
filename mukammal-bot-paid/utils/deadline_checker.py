"""
Deadline checker - har 10 daqiqada deadline o'tgan testlarni tekshiradi
va avval yechgan userlarga batafsil natijalarni yuboradi
"""
import asyncio
import logging
from datetime import datetime, timezone
import aiohttp
import re

from data.config import API_BASE_URL
from loader import bot

logger = logging.getLogger(__name__)


async def check_and_notify_expired_deadlines():
    """Deadline o'tgan testlarni tekshiradi va userlarga xabar yuboradi"""
    try:
        async with aiohttp.ClientSession() as session:
            # Barcha active topiclarni olamiz
            async with session.get(f"{API_BASE_URL}/topics/") as resp:
                if resp.status != 200:
                    logger.error(f"Topics API xatolik: {resp.status}")
                    return
                topics = await resp.json()
            
            current_time = datetime.now(timezone.utc)
            
            for topic in topics:
                # Faqat deadline bor va active topiclarni tekshiramiz
                if not topic.get('deadline') or not topic.get('is_active'):
                    continue
                
                # Deadline ni tekshiramiz
                deadline_str = topic['deadline']
                deadline_dt = datetime.fromisoformat(deadline_str.replace('Z', '+00:00'))
                
                # Agar deadline o'tmagan bo'lsa, o'tkazib yuboramiz
                if current_time <= deadline_dt:
                    continue
                
                # Agar deadline 10 daqiqadan ko'proq vaqt o'tgan bo'lsa, o'tkazib yuboramiz
                # (faqat yangi o'tgan deadlinelar uchun xabar yuboramiz)
                # PRODUCTION: 10 daqiqa (600 sekund)
                time_since_deadline = (current_time - deadline_dt).total_seconds()
                if time_since_deadline > 600:  # 10 daqiqa
                    continue
                
                # Deadline o'tgan - ushbu mavzu uchun barcha testlarni olamiz
                topic_id = topic['id']
                topic_title = topic['title']
                correct_answers = topic.get('correct_answers', {})
                
                if not correct_answers:
                    continue  # Test emas, maxsus topshiriq
                
                # Ushbu mavzu uchun barcha tasklarni olamiz
                async with session.get(f"{API_BASE_URL}/tasks/") as resp:
                    if resp.status != 200:
                        logger.error(f"Tasks API xatolik: {resp.status}")
                        continue
                    all_tasks = await resp.json()
                
                # Faqat shu mavzu uchun testlarni filter qilamiz
                topic_tasks = [
                    task for task in all_tasks
                    if task['topic']['id'] == topic_id and task['task_type'] == 'test'
                ]
                
                logger.info(f"Deadline o'tgan mavzu: {topic_title}, {len(topic_tasks)} ta test topildi")
                
                # Har bir test uchun batafsil natijalarni yuboramiz
                for task in topic_tasks:
                    await send_detailed_results(task, correct_answers, topic_title)
                
    except Exception as e:
        logger.error(f"Deadline checker xatolik: {e}", exc_info=True)


async def send_detailed_results(task, correct_answers, topic_title):
    """Bitta task uchun batafsil natijalarni yuboradi"""
    try:
        student_telegram_id = task['student']['telegram_id']
        test_code = task.get('test_code')
        test_answers = task.get('test_answers')
        
        if not test_code or not test_answers:
            return
        
        # Test kodini tekshiramiz
        if test_code not in correct_answers:
            return
        
        # To'g'ri javoblarni parse qilamiz
        correct = correct_answers[test_code].lower().strip()
        user_answer = test_answers.lower().strip()
        
        # Parse admin correct answers
        correct_answers_list = []
        has_numbers = bool(re.search(r'\d', correct))
        
        if has_numbers:
            for match in re.finditer(r'\d+([a-zx]+)', correct):
                answers = match.group(1)
                if answers == 'x':
                    correct_answers_list.append(['x'])
                else:
                    correct_answers_list.append(list(answers))
        elif re.match(r'^[a-zx]+$', correct):
            correct_answers_list = [[ch] for ch in correct]
        else:
            filtered = ''.join(ch for ch in correct if ch.isalpha() or ch == 'x')
            correct_answers_list = [[ch] for ch in filtered]
        
        # Parse student answers
        student_answers_list = []
        has_numbers_student = bool(re.search(r'\d', user_answer))
        
        if has_numbers_student:
            for match in re.finditer(r'\d+([a-zx])', user_answer):
                student_answers_list.append(match.group(1))
        elif re.match(r'^[a-zx]+$', user_answer):
            student_answers_list = list(user_answer)
        else:
            filtered = ''.join(ch for ch in user_answer if ch.isalpha() or ch == 'x')
            student_answers_list = list(filtered)
        
        # Natijalarni hisoblash
        correct_count = 0
        total_count = len(correct_answers_list)
        
        result_text = f"🔔 Deadline o'tdi!\n\n"
        result_text += f"📚 Mavzu: {topic_title}\n"
        result_text += f"📝 Test kodi: {test_code}\n\n"
        result_text += f"📊 Sizning natijalaringiz (batafsil):\n\n"
        
        for i in range(min(total_count, len(student_answers_list))):
            student_ans = student_answers_list[i]
            correct_ans_list = correct_answers_list[i]
            
            if student_ans in correct_ans_list:
                result_text += f"{i+1}. ✅ {student_ans.upper()}\n"
                correct_count += 1
            else:
                valid_answers = '/'.join([a.upper() for a in correct_ans_list])
                result_text += f"{i+1}. ❌ {student_ans.upper()} (To'g'ri: {valid_answers})\n"
        
        percentage = (correct_count / total_count * 100) if total_count > 0 else 0
        final_grade = int(correct_count * 0.8)  # 80% ball
        
        result_text += f"\n📈 Natija: {correct_count}/{total_count} ({percentage:.1f}%)"
        result_text += f"\n🏆 Final ball: {final_grade}/{total_count} (80%)"
        
        # Userga yuborish
        await bot.send_message(student_telegram_id, result_text)
        logger.info(f"Batafsil natija yuborildi: user_id={student_telegram_id}, topic={topic_title}")
        
    except Exception as e:
        logger.error(f"Batafsil natija yuborishda xatolik: {e}", exc_info=True)


async def deadline_checker_loop():
    """Background task - har 10 daqiqada deadline tekshiradi (PRODUCTION rejimi)"""
    logger.info("Deadline checker started")
    
    while True:
        try:
            await check_and_notify_expired_deadlines()
        except Exception as e:
            logger.error(f"Deadline checker loop xatolik: {e}", exc_info=True)
        
        # PRODUCTION: 10 daqiqa (600 sekund)
        await asyncio.sleep(600)
