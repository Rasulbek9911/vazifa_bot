#!/usr/bin/env python3
"""
Test answers parsing logic - REAL USER DATA
"""
import re

# Test ma'lumotlari (REAL DATA)
student_answers_raw = "dbcaabaabadacddbcabcaddbadbbdccbbcc"  # User javobi
admin_new_answers = "1d2c3c4a5a6c7a8a9b10a11d12a13c14d15d16b17c18a19b20c21a22d23d24b25a26d27b28x29d30c31c32b33b34c35c"

print("=" * 70)
print("REAL USER DATA - GRADE CALCULATION TEST")
print("=" * 70)

# Student javoblarini parse qilish (hozirgi kod)
student_answers = student_answers_raw.lower().strip()

# FIX: Test kod prefixini olib tashlashprint("\n📋 INPUT DATA:")
print(f"   Student: {student_answers_raw}")
print(f"   Admin:   {admin_new_answers}")

# Student javoblarini parse qilish
student_answers = student_answers_raw.lower().strip()

# Test kod prefixini olib tashlash (agar bor bo'lsa)
if '-' in student_answers:
    parts = student_answers.split('-', 1)
    if len(parts) == 2 and parts[0].replace('_', '').isdigit():
        student_answers = parts[1]

# Student javoblarini list ga aylantirish
has_numbers = bool(re.search(r'\d', student_answers))
student_answers_list = []

if has_numbers:
    for match in re.finditer(r'\d+([a-zx])', student_answers):
        student_answers_list.append(match.group(1))
elif re.match(r'^[a-zx]+$', student_answers):
    student_answers_list = list(student_answers)
else:
    filtered = ''.join(ch for ch in student_answers if ch.isalpha() or ch == 'x')
    student_answers_list = list(filtered)

print(f"\n✅ Student parsed ({len(student_answers_list)} ta): {student_answers_list}")

# Admin javoblarini parse qilish
correct_answers_list = []
for match in re.finditer(r'\d+([a-zx]+)', admin_new_answers):
    answers = match.group(1)
    if answers == 'x':
        correct_answers_list.append(['x'])
    else:
        correct_answers_list.append(list(answers))

print(f"✅ Admin parsed ({len(correct_answers_list)} ta)")

# Baho hisoblash
if len(student_answers_list) != len(correct_answers_list):
    print(f"\n❌ XATO: Javoblar soni mos kelmaydi!")
    print(f"   Student: {len(student_answers_list)} ta")
    print(f"   Admin: {len(correct_answers_list)} ta")
else:
    correct_count = 0
    bekor_count = 0
    wrong_answers = []
    
    print(f"\n📊 DETAILED COMPARISON:")
    print(f"{'No':<4} {'Student':<8} {'Admin':<12} {'Result':<10}")
    print("-" * 40)
    
    for i in range(len(correct_answers_list)):
        student_ans = student_answers_list[i]
        correct_ans_list = correct_answers_list[i]
        
        if correct_ans_list == ['x']:
            result = "✓ BEKOR"
            correct_count += 1
            bekor_count += 1
        elif student_ans in correct_ans_list:
            result = "✓"
            correct_count += 1
        else:
            result = "✗"
            wrong_answers.append(i+1)
        
        # Faqat noto'g'ri yoki bekor javoblarni ko'rsatamiz
        if result != "✓":
            admin_str = ''.join(correct_ans_list) if correct_ans_list != ['x'] else 'x'
            print(f"{i+1:<4} {student_ans:<8} {admin_str:<12} {result:<10}")
    
    print("-" * 40)
    print(f"\n🎯 FINAL RESULT:")
    print(f"   ✅ To'g'ri: {correct_count}/{len(correct_answers_list)}")
    print(f"   🎁 Bekor: {bekor_count} ta savol")
    print(f"   ❌ Noto'g'ri: {len(wrong_answers)} ta")
    if wrong_answers:
        print(f"   ❌ Noto'g'ri savollar: {wrong_answers[:10]}")
    
    print(f"\n📈 GRADE: {correct_count}")

print("\n" + "=" * 70)
