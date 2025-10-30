# Umumiy Guruh Link Muammosini Tuzatish

## 🔍 Diagnostika

Botni ishga tushiring va ro'yxatdan o'ting. Terminal loglarida quyidagilarni qidiring:

### 1. Bot statusini tekshirish:
```
🔍 Umumiy guruhdagi bot statusini tekshirish... (chat_id=-1003273702109)
   Bot statusi: administrator  ✅ YOK
```

Agar bot **administrator** bo'lmasa:
- ❌ Umumiy guruhga botni admin qiling
- ✅ "Invite users via link" ruxsatini yoqing

### 2. Link yaratish xatosini tekshirish:
```
❌ XATOLIK: Umumiy guruh uchun link yaratib bo'lmadi (chat_id=-1003273702109)
   Xato turi: <XatoNomi>
   Xato matni: <XatoSababi>
```

### Mumkin bo'lgan xatolar:

#### A) "Chat not found"
**Sabab:** Group ID noto'g'ri yoki bot guruhda emas
**Yechim:** 
1. Umumiy guruhga `/my_id` yoki shunga o'xshash bot qo'ying
2. Chat ID ni tekshiring
3. GENERAL_GROUP_ID ni to'g'ri ID bilan almashtiring

#### B) "Not enough rights to manage chat invite link"
**Sabab:** Bot admin emas yoki ruxsati yo'q
**Yechim:**
1. Botni guruhda admin qiling
2. "Invite users via link" ruxsatini bering

#### C) Link yaratiladi lekin invalid
**Sabab:** Guruhning sozlamalari (approve members, etc.)
**Yechim:**
1. Guruh sozlamalarida "Approve new members" ni o'chiring
2. Guruh Public bo'lsa, Private qiling (yoki aksincha)

## 🔧 Keyingi qadamlar:

1. **Loglarni yuboring** - Terminal chiqishini to'liq ko'rsating
2. **Bot admin ekanligini tasdiqlang** - Umumiy guruhda bot adminmi?
3. **Ruxsatlarni tekshiring** - Bot "Invite users via link" ga ega mi?

## 📝 Qo'shimcha test:

Agar muammo davom etsa, `user_registration.py` da quyidagi kodni qo'shing:

```python
# Test: Guruh haqida ma'lumot olish
try:
    chat_info = await bot.get_chat(GENERAL_GROUP_ID)
    print(f"📋 Guruh info:")
    print(f"   Title: {chat_info.title}")
    print(f"   Type: {chat_info.type}")
    print(f"   Username: {chat_info.username}")
except Exception as e:
    print(f"❌ Guruh haqida ma'lumot ololmadik: {e}")
```
