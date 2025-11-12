# Telegram Bot Load Testing - To'liq Qo'llanma

## 1. Test Strategiyasi

### 1.1. Backend API Load Testing (Tavsiya etiladi)
Backend API ni 500-1000 user bilan test qilish:

```bash
cd /home/rasulbek/Projects/vazifa_bot
python3 test_bot_load.py
```

**Test turlari:**
- Registration test: 500-1000 userlarni ro'yxatdan o'tkazish
- Task submission test: 500-1000 ta vazifa yuborish
- Mixed test: Registration + Task submission

**Kutilgan natijalar:**
- Requests per second: 50-100 RPS
- Avg response time: < 1 second
- Success rate: > 95%

---

### 1.2. Database Performance Testing
PostgreSQL/SQLite performanceini test qilish:

```bash
cd /home/rasulbek/Projects/vazifa_bot

# Database migration va optimizatsiya
python3 manage.py migrate
python3 manage.py sqlflush  # Test ma'lumotlarni tozalash

# Django shell orqali bulk insert test
python3 manage.py shell
```

Django shell ichida:
```python
from base_app.models import Group, Student, Topic, Task
import time

# 700 ta student yaratish
start = time.time()
students = []
for i in range(700):
    students.append(Student(
        telegram_id=f"100{i:04d}",
        full_name=f"Test User {i}",
        group_id=1
    ))
Student.objects.bulk_create(students, batch_size=100)
print(f"Created 700 students in {time.time() - start:.2f}s")

# Natijani tekshirish
print(f"Total students: {Student.objects.count()}")
```

---

### 1.3. Bot Performance Monitoring
Botni ishlatish vaqtida monitoring qilish:

#### Terminal 1: Botni ishga tushirish
```bash
cd /home/rasulbek/Projects/vazifa_bot/mukammal-bot-paid
python3 app.py 2>&1 | tee bot.log
```

#### Terminal 2: Real-time monitoring
```bash
# CPU va Memory
watch -n 1 'ps aux | grep "python3 app.py" | grep -v grep'

# yoki htop ishlatish
htop -p $(pgrep -f "python3 app.py")
```

#### Terminal 3: Log monitoring
```bash
cd /home/rasulbek/Projects/vazifa_bot/mukammal-bot-paid

# Error monitoring
tail -f bot.log | grep -i error

# Debug monitoring
tail -f bot.log | grep DEBUG

# Request monitoring
tail -f bot.log | grep "Start polling"
```

---

### 1.4. Haqiqiy User Testing (Eng muhim!)
Telegram botni haqiqiy userlar bilan test qilish:

**Tayyorgarlik:**
1. Backend serverni ishga tushiring
2. Botni ishga tushiring
3. 5-10 ta test account yarating (Telegram da)

**Test ssenariylari:**

#### Ssenariy 1: Ro'yxatdan o'tish (5-10 user)
```
1. Har bir test user /start ni bosadi
2. Invite code kiritadi
3. F.I.Sh kiritadi
4. Kanallarga qo'shiladi
5. Monitoring: Javob vaqti va success rate
```

#### Ssenariy 2: Vazifa yuborish (5-10 user)
```
1. "📤 Vazifa yuborish" tugmasini bosadi
2. Mavzu tanlaydi
3. Fayl yuboradi
4. Monitoring: File upload speed va success rate
```

#### Ssenariy 3: Concurrent users (5-10 user bir vaqtda)
```
1. Barcha userlar bir vaqtda /start ni bosadi
2. Barcha userlar bir vaqtda vazifa yuboradi
3. Monitoring: Bot response time va error rate
```

---

## 2. Performance Optimization

### 2.1. Database Indexing
```sql
-- PostgreSQL uchun (agar ishlatilsa)
CREATE INDEX idx_student_telegram_id ON base_app_student(telegram_id);
CREATE INDEX idx_student_group ON base_app_student(group_id);
CREATE INDEX idx_task_student ON base_app_task(student_id);
CREATE INDEX idx_task_topic ON base_app_task(topic_id);
```

Django migration orqali:
```python
# base_app/models.py da
class Meta:
    indexes = [
        models.Index(fields=['telegram_id']),
        models.Index(fields=['group']),
    ]
```

### 2.2. API Caching
Redis yoki Memcached ishlatish:
```python
# settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',
    }
}
```

### 2.3. Aiogram Optimizatsiya
```python
# mukammal-bot-paid/loader.py
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# Throttling qo'shish
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from middlewares.throttling import ThrottlingMiddleware

dp.middleware.setup(ThrottlingMiddleware())
```

---

## 3. Load Testing Commandalari

### Backend API Load Test
```bash
# 500 user registration test
cd /home/rasulbek/Projects/vazifa_bot
python3 test_bot_load.py
# Tanlang: 1 (Registration test)

# 500 task submission test
python3 test_bot_load.py
# Tanlang: 2 (Task submission test)

# 1000 user mixed test
python3 test_bot_load.py
# Tanlang: 4 (Custom test)
# Kiriting: 1000
# Kiriting: 50
# Tanlang: registration
```

### Database Bulk Insert Test
```bash
cd /home/rasulbek/Projects/vazifa_bot
python3 manage.py shell < test_bulk_insert.py
```

---

## 4. Kutilgan Natijalar

### Good Performance (Yaxshi)
- Response time: < 1 second
- Success rate: > 95%
- Requests per second: 50-100 RPS
- Memory usage: < 500 MB
- CPU usage: < 50%

### Acceptable Performance (Qoniqarli)
- Response time: 1-3 seconds
- Success rate: > 90%
- Requests per second: 20-50 RPS
- Memory usage: < 1 GB
- CPU usage: < 70%

### Poor Performance (Yomon) - Optimizatsiya kerak!
- Response time: > 3 seconds
- Success rate: < 90%
- Requests per second: < 20 RPS
- Memory usage: > 1 GB
- CPU usage: > 70%

---

## 5. Troubleshooting

### Agar bot sekin ishlasa:
1. Database indexlarni tekshiring
2. Caching qo'shing (Redis)
3. API request loglarini tekshiring
4. Throttling middleware qo'shing

### Agar xotira ko'p ishlatilsa:
1. MemoryStorage o'rniga Redis FSM storage ishlatng
2. Unused imports va modullarni olib tashlang
3. Garbage collector chaqiring

### Agar database sekin ishlasa:
1. SQLite o'rniga PostgreSQL ishlatng
2. Database indexlar qo'shing
3. Query optimizatsiyasi qiling (select_related, prefetch_related)

---

## 6. Ishga Tushirish Ketma-ketligi

```bash
# Terminal 1: Backend server
cd /home/rasulbek/Projects/vazifa_bot
python3 manage.py runserver

# Terminal 2: Bot
cd /home/rasulbek/Projects/vazifa_bot/mukammal-bot-paid
python3 app.py

# Terminal 3: Load test
cd /home/rasulbek/Projects/vazifa_bot
python3 test_bot_load.py

# Terminal 4: Monitoring
watch -n 1 'ps aux | grep python | grep -v grep'
```

---

## 7. Xulosa

**Eng muhim test:** Haqiqiy userlar bilan test qilish!

1. Backend API load test qiling (500-1000 requests)
2. Database performance test qiling (700+ records)
3. Bot monitoring qiling (real-time)
4. Haqiqiy userlar bilan test qiling (5-10 user)
5. Natijalarni tahlil qiling va optimizatsiya qiling

**Muvaffaqiyat mezonlari:**
- ✅ 500 user bir vaqtda ro'yxatdan o'ta oladi
- ✅ Response time < 2 second
- ✅ Success rate > 95%
- ✅ Bot 24/7 ishlab turadi
- ✅ Xotira va CPU normal darajada

---

**Muallif:** GitHub Copilot
**Sana:** 2025-11-12
