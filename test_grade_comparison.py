#!/usr/bin/env python3
"""
Compare OLD vs NEW admin answers and calculate grade change
"""
import re

# Ma'lumotlar
student_answers_raw = "dbcaabaabadacddbcabcaddbadbbdccbbcc"
old_admin_answers = "1d2b3c4a5a6b7a8a9b10a11d12a13c14d15d16b17c18a19b20c21a22d23d24b25a26d27b28b29d30c31c32b33c34c35c"
new_admin_answers = "1d2c3c4a5a6c7a8a9b10a11d12a13c14d15d16b17c18a19b20c21a22d23d24b25a26d27b28x29d30c31c32b33b34c35c"

print("=" * 80)
print("GRADE COMPARISON: OLD vs NEW")
print("=" * 80)

# Student javoblarini parse qilish
student_answers = student_answers_raw.lower().strip()
if '-' in student_answers:
    parts = student_answers.split('-', 1)
    if len(parts) == 2 and parts[0].replace('_', '').isdigit():
        student_answers = parts[1]

student_answers_list = list(student_answers)
print(f"\n📋 Student answers ({len(student_answers_list)} ta): {student_answers_raw}")

# OLD admin javoblarini parse qilish
old_correct_list = []
for match in re.finditer(r'\d+([a-zx]+)', old_admin_answers):
    answers = match.group(1)
    old_correct_list.append(['x'] if answers == 'x' else list(answers))

print(f"\n❌ OLD admin answers ({len(old_correct_list)} ta): {old_admin_answers}")

# NEW admin javoblarini parse qilish
new_correct_list = []
for match in re.finditer(r'\d+([a-zx]+)', new_admin_answers):
    answers = match.group(1)
    new_correct_list.append(['x'] if answers == 'x' else list(answers))

print(f"✅ NEW admin answers ({len(new_correct_list)} ta): {new_admin_answers}")

# OLD baho hisoblash
old_correct_count = 0
old_bekor = 0
for i in range(len(old_correct_list)):
    student_ans = student_answers_list[i]
    correct_ans = old_correct_list[i]
    if correct_ans == ['x']:
        old_correct_count += 1
        old_bekor += 1
    elif student_ans in correct_ans:
        old_correct_count += 1

# NEW baho hisoblash
new_correct_count = 0
new_bekor = 0
for i in range(len(new_correct_list)):
    student_ans = student_answers_list[i]
    correct_ans = new_correct_list[i]
    if correct_ans == ['x']:
        new_correct_count += 1
        new_bekor += 1
    elif student_ans in correct_ans:
        new_correct_count += 1

print(f"\n" + "=" * 80)
print("DETAILED COMPARISON:")
print("=" * 80)
print(f"{'#':<4} {'Student':<8} {'OLD':<8} {'NEW':<8} {'OLD Result':<12} {'NEW Result':<12} {'Status':<10}")
print("-" * 80)

changes = []
for i in range(len(student_answers_list)):
    student_ans = student_answers_list[i]
    old_ans = ''.join(old_correct_list[i]) if old_correct_list[i] != ['x'] else 'x'
    new_ans = ''.join(new_correct_list[i]) if new_correct_list[i] != ['x'] else 'x'
    
    # OLD result
    if old_correct_list[i] == ['x']:
        old_result = "✓ BEKOR"
    elif student_ans in old_correct_list[i]:
        old_result = "✓"
    else:
        old_result = "✗"
    
    # NEW result
    if new_correct_list[i] == ['x']:
        new_result = "✓ BEKOR"
    elif student_ans in new_correct_list[i]:
        new_result = "✓"
    else:
        new_result = "✗"
    
    # Status
    if old_result != new_result or old_ans != new_ans:
        status = "CHANGED"
        changes.append(i+1)
        print(f"{i+1:<4} {student_ans:<8} {old_ans:<8} {new_ans:<8} {old_result:<12} {new_result:<12} {status:<10}")

print("-" * 80)

print(f"\n" + "=" * 80)
print("SUMMARY:")
print("=" * 80)
print(f"📊 OLD Grade: {old_correct_count}/{len(old_correct_list)} (bekor: {old_bekor})")
print(f"📊 NEW Grade: {new_correct_count}/{len(new_correct_list)} (bekor: {new_bekor})")
print(f"📈 Difference: {new_correct_count - old_correct_count:+d} ball")
print(f"🔄 Changed questions: {len(changes)} ta - {changes}")
print("=" * 80)
