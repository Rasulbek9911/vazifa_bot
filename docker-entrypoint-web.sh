#!/bin/sh
set -e

echo "DB tayyor bo'lishini kutyapmiz ($DB_HOST:$DB_PORT)..."
python - <<'PYEOF'
import os
import socket
import time

host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", "5432"))

for _ in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"DB {host}:{port} ga ulanib bo'lmadi (timeout)")
PYEOF

echo "Migratsiyalar ishga tushirilmoqda..."
python manage.py migrate --noinput

echo "Static fayllar yig'ilmoqda..."
python manage.py collectstatic --noinput

echo "Gunicorn ishga tushirilmoqda..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
