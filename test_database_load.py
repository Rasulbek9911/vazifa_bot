"""
Database Bulk Insert Test
700 ta dummy student yaratish va performance test
"""
import os
import sys
import django
import time
from datetime import datetime

# Django setup
sys.path.append('/home/rasulbek/Projects/vazifa_bot')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from base_app.models import Group, Student, Topic, Task


def create_test_group():
    """Test guruh yaratish"""
    group, created = Group.objects.get_or_create(
        name="Test Group 700",
        defaults={
            'telegram_group_id': '-1001234567890',
            'invite_link': 'https://t.me/+test700'
        }
    )
    if created:
        print(f"✅ Yangi guruh yaratildi: {group.name}")
    else:
        print(f"ℹ️  Guruh allaqachon mavjud: {group.name}")
    return group


def bulk_create_students(group, count=700):
    """Bulk insert bilan studentlar yaratish"""
    print(f"\n{'='*60}")
    print(f"BULK INSERT TEST - {count} students")
    print(f"{'='*60}")
    
    # Mavjud studentlarni o'chirish (test uchun)
    existing_count = Student.objects.filter(telegram_id__startswith='test_').count()
    if existing_count > 0:
        confirm = input(f"\n⚠️  {existing_count} ta test student mavjud. O'chirilsinmi? (y/n): ")
        if confirm.lower() == 'y':
            Student.objects.filter(telegram_id__startswith='test_').delete()
            print(f"✅ {existing_count} ta test student o'chirildi")
    
    print(f"\n📊 {count} ta student yaratilmoqda...")
    start_time = time.time()
    
    students = []
    for i in range(count):
        students.append(Student(
            telegram_id=f"test_{100000 + i}",
            full_name=f"Test Student {i+1}",
            group=group
        ))
    
    # Bulk create with batch_size
    Student.objects.bulk_create(students, batch_size=100)
    
    elapsed = time.time() - start_time
    
    print(f"✅ {count} ta student yaratildi!")
    print(f"⏱️  Vaqt: {elapsed:.2f} soniya")
    print(f"📈 Speed: {count/elapsed:.0f} records/second")
    print(f"{'='*60}")
    
    # Verification
    total = Student.objects.filter(telegram_id__startswith='test_').count()
    print(f"\n✅ Verification: {total} ta test student database da")
    
    return total


def test_query_performance(group):
    """Query performance test"""
    print(f"\n{'='*60}")
    print(f"QUERY PERFORMANCE TEST")
    print(f"{'='*60}")
    
    # Test 1: Count query
    print("\n1️⃣  Count query:")
    start = time.time()
    count = Student.objects.filter(group=group).count()
    elapsed = time.time() - start
    print(f"   Result: {count} students")
    print(f"   Time: {elapsed*1000:.2f} ms")
    
    # Test 2: List query
    print("\n2️⃣  List query (first 100):")
    start = time.time()
    students = list(Student.objects.filter(group=group)[:100])
    elapsed = time.time() - start
    print(f"   Result: {len(students)} students")
    print(f"   Time: {elapsed*1000:.2f} ms")
    
    # Test 3: Prefetch related
    print("\n3️⃣  Prefetch related query:")
    start = time.time()
    students = list(Student.objects.filter(group=group).select_related('group')[:100])
    elapsed = time.time() - start
    print(f"   Result: {len(students)} students with group data")
    print(f"   Time: {elapsed*1000:.2f} ms")
    
    # Test 4: Filter query
    print("\n4️⃣  Filter query (name contains 'Test'):")
    start = time.time()
    students = list(Student.objects.filter(
        group=group,
        full_name__icontains='Test'
    )[:100])
    elapsed = time.time() - start
    print(f"   Result: {len(students)} students")
    print(f"   Time: {elapsed*1000:.2f} ms")
    
    print(f"\n{'='*60}")


def generate_pdf_report_test(group):
    """PDF report generatsiyasi test (agar backend API ishlasa)"""
    print(f"\n{'='*60}")
    print(f"PDF REPORT GENERATION TEST")
    print(f"{'='*60}")
    
    try:
        import requests
        
        print("\n📄 PDF report yaratilmoqda...")
        start = time.time()
        
        response = requests.get(
            f"http://127.0.0.1:8000/api/reports/{group.id}/weekly/pdf/",
            timeout=30
        )
        
        elapsed = time.time() - start
        
        if response.status_code == 200:
            pdf_size = len(response.content)
            print(f"✅ PDF yaratildi!")
            print(f"   Size: {pdf_size/1024:.2f} KB")
            print(f"   Time: {elapsed:.2f} seconds")
            
            # Save PDF
            filename = f"test_report_700_users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            with open(filename, 'wb') as f:
                f.write(response.content)
            print(f"   Saved: {filename}")
        else:
            print(f"❌ PDF yaratishda xatolik: {response.status_code}")
    
    except requests.exceptions.ConnectionError:
        print("❌ Backend server ishlamayapti!")
        print("   Ishga tushiring: python3 manage.py runserver")
    except Exception as e:
        print(f"❌ Xatolik: {e}")
    
    print(f"{'='*60}")


def cleanup_test_data():
    """Test ma'lumotlarni tozalash"""
    print(f"\n{'='*60}")
    print(f"CLEANUP TEST DATA")
    print(f"{'='*60}")
    
    count = Student.objects.filter(telegram_id__startswith='test_').count()
    if count > 0:
        confirm = input(f"\n⚠️  {count} ta test student o'chirilsinmi? (y/n): ")
        if confirm.lower() == 'y':
            start = time.time()
            Student.objects.filter(telegram_id__startswith='test_').delete()
            elapsed = time.time() - start
            print(f"✅ {count} ta student o'chirildi ({elapsed:.2f}s)")
    else:
        print("ℹ️  Test ma'lumotlar topilmadi")
    
    print(f"{'='*60}")


def main():
    """Asosiy test funksiyasi"""
    print("\n" + "="*60)
    print("DATABASE LOAD TESTING - 700 USERS")
    print("="*60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Menu
    print("\nTest options:")
    print("1. Bulk create 700 students")
    print("2. Query performance test")
    print("3. PDF report generation test")
    print("4. Full test (1+2+3)")
    print("5. Cleanup test data")
    print("6. Exit")
    
    choice = input("\nTanlang (1-6): ").strip()
    
    if choice == "1":
        group = create_test_group()
        bulk_create_students(group, 700)
    
    elif choice == "2":
        group = Group.objects.filter(name="Test Group 700").first()
        if group:
            test_query_performance(group)
        else:
            print("❌ Test guruh topilmadi. Avval option 1 ni ishlating.")
    
    elif choice == "3":
        group = Group.objects.filter(name="Test Group 700").first()
        if group:
            generate_pdf_report_test(group)
        else:
            print("❌ Test guruh topilmadi. Avval option 1 ni ishlating.")
    
    elif choice == "4":
        group = create_test_group()
        bulk_create_students(group, 700)
        test_query_performance(group)
        generate_pdf_report_test(group)
    
    elif choice == "5":
        cleanup_test_data()
    
    elif choice == "6":
        print("\n👋 Xayr!")
        return
    
    else:
        print("❌ Noto'g'ri tanlov!")
    
    print("\n" + "="*60)
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test to'xtatildi!")
    except Exception as e:
        print(f"\n❌ Xatolik: {e}")
        import traceback
        traceback.print_exc()
