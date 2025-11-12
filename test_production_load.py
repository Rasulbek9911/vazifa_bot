"""
Production Load Test - PostgreSQL + DRF + aiogram
Real server: 2 CPU cores, 2GB RAM, 40GB NVME, 200Mb/s TAS-IX + 200Mb/s Internet
Target: 1000-2000 concurrent users
"""
import os
import sys
import django
import time
import asyncio
import aiohttp
import psutil
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Django setup
sys.path.append('/home/rasulbek/Projects/vazifa_bot')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from base_app.models import Group, Student, Topic, Task
from django.db import connection, connections
from django.db.models import Count


API_BASE_URL = "http://127.0.0.1:8000/api"


def print_header(title):
    """Formatlangan header"""
    print(f"\n{'='*80}")
    print(f"{title:^80}")
    print(f"{'='*80}\n")


def get_system_stats():
    """Server resurslarini ko'rsatish"""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    print(f"🖥️  CPU: {cpu_percent}%")
    print(f"💾 RAM: {memory.used / (1024**3):.2f} GB / {memory.total / (1024**3):.2f} GB ({memory.percent}%)")
    print(f"💿 Disk: {disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB ({disk.percent}%)")
    
    # PostgreSQL connection count
    with connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname='vazifa_bot';")
        pg_connections = cursor.fetchone()[0]
        print(f"🔌 PostgreSQL Connections: {pg_connections}")
    
    return {
        'cpu': cpu_percent,
        'ram': memory.percent,
        'disk': disk.percent,
        'pg_connections': pg_connections
    }


def test_database_performance():
    """PostgreSQL performance test"""
    print_header("DATABASE PERFORMANCE TEST")
    
    print("📊 Database Statistics:")
    print(f"   Students: {Student.objects.count()}")
    print(f"   Groups: {Group.objects.count()}")
    print(f"   Topics: {Topic.objects.count()}")
    print(f"   Tasks: {Task.objects.count()}")
    
    print("\n🔍 Query Performance Test:")
    
    # Test 1: Simple SELECT
    start = time.time()
    students = list(Student.objects.all()[:100])
    duration = time.time() - start
    print(f"   SELECT 100 students: {duration*1000:.2f}ms")
    
    # Test 2: JOIN query
    start = time.time()
    students_with_group = list(Student.objects.select_related('group')[:100])
    duration = time.time() - start
    print(f"   SELECT with JOIN: {duration*1000:.2f}ms")
    
    # Test 3: Aggregate query
    start = time.time()
    group_stats = Group.objects.annotate(student_count=Count('students')).values('name', 'student_count')
    list(group_stats)
    duration = time.time() - start
    print(f"   Aggregate query: {duration*1000:.2f}ms")
    
    # Test 4: Filter query
    start = time.time()
    test_students = Student.objects.filter(telegram_id__startswith='test_')[:50]
    list(test_students)
    duration = time.time() - start
    print(f"   Filter query: {duration*1000:.2f}ms")


def test_concurrent_api_requests(num_requests=100):
    """DRF API concurrent requests test"""
    print_header(f"DRF API CONCURRENT TEST - {num_requests} requests")
    
    print(f"⚠️  Eslatma: Django dev server faqat 1 request bir vaqtda qabul qiladi!")
    print(f"   Production uchun Gunicorn + Nginx kerak.\n")
    
    async def api_request(session, url, request_id):
        """Single API request"""
        try:
            start = time.time()
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    duration = time.time() - start
                    return {
                        'success': True,
                        'duration': duration,
                        'request_id': request_id
                    }
                else:
                    return {'success': False, 'status': resp.status, 'request_id': request_id}
        except Exception as e:
            return {'success': False, 'error': str(e), 'request_id': request_id}
    
    async def run_concurrent_requests(num_requests):
        """Run multiple concurrent requests"""
        print(f"🚀 {num_requests} ta API request yuborilmoqda...\n")
        
        start_time = time.time()
        
        async with aiohttp.ClientSession() as session:
            tasks = [
                api_request(session, f"{API_BASE_URL}/groups/", i)
                for i in range(num_requests)
            ]
            results = await asyncio.gather(*tasks)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        success = sum(1 for r in results if r.get('success'))
        failed = num_requests - success
        
        if success > 0:
            durations = [r['duration'] for r in results if r.get('success')]
            avg_duration = sum(durations) / len(durations)
            min_duration = min(durations)
            max_duration = max(durations)
        else:
            avg_duration = min_duration = max_duration = 0
        
        print(f"✅ Success: {success}/{num_requests}")
        print(f"❌ Failed: {failed}")
        print(f"⏱️  Total Time: {total_time:.3f}s")
        print(f"⏱️  Avg Response: {avg_duration*1000:.2f}ms")
        print(f"⏱️  Min Response: {min_duration*1000:.2f}ms")
        print(f"⏱️  Max Response: {max_duration*1000:.2f}ms")
        print(f"📈 Throughput: {success/total_time:.1f} req/sec")
        
        # Resource usage (bu yerda system stats ni chaqirmaymiz, async context da)
        print("\n📊 Resource Usage:")
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        print(f"🖥️  CPU: {cpu_percent}%")
        print(f"💾 RAM: {memory.used / (1024**3):.2f} GB / {memory.total / (1024**3):.2f} GB ({memory.percent}%)")
        print(f"💿 Disk: {disk.used / (1024**3):.2f} GB / {disk.total / (1024**3):.2f} GB ({disk.percent}%)")
    
    asyncio.run(run_concurrent_requests(num_requests))


def test_user_registration_load(num_users=1500):
    """Simulate user registration load"""
    print_header(f"USER REGISTRATION LOAD TEST - {num_users} users")
    
    print(f"📝 Scenario: {num_users} ta user bir vaqtda ro'yxatdan o'tadi\n")
    
    group, _ = Group.objects.get_or_create(
        name="Load Test Group",
        defaults={'telegram_group_id': '-100999', 'invite_link': 'https://t.me/load'}
    )
    
    def register_user(user_id):
        """Single user registration"""
        try:
            start = time.time()
            student, created = Student.objects.get_or_create(
                telegram_id=f"load_test_{user_id}",
                defaults={'full_name': f"Load User {user_id}", 'group': group}
            )
            duration = time.time() - start
            return {'success': True, 'duration': duration, 'created': created}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    print(f"🚀 {num_users} ta user registratsiyasi boshlanmoqda...\n")
    
    start_time = time.time()
    success_count = 0
    total_duration = 0
    
    with ThreadPoolExecutor(max_workers=50) as executor:
        futures = [executor.submit(register_user, i) for i in range(num_users)]
        
        for future in as_completed(futures):
            result = future.result()
            if result['success']:
                success_count += 1
                total_duration += result['duration']
    
    end_time = time.time()
    total_time = end_time - start_time
    avg_duration = total_duration / success_count if success_count > 0 else 0
    
    print(f"✅ Success: {success_count}/{num_users}")
    print(f"⏱️  Total Time: {total_time:.3f}s")
    print(f"⏱️  Avg Registration: {avg_duration*1000:.2f}ms")
    print(f"📈 Users/second: {success_count/total_time:.1f}")
    
    print("\n📊 Resource Usage:")
    get_system_stats()
    
    # Cleanup
    Student.objects.filter(telegram_id__startswith='load_test_').delete()


def test_mixed_load(duration_seconds=60):
    """Mixed load test: reads + writes"""
    print_header(f"MIXED LOAD TEST - {duration_seconds} seconds")
    
    print(f"📝 Scenario: Read va Write operatsiyalar aralash\n")
    print(f"   {duration_seconds} soniya davomida load simulyatsiya qilinadi\n")
    
    group, _ = Group.objects.get_or_create(
        name="Mixed Load Group",
        defaults={'telegram_group_id': '-100888', 'invite_link': 'https://t.me/mixed'}
    )
    
    start_time = time.time()
    read_count = 0
    write_count = 0
    error_count = 0
    
    def read_operation():
        """Read operation"""
        try:
            students = list(Student.objects.select_related('group')[:10])
            return 'read'
        except:
            return 'error'
    
    def write_operation(user_id):
        """Write operation"""
        try:
            student, _ = Student.objects.get_or_create(
                telegram_id=f"mixed_{user_id}_{int(time.time())}",
                defaults={'full_name': f"Mixed User {user_id}", 'group': group}
            )
            return 'write'
        except:
            return 'error'
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = []
        operation_id = 0
        
        while (time.time() - start_time) < duration_seconds:
            # 70% read, 30% write
            if operation_id % 10 < 7:
                futures.append(executor.submit(read_operation))
            else:
                futures.append(executor.submit(write_operation, operation_id))
            
            operation_id += 1
            time.sleep(0.01)  # Small delay
        
        # Wait for completion
        for future in as_completed(futures):
            result = future.result()
            if result == 'read':
                read_count += 1
            elif result == 'write':
                write_count += 1
            else:
                error_count += 1
    
    end_time = time.time()
    actual_duration = end_time - start_time
    total_operations = read_count + write_count
    
    print(f"📊 Operations:")
    print(f"   Read: {read_count}")
    print(f"   Write: {write_count}")
    print(f"   Errors: {error_count}")
    print(f"   Total: {total_operations}")
    print(f"\n⏱️  Duration: {actual_duration:.2f}s")
    print(f"📈 Operations/sec: {total_operations/actual_duration:.1f}")
    
    print("\n📊 Final Resource Usage:")
    get_system_stats()
    
    # Cleanup
    Student.objects.filter(telegram_id__startswith='mixed_').delete()


def performance_recommendations():
    """Server uchun optimizatsiya tavsiyalari"""
    print_header("PRODUCTION OPTIMIZATSIYA TAVSIYALARI")
    
    stats = get_system_stats()
    
    print("🎯 Sizning server (2 CPU cores, 2GB RAM) uchun tavsiyalar:\n")
    
    print("1️⃣  **Gunicorn Configuration:**")
    print("   workers = 5  # (2 * CPU_cores) + 1 = 5")
    print("   worker_class = 'gevent'  # Async workers")
    print("   worker_connections = 1000")
    print("   max_requests = 1000")
    print("   max_requests_jitter = 100")
    print("   timeout = 30")
    
    print("\n2️⃣  **PostgreSQL tuning (2GB RAM):**")
    print("   shared_buffers = 512MB")
    print("   effective_cache_size = 1536MB")
    print("   maintenance_work_mem = 128MB")
    print("   work_mem = 8MB")
    print("   max_connections = 200")
    print("   checkpoint_completion_target = 0.9")
    
    print("\n3️⃣  **Nginx:**")
    print("   worker_processes = 2  # CPU cores")
    print("   worker_connections = 2048")
    print("   keepalive_timeout = 65")
    print("   gzip on")
    print("   gzip_comp_level = 5")
    
    print("\n4️⃣  **Redis (caching):**")
    print("   maxmemory = 256MB")
    print("   maxmemory-policy = allkeys-lru")
    
    print("\n5️⃣  **Django settings:**")
    print("   DEBUG = False")
    print("   CONN_MAX_AGE = 600")
    print("   CACHES = Redis")
    print("   SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'")
    
    print("\n📊 Expected Performance (optimized):")
    print("   • 1000 concurrent users: ✅ Yaxshi")
    print("   • 2000 concurrent users: ✅ Yetarli (monitoring bilan)")
    print("   • 3000+ concurrent users: ⚠️  Maksimal load")
    print("   • API throughput: ~500-800 req/sec")
    print("   • Database queries: ~1000-1500 queries/sec")
    
    print("\n⚠️  RAM bo'yicha limitlar:")
    if stats['ram'] > 85:
        print("   ❌ CRITICAL: RAM 85% dan oshdi!")
        print("   Tavsiya: Swap file yaratish (4GB) yoki RAM oshirish")
    elif stats['ram'] > 70:
        print("   ⚠️  WARNING: RAM 70% dan oshdi")
        print("   Monitoring kerak")
    else:
        print("   ✅ RAM yetarli")
    
    print("\n💡 2GB RAM bilan:")
    print("   • Django + Bot: ~400-500MB")
    print("   • PostgreSQL: ~512MB (shared_buffers)")
    print("   • Redis: ~256MB")
    print("   • System: ~300-400MB")
    print("   • Available: ~600-800MB (cache va buffer uchun)")


def main():
    """Main test menu"""
    print_header("PRODUCTION LOAD TESTING")
    print(f"🖥️  Server: 2 CPU cores, 2GB RAM, 40GB NVME")
    print(f"🌐 Network: 200Mb/s TAS-IX + 200Mb/s Internet")
    print(f"🎯 Target: 1000-2000 concurrent users")
    print(f"⏰ Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print("\n📊 Hozirgi system stats:")
    get_system_stats()
    
    while True:
        print("\n" + "="*80)
        print("Test Options:")
        print("="*80)
        print("1. Database performance test")
        print("2. API concurrent requests (100 req)")
        print("3. API concurrent requests (500 req)")
        print("4. User registration load (1500 users)")
        print("5. User registration load (500 users)")
        print("6. Mixed load test (60 seconds)")
        print("7. System stats")
        print("8. Performance recommendations")
        print("9. Full test (1+2+4+6)")
        print("0. Exit")
        print("="*80)
        
        choice = input("\nTanlang (0-9): ").strip()
        
        if choice == '1':
            test_database_performance()
        elif choice == '2':
            print("\n⚠️  Django dev server ishga tushganligiga ishonch hosil qiling!")
            print("   Terminal: python manage.py runserver")
            input("\nDavom etish uchun Enter...")
            test_concurrent_api_requests(100)
        elif choice == '3':
            print("\n⚠️  Django dev server ishga tushganligiga ishonch hosil qiling!")
            input("\nDavom etish uchun Enter...")
            test_concurrent_api_requests(500)
        elif choice == '4':
            test_user_registration_load(1500)
        elif choice == '5':
            test_user_registration_load(500)
        elif choice == '6':
            test_mixed_load(60)
        elif choice == '7':
            print_header("SYSTEM STATS")
            get_system_stats()
        elif choice == '8':
            performance_recommendations()
        elif choice == '9':
            test_database_performance()
            print("\n⚠️  API test uchun Django dev server kerak!")
            choice = input("API test o'tkazilsinmi? (y/n): ")
            if choice.lower() == 'y':
                test_concurrent_api_requests(100)
            test_user_registration_load(1500)
            test_mixed_load(60)
            performance_recommendations()
        elif choice == '0':
            print("\n👋 Test tugadi!")
            break
        else:
            print("❌ Noto'g'ri tanlov!")
    
    print(f"\n⏰ End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)


if __name__ == "__main__":
    try:
        # psutil package tekshirish
        import psutil
        main()
    except ImportError:
        print("❌ psutil package topilmadi!")
        print("O'rnatish: pip install psutil")
        sys.exit(1)
