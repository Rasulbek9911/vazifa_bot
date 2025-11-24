# FIX: API Connection Error - Cannot connect to host

## ❌ Error:
```
aiohttp.client_exceptions.ClientConnectorError: 
Cannot connect to host 45.138.0.159:37 ssl:default [Connect call failed ('45.138.0.159', 37)]
```

## 🔍 Problem Analysis:

1. **Wrong API URL**: Bot trying to connect to `45.138.0.159:37` (external IP with wrong port)
2. **Expected**: Should connect to `http://127.0.0.1:8000/api` (local Django server)
3. **Root Cause**: Server's `.env` file has incorrect `API_BASE_URL`

---

## ✅ SOLUTION:

### Step 1: Check Server .env File

```bash
# On server:
cd /var/www/vazifa_bot/mukammal-bot-paid
cat .env
```

**Expected content:**
```bash
ADMINS=1062271566
BOT_TOKEN=1650343704:AAF1LpJZMoZ25fV5OjYJ4CvwDncJryljtDk
ip=localhost
API_BASE_URL=http://127.0.0.1:8000/api
```

**Current (WRONG) content might be:**
```bash
API_BASE_URL=http://45.138.0.159:37/api  # ❌ WRONG!
```

---

### Step 2: Fix .env File

```bash
# On server:
cd /var/www/vazifa_bot/mukammal-bot-paid

# Edit .env file
nano .env

# Change API_BASE_URL to:
API_BASE_URL=http://127.0.0.1:8000/api

# Save: Ctrl+X, then Y, then Enter
```

Or use sed to replace:
```bash
cd /var/www/vazifa_bot/mukammal-bot-paid
sed -i 's|API_BASE_URL=.*|API_BASE_URL=http://127.0.0.1:8000/api|' .env
```

---

### Step 3: Verify Django Server is Running

```bash
# Check if Django/Gunicorn is running
sudo systemctl status gunicorn

# If not running, start it:
sudo systemctl start gunicorn

# Check port 8000 is listening
sudo netstat -tlnp | grep 8000
# Should show: tcp  0  0  127.0.0.1:8000  0.0.0.0:*  LISTEN

# Or use curl to test:
curl http://127.0.0.1:8000/api/students/
# Should return JSON response
```

---

### Step 4: Restart Bot Service

```bash
# After fixing .env:
sudo systemctl restart vazifa_bot
sudo systemctl status vazifa_bot

# Check logs:
sudo journalctl -u vazifa_bot -n 50 --no-pager
```

---

## 🔧 Complete Fix Commands:

```bash
# 1. Fix .env file
cd /var/www/vazifa_bot/mukammal-bot-paid
cat > .env << 'EOF'
ADMINS=1062271566
BOT_TOKEN=1650343704:AAF1LpJZMoZ25fV5OjYJ4CvwDncJryljtDk
ip=localhost
API_BASE_URL=http://127.0.0.1:8000/api
GENERAL_CHANNEL_ID=-1003295943458
GENERAL_CHANNEL_INVITE_LINK=https://t.me/+Pa-WbbL1s0c3NmYy
EOF

# 2. Make sure Django is running
sudo systemctl status gunicorn
# If stopped:
sudo systemctl start gunicorn

# 3. Test API connection
curl http://127.0.0.1:8000/api/groups/

# 4. Restart bot
sudo systemctl restart vazifa_bot

# 5. Monitor logs
sudo journalctl -u vazifa_bot -f
```

---

## 🎯 Why This Happened:

1. **Incorrect .env on server**: API_BASE_URL pointing to external IP
2. **Port mismatch**: Port 37 instead of 8000
3. **Network issue**: Trying to connect externally instead of localhost

---

## ✅ After Fix - Expected Behavior:

### Logs should show:
```
✅ Successfully connected to API
✅ Bot polling started
✅ Ready to receive messages
```

### No more errors like:
```
❌ Cannot connect to host 45.138.0.159:37
```

---

## 🧪 Testing:

```bash
# 1. Check API is accessible
curl http://127.0.0.1:8000/api/students/

# 2. Check bot can connect
sudo journalctl -u vazifa_bot -n 20 --no-pager | grep -i "error\|success"

# 3. Send /start to bot on Telegram
# Should work without connection errors
```

---

## 📋 Checklist:

- [ ] `.env` file has correct `API_BASE_URL=http://127.0.0.1:8000/api`
- [ ] Django/Gunicorn service is running (`sudo systemctl status gunicorn`)
- [ ] Port 8000 is listening (`sudo netstat -tlnp | grep 8000`)
- [ ] Bot service restarted (`sudo systemctl restart vazifa_bot`)
- [ ] No connection errors in logs (`sudo journalctl -u vazifa_bot -f`)
- [ ] `/start` command works in Telegram

---

**Priority**: 🔴 CRITICAL - Bot cannot work without API connection
**Fix Time**: ~2 minutes
**Difficulty**: Easy (just .env file correction)
