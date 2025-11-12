# PRODUCTION DEPLOYMENT - 2 CPU cores, 2GB RAM Server

## ✅ BAJARILGAN:
- [x] PostgreSQL o'rnatildi va sozlandi
- [x] SQLite dan migratsiya
- [x] 701 student, 3 guruh, 1 task import qilindi
- [x] Load test: 1500 user registration - SUCCESS!
- [x] Server yangilandi: 2 CPU cores, 2GB RAM, 40GB NVME

## 🎯 SERVER SPECIFICATIONS:
- **CPU**: 2 cores
- **RAM**: 2GB
- **Disk**: 40GB NVME
- **Network**: 200Mb/s TAS-IX + 200Mb/s Internet
- **Expected Load**: 1000-2000 concurrent users

---

## 🚀 KEYINGI QADAMLAR:

### 1. **Gunicorn o'rnatish (MUHIM!)**

```bash
# Virtual environment da
pip install gunicorn gevent

# gunicorn_config.py yaratish
cat > gunicorn_config.py << 'EOF'
# Gunicorn konfiguratsiyasi - 2 CPU cores, 2GB RAM uchun
import multiprocessing

# Server socket
bind = "127.0.0.1:8000"
backlog = 2048

# Workers
workers = 5  # (2 * CPU_cores) + 1 = 5
worker_class = "gevent"  # Async workers (blocking I/O uchun yaxshi)
worker_connections = 1000
max_requests = 1000  # Worker restart (memory leak oldini olish)
max_requests_jitter = 100
timeout = 30
keepalive = 5

# Logging
accesslog = "/home/rasulbek/logs/gunicorn_access.log"
errorlog = "/home/rasulbek/logs/gunicorn_error.log"
loglevel = "info"

# Process naming
proc_name = "vazifa_bot"

# Server mechanics
daemon = False
pidfile = "/tmp/gunicorn_vazifa_bot.pid"
EOF

# Log papkasini yaratish
mkdir -p /home/rasulbek/logs

# Test
gunicorn config.wsgi:application -c gunicorn_config.py
```

---

### 2. **Nginx o'rnatish va sozlash**

```bash
# Nginx o'rnatish
sudo apt install nginx -y

# Konfiguratsiya
sudo nano /etc/nginx/sites-available/vazifa_bot

# Quyidagini qo'shing:
server {
    listen 80;
    server_name your-domain.com;  # yoki server IP

    # Static files
    location /static/ {
        alias /home/rasulbek/Projects/vazifa_bot/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /home/rasulbek/Projects/vazifa_bot/media/;
    }

    # Django backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }

    # Compression
    gzip on;
    gzip_comp_level 5;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;

    # Client body size (vazifa fayllari uchun)
    client_max_body_size 10M;
}

# Enable site
sudo ln -s /etc/nginx/sites-available/vazifa_bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Nginx global konfiguratsiya (2 CPU cores uchun)
sudo nano /etc/nginx/nginx.conf
# worker_processes ni o'zgartiring:
worker_processes 2;
events {
    worker_connections 2048;
}
```

---

### 3. **PostgreSQL tuning (2GB RAM)**

```bash
# PostgreSQL konfiguratsiya
sudo nano /etc/postgresql/16/main/postgresql.conf

# Quyidagilarni qo'shing/o'zgartiring:
shared_buffers = 512MB                    # 2GB RAM uchun
effective_cache_size = 1536MB             # 2GB RAM * 0.75
maintenance_work_mem = 128MB              # 2GB RAM uchun
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
work_mem = 8MB                            # 2GB RAM uchun
min_wal_size = 1GB
max_wal_size = 4GB
max_connections = 200                     # 2GB RAM uchun oshirildi

# Restart
sudo systemctl restart postgresql
```

---

### 4. **Redis o'rnatish (Caching)**

```bash
# Redis o'rnatish
sudo apt install redis-server -y

# Konfiguratsiya
sudo nano /etc/redis/redis.conf

# Quyidagilarni qo'shing:
maxmemory 256mb                           # 2GB RAM uchun oshirildi
maxmemory-policy allkeys-lru

# Restart
sudo systemctl restart redis

# Python package
pip install redis django-redis
```

**Django settings.py ga qo'shing:**

```python
# Cache
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# Session cache
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
```

---

### 5. **Django production settings**

```python
# config/settings.py

DEBUG = False
ALLOWED_HOSTS = ['your-domain.com', 'your-ip', 'localhost']

# Security
SECRET_KEY = 'your-new-secret-key-here-generate-new-one'
SECURE_SSL_REDIRECT = False  # Agar HTTPS bo'lsa True
SESSION_COOKIE_SECURE = False  # Agar HTTPS bo'lsa True
CSRF_COOKIE_SECURE = False  # Agar HTTPS bo'lsa True

# Static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATIC_URL = '/static/'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/home/rasulbek/logs/django.log',
            'maxBytes': 1024 * 1024 * 10,  # 10MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# Database connection pooling
DATABASES['default']['CONN_MAX_AGE'] = 600
DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 10,
    'options': '-c statement_timeout=30000'
}
```

---

### 6. **Systemd service yaratish**

```bash
# Service fayli
sudo nano /etc/systemd/system/vazifa_bot.service

# Quyidagini qo'shing:
[Unit]
Description=Vazifa Bot Gunicorn daemon
After=network.target postgresql.service redis.service

[Service]
Type=notify
User=rasulbek
Group=rasulbek
WorkingDirectory=/home/rasulbek/Projects/vazifa_bot
Environment="PATH=/home/rasulbek/Projects/vazifa_bot/venv/bin"
ExecStart=/home/rasulbek/Projects/vazifa_bot/venv/bin/gunicorn config.wsgi:application -c gunicorn_config.py
ExecReload=/bin/kill -s HUP $MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=on-failure

[Install]
WantedBy=multi-user.target

# Enable va start
sudo systemctl daemon-reload
sudo systemctl enable vazifa_bot
sudo systemctl start vazifa_bot
sudo systemctl status vazifa_bot
```

---

### 7. **Bot servisi (aiogram)**

```bash
# Bot uchun alohida service
sudo nano /etc/systemd/system/vazifa_bot_telegram.service

[Unit]
Description=Vazifa Bot Telegram aiogram
After=network.target vazifa_bot.service

[Service]
Type=simple
User=rasulbek
Group=rasulbek
WorkingDirectory=/home/rasulbek/Projects/vazifa_bot/mukammal-bot-paid
Environment="PATH=/home/rasulbek/Projects/vazifa_bot/venv/bin"
ExecStart=/home/rasulbek/Projects/vazifa_bot/venv/bin/python app.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target

# Enable va start
sudo systemctl daemon-reload
sudo systemctl enable vazifa_bot_telegram
sudo systemctl start vazifa_bot_telegram
sudo systemctl status vazifa_bot_telegram
```

---

### 8. **Monitoring setup**

```bash
# htop o'rnatish
sudo apt install htop -y

# Monitoring skripti
cat > /home/rasulbek/monitor.sh << 'EOF'
#!/bin/bash
echo "=== Vazifa Bot Monitoring ==="
echo "Time: $(date)"
echo ""
echo "=== System Resources ==="
free -h
df -h | grep -E "/$|/home"
echo ""
echo "=== PostgreSQL ==="
sudo systemctl status postgresql --no-pager | head -3
echo ""
echo "=== Redis ==="
sudo systemctl status redis --no-pager | head -3
echo ""
echo "=== Gunicorn ==="
sudo systemctl status vazifa_bot --no-pager | head -5
echo ""
echo "=== Telegram Bot ==="
sudo systemctl status vazifa_bot_telegram --no-pager | head -5
EOF

chmod +x /home/rasulbek/monitor.sh

# Test
./monitor.sh
```

---

### 9. **Backup setup**

```bash
# Daily backup skripti
cat > /home/rasulbek/backup_db.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/rasulbek/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# PostgreSQL backup
PGPASSWORD='vazifa_bot_2025' pg_dump -U vazifa_user -h localhost vazifa_bot > "$BACKUP_DIR/db_$DATE.sql"

# Django dumpdata (JSON)
cd /home/rasulbek/Projects/vazifa_bot
source venv/bin/activate
python manage.py dumpdata --indent 2 > "$BACKUP_DIR/data_$DATE.json"

# Eski backuplarni o'chirish (30 kundan eski)
find $BACKUP_DIR -type f -mtime +30 -delete

echo "Backup completed: $DATE"
EOF

chmod +x /home/rasulbek/backup_db.sh

# Cron job (har kuni 3:00 da)
crontab -e
# Quyidagini qo'shing:
0 3 * * * /home/rasulbek/backup_db.sh >> /home/rasulbek/logs/backup.log 2>&1
```

---

### 10. **SSL (HTTPS) - Let's Encrypt**

```bash
# Certbot o'rnatish
sudo apt install certbot python3-certbot-nginx -y

# SSL sertifikat olish
sudo certbot --nginx -d your-domain.com

# Auto-renewal test
sudo certbot renew --dry-run
```

---

## 📊 KUTILAYOTGAN NATIJALAR (Production - 2 CPU, 2GB RAM):

| Metric | Dev | Production (Gunicorn+Nginx) |
|--------|-----|----------------------------|
| API throughput | 116 req/sec | 500-800 req/sec |
| Response time | 323ms | 50-150ms |
| Max concurrent users | 200 | 1000-2000 |
| Database queries/sec | ~100 | 1000-1500 |
| CPU usage | 5% | 40-60% |
| RAM usage | 47% | 65-80% |

---

## ⚠️  CRITICAL CHECKS:

- [ ] DEBUG = False
- [ ] SECRET_KEY o'zgartirilgan
- [ ] ALLOWED_HOSTS to'g'ri
- [ ] PostgreSQL backup daily
- [ ] Monitoring ishlayapti
- [ ] Nginx + Gunicorn ishlayapti (5 workers)
- [ ] SSL sertifikat (agar domain bo'lsa)
- [ ] Firewall sozlangan
- [ ] Log rotation sozlangan
- [ ] Redis cache ishlayapti

---

## 🎯 2GB RAM SERVER UCHUN XULOSA:

✅ **1000 users:** YAXSHI ishlamoqda
✅ **2000 users:** YETARLI (monitoring bilan)
⚠️ **3000+ users:** Maksimal (4GB RAM tavsiya qilinadi)

### 📈 RAM TAQSIMOTI:
- Django + Gunicorn (5 workers): ~400-500MB
- PostgreSQL (shared_buffers=512MB): ~600-700MB
- Redis (maxmemory=256MB): ~256MB
- System + Other: ~300-400MB
- Available (cache/buffer): ~400-600MB

### 💡 OPTIMIZATSIYA IMKONIYATLARI:
1. **3000+ users uchun:**
   - 4GB RAM ga oshirish
   - Horizontal scaling (load balancer + 2 server)
   - CDN ishlatish (static files uchun)

2. **Database optimization:**
   - Index qo'shish (telegram_id, group_id)
   - Query optimization
   - Connection pooling (PgBouncer)

3. **Caching strategy:**
   - API response caching (Redis)
   - Database query caching
   - Session caching

---

Agar savol bo'lsa, so'rang! 🚀
