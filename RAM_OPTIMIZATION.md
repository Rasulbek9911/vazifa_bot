# RAM OPTIMIZATION GUIDE - 2GB Server

## 🔴 MUAMMO: RAM 97.6% ishlatilmoqda!

### Test natijalari:
- ✅ 1500 users registered successfully
- ✅ Speed: 489.9 users/sec (JUDA YAXSHI!)
- ❌ RAM: 1.87 GB / 1.92 GB (97.6%) - CRITICAL!
- ⚠️ PostgreSQL connections: 51 (normal)

---

## 🎯 HAL QILISH STRATEGIYASI:

### 1. **SWAP FILE yaratish (MUHIM!)**

2GB RAM yetarli emas, swap file qo'shamiz:

```bash
# 4GB swap file yaratish
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Permanent qilish
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Swappiness sozlash (10 = kamroq swap ishlatadi)
sudo sysctl vm.swappiness=10
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf

# Tekshirish
free -h
```

---

### 2. **PostgreSQL Memory Tuning**

2GB RAM uchun PostgreSQL sozlamalarini kamaytirish:

```bash
sudo nano /etc/postgresql/16/main/postgresql.conf

# O'zgartiring:
shared_buffers = 384MB              # 512MB → 384MB (RAM 19%)
effective_cache_size = 1152MB       # 1536MB → 1152MB
work_mem = 6MB                      # 8MB → 6MB
maintenance_work_mem = 96MB         # 128MB → 96MB
max_connections = 150               # 200 → 150

# Restart
sudo systemctl restart postgresql
```

---

### 3. **Gunicorn Workers kamaytirish**

5 workers → 4 workers (RAM tejash):

```python
# gunicorn_config.py
workers = 4  # 5 → 4 (har biri ~100-120MB)
worker_class = "gevent"
worker_connections = 1000
max_requests = 800  # 1000 → 800 (tez-tez restart)
timeout = 25  # 30 → 25
```

---

### 4. **Redis Memory Limit kamaytirish**

```bash
sudo nano /etc/redis/redis.conf

# O'zgartiring:
maxmemory 192mb  # 256MB → 192MB
maxmemory-policy allkeys-lru

# Restart
sudo systemctl restart redis
```

---

### 5. **Python Memory Optimization**

```python
# config/settings.py ga qo'shing:

# Database connection pooling
DATABASES = {
    'default': {
        # ... existing config ...
        'CONN_MAX_AGE': 300,  # 600 → 300 (kamroq connection)
        'OPTIONS': {
            'connect_timeout': 10,
            'options': '-c statement_timeout=10000',  # 10s query timeout
        },
    }
}

# Query optimization
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',  # DEBUG → WARNING (kam log)
        },
    },
}

# Middleware optimization (keraksizlarini o'chirish)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    # 'django.middleware.clickjacking.XFrameOptionsMiddleware',  # O'chirish mumkin
]
```

---

### 6. **Bot Memory Optimization**

```python
# mukammal-bot-paid/loader.py
from aiogram import Bot, Dispatcher
from aiogram.contrib.fsm_storage.redis import RedisStorage2

# Redis storage (RAM tejaydi)
storage = RedisStorage2(
    host='localhost',
    port=6379,
    db=1,  # Django dan ajratish
    pool_size=10,  # 20 → 10
)

bot = Bot(token=BOT_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=storage)
```

---

### 7. **Monitoring va Auto-cleanup Script**

```bash
# /home/rasulbek/monitor_ram.sh
#!/bin/bash

RAM_PERCENT=$(free | grep Mem | awk '{print int($3/$2 * 100)}')

if [ $RAM_PERCENT -gt 85 ]; then
    echo "[$(date)] RAM 85% dan oshdi: $RAM_PERCENT%" >> /home/rasulbek/logs/ram_monitor.log
    
    # Django/Bot restart (memory leak bo'lsa)
    sudo systemctl restart gunicorn
    sudo systemctl restart vazifa_bot
    
    # Cache tozalash
    echo 3 | sudo tee /proc/sys/vm/drop_caches
fi

# Cron: har 5 daqiqada
# */5 * * * * /home/rasulbek/monitor_ram.sh
```

---

## 📊 OPTIMIZATSIYADAN KEYIN KUTILGAN NATIJALAR:

| Resource | Oldin | Keyin | Status |
|----------|-------|-------|--------|
| Django + Gunicorn (4 workers) | ~500MB | ~400MB | ✅ |
| PostgreSQL (384MB buffers) | ~600MB | ~500MB | ✅ |
| Redis (192MB) | ~256MB | ~192MB | ✅ |
| Bot + System | ~400MB | ~350MB | ✅ |
| **Total Used** | ~1.87GB | ~1.44GB | ✅ |
| **Free RAM** | ~50MB | ~480MB | ✅ |
| **RAM Usage** | 97.6% | ~75% | ✅ |
| **+ Swap** | 0 | 4GB | ✅ |

---

## 🚀 DEPLOYMENT KETMA-KETLIGI:

```bash
# 1. Swap file yaratish
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
sudo sysctl vm.swappiness=10

# 2. PostgreSQL tuning
sudo nano /etc/postgresql/16/main/postgresql.conf
# (yuqoridagi sozlamalarni qo'shing)
sudo systemctl restart postgresql

# 3. Redis tuning
sudo nano /etc/redis/redis.conf
# (maxmemory 192mb)
sudo systemctl restart redis

# 4. Gunicorn workers kamaytirish
nano /home/rasulbek/Projects/vazifa_bot/gunicorn_config.py
# (workers = 4)

# 5. Test qiling
python3 test_production_load.py
# Option 4: 1500 users test
```

---

## 💡 QACHON RAM YETARLI?

✅ **1000-1500 users:** RAM ~75% (YAXSHI)
⚠️ **2000-2500 users:** RAM ~85% (MONITORING KERAK)
❌ **3000+ users:** 4GB RAM kerak yoki horizontal scaling

---

## 🎯 XULOSA:

**Hozirgi holat:**
- 2GB RAM juda yetarli, lekin optimization kerak
- Swap file qo'shish MUHIM!
- PostgreSQL va Gunicorn sozlamalarini kamaytirish

**Optimizatsiya keyin:**
- 1500 users bir vaqtda: RAM ~75% (SAFE)
- 2000 users bir vaqtda: RAM ~85% (OK with swap)
- 3000+ users: 4GB RAM tavsiya qilinadi

**Test natijalaringiz AJOYIB:**
- ✅ 489.9 users/sec speed
- ✅ 0 errors
- ✅ PostgreSQL ishlayapti (51 connections - normal)
- ⚠️ Faqat RAM optimization kerak!
