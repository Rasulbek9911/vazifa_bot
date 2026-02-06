# Admin - Yangi Mavzu Qo'shish Qo'llanmasi

## 📋 Imkoniyatlar

Admin uchun yangi mavzu qo'shish funksiyasi qo'shildi. Bu funksiya quyidagi imkoniyatlarni beradi:

1. ✅ Kurs tanlash (Milliy Sertifikat, Attestatsiya va boshqalar)
2. ✅ Mavzu nomi kiritish
3. ✅ Deadline belgilash (ixtiyoriy)
4. ✅ Mavzuni yaratish (default: inactive)
5. ✅ Mavzuni activate qilish

## 🚀 Qanday ishlatish

### 1. Mavzu qo'shish jarayonini boshlash

Admin botda **"➕ Mavzu qo'shish"** tugmasini bosadi.

### 2. Kurs tanlash

Bot barcha faol kurslarni ko'rsatadi:
- Milliy Sertifikat
- Attestatsiya
- va boshqalar...

Admin kerakli kursni tanlaydi.

### 3. Mavzu nomini kiritish

Admin mavzu nomini yozadi, masalan:
- `1-mavzu`
- `2-mavzu`
- `Python asoslari`

### 4. Deadline belgilash (ixtiyoriy)

Bot ikkita variant taklif qiladi:
- **📅 Deadline belgilash** - deadline kiritish
- **⏩ O'tkazib yuborish** - deadline siz davom etish

#### Deadline formatı:
```
KUN.OY.YIL SOAT:DAQIQA
```

Masalan:
- `15.02.2026 23:59`
- `20.03.2026 18:00`

⚠️ **Muhim:** Deadline dan keyin topshirilgan testlar avtomatik ravishda 80% ball oladi.

### 5. Mavzu yaratilishi

Bot yangi mavzuni yaratib, quyidagi ma'lumotlarni ko'rsatadi:
- 📚 Kurs nomi
- 📝 Mavzu nomi
- 🆔 Mavzu ID
- 📅 Deadline (agar belgilangan bo'lsa)
- 🔴 Status: **Inactive**

### 6. Mavzuni aktivlashtirish

Mavzu yaratilgandan so'ng, uni aktivlashtirish uchun:

```
/activate <mavzu_id>
```

Masalan:
```
/activate 15
```

## 🔧 Boshqa buyruqlar

### Barcha mavzularni ko'rish
```
/topics
```

### Bekor qilish
Har qanday bosqichda jarayonni bekor qilish uchun:
```
/cancel
```

## 📊 API Endpoint

Backend'da yangi endpoint qo'shildi:

**POST** `/api/topics/create/`

Request body:
```json
{
  "course_id": 1,
  "title": "1-mavzu",
  "deadline": "2026-02-15T23:59:59+05:00",  // optional
  "is_active": false  // default: false
}
```

Response:
```json
{
  "id": 15,
  "title": "1-mavzu",
  "course": {
    "id": 1,
    "name": "Milliy Sertifikat",
    "code": "milliy_sert"
  },
  "deadline": "2026-02-15T23:59:59+05:00",
  "is_active": false,
  "created_at": "2026-02-06T10:00:00+05:00"
}
```

## 🎯 Workflow

```
Admin → "➕ Mavzu qo'shish"
  ↓
Kurs tanlash (Inline keyboard)
  ↓
Mavzu nomini kiritish
  ↓
Deadline belgilash / O'tkazib yuborish
  ↓
Mavzu yaratildi (Inactive)
  ↓
/activate <id> - Aktivlashtirish
  ↓
Studentlar mavzuni ko'rishadi
```

## 📝 Misollar

### Misol 1: Deadline bilan
```
Admin: "➕ Mavzu qo'shish"
Bot: [Milliy Sertifikat] [Attestatsiya] tanlang

Admin: [Milliy Sertifikat]
Bot: Mavzu nomini yuboring

Admin: "1-mavzu"
Bot: [Deadline belgilash] [O'tkazib yuborish]

Admin: [Deadline belgilash]
Bot: Deadline ni yuboring: KUN.OY.YIL SOAT:DAQIQA

Admin: "15.02.2026 23:59"
Bot: ✅ Yangi mavzu yaratildi!
     📚 Kurs: Milliy Sertifikat
     📝 Mavzu: 1-mavzu
     🆔 ID: 15
     📅 Deadline: 15.02.2026 23:59
     🔴 Status: Inactive
     
     Mavzuni active qilish uchun: /activate 15

Admin: "/activate 15"
Bot: ✅ Mavzu aktivlashtirildi!
```

### Misol 2: Deadline siz
```
Admin: "➕ Mavzu qo'shish"
Bot: [Attestatsiya] tanlang

Admin: [Attestatsiya]
Bot: Mavzu nomini yuboring

Admin: "Python asoslari"
Bot: [Deadline belgilash] [O'tkazib yuborish]

Admin: [O'tkazib yuborish]
Bot: ✅ Yangi mavzu yaratildi!
     📚 Kurs: Attestatsiya
     📝 Mavzu: Python asoslari
     🆔 ID: 16
     📅 Deadline: Yo'q
     🔴 Status: Inactive
     
     Mavzuni active qilish uchun: /activate 16
```

## 🔐 Xavfsizlik

- Faqat ADMINS listidagi foydalanuvchilar mavzu qo'sha oladi
- State orqali ma'lumotlar xavfsiz saqlanadi
- Deadline validatsiyasi qilinadi
- Course mavjudligi tekshiriladi

## 🐛 Xatolarni Bartaraf Qilish

### Xato: "Course topilmadi"
**Sabab:** Course ID noto'g'ri yoki course o'chirilgan
**Yechim:** `/topics` buyrug'i bilan mavjud courslarni tekshiring

### Xato: "Xato format!"
**Sabab:** Deadline noto'g'ri formatda kiritilgan
**Yechim:** `KUN.OY.YIL SOAT:DAQIQA` formatidan foydalaning

### Xato: "Mavzu nomi bo'sh bo'lishi mumkin emas"
**Sabab:** Bo'sh satr yuborilgan
**Yechim:** Mavzu nomini to'liq kiriting

## ✅ Test Qilish

1. Admin botga kiradi
2. "➕ Mavzu qo'shish" tugmasini bosadi
3. Kurs tanlaydi
4. Mavzu nomini kiritadi
5. Deadline belgilaydi (yoki o'tkazib yuboradi)
6. Yangi mavzu yaratilganligini tekshiradi
7. `/activate <id>` bilan aktivlashtiradi
8. Studentlar mavzuni ko'rishini tekshiradi

## 📞 Qo'llab-quvvatlash

Agar muammolar yuzaga kelsa:
1. Botning loglarini tekshiring
2. API endpoint ishlayotganligini tekshiring
3. Database'da yangi mavzu yaratilganligini tekshiring
4. `/cancel` bilan state'ni tozalang va qaytadan urinib ko'ring
