"""
Bot Load Testing Script
Bir vaqtning o'zida 500-1000 ta userdan so'rovlar yuborish
"""
import asyncio
import aiohttp
import time
from datetime import datetime

# Config
API_BASE_URL = "http://127.0.0.1:8000/api"
NUM_USERS = 500  # Test qilish uchun userlar soni
CONCURRENT_REQUESTS = 50  # Bir vaqtda bajarilish uchun so'rovlar

# Test statistikasi
stats = {
    "total_requests": 0,
    "successful": 0,
    "failed": 0,
    "total_time": 0,
    "errors": []
}


async def simulate_user_registration(session, user_id):
    """Bitta userni ro'yxatdan o'tkazish simulyatsiyasi"""
    start_time = time.time()
    
    try:
        # 1. Studentni tekshirish
        async with session.get(f"{API_BASE_URL}/students/{user_id}/") as resp:
            if resp.status == 404:
                # Student yo'q, ro'yxatdan o'tkazamiz
                payload = {
                    "telegram_id": str(user_id),
                    "full_name": f"Test User {user_id}",
                    "group_id": 1  # Birinchi guruhga qo'shamiz
                }
                async with session.post(f"{API_BASE_URL}/students/register/", json=payload) as reg_resp:
                    if reg_resp.status == 201:
                        stats["successful"] += 1
                    else:
                        stats["failed"] += 1
                        error_text = await reg_resp.text()
                        stats["errors"].append(f"User {user_id}: {error_text[:100]}")
            else:
                stats["successful"] += 1  # Allaqachon ro'yxatdan o'tgan
        
        stats["total_requests"] += 1
        elapsed = time.time() - start_time
        stats["total_time"] += elapsed
        
        if stats["total_requests"] % 100 == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Progress: {stats['total_requests']}/{NUM_USERS} "
                  f"| Success: {stats['successful']} | Failed: {stats['failed']} "
                  f"| Avg time: {stats['total_time']/stats['total_requests']:.2f}s")
    
    except Exception as e:
        stats["failed"] += 1
        stats["errors"].append(f"User {user_id}: {str(e)[:100]}")


async def simulate_task_submission(session, user_id, topic_id=1):
    """Vazifa yuborish simulyatsiyasi"""
    start_time = time.time()
    
    try:
        payload = {
            "student_id": user_id,
            "topic_id": topic_id,
            "file_link": f"test_file_{user_id}"
        }
        
        async with session.post(f"{API_BASE_URL}/tasks/submit/", json=payload) as resp:
            if resp.status == 201:
                stats["successful"] += 1
            else:
                stats["failed"] += 1
                error_text = await resp.text()
                stats["errors"].append(f"Task {user_id}: {error_text[:100]}")
        
        stats["total_requests"] += 1
        elapsed = time.time() - start_time
        stats["total_time"] += elapsed
    
    except Exception as e:
        stats["failed"] += 1
        stats["errors"].append(f"Task {user_id}: {str(e)[:100]}")


async def run_load_test(test_type="registration"):
    """Load testni ishga tushirish"""
    print(f"{'='*60}")
    print(f"Bot Load Testing - {test_type.upper()}")
    print(f"{'='*60}")
    print(f"Total users: {NUM_USERS}")
    print(f"Concurrent requests: {CONCURRENT_REQUESTS}")
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    
    async with aiohttp.ClientSession() as session:
        # Userlarni guruhlar bo'yicha bo'lib yuboramiz
        for i in range(0, NUM_USERS, CONCURRENT_REQUESTS):
            tasks = []
            for user_id in range(i, min(i + CONCURRENT_REQUESTS, NUM_USERS)):
                if test_type == "registration":
                    task = simulate_user_registration(session, 100000 + user_id)
                elif test_type == "task_submission":
                    task = simulate_task_submission(session, 100000 + user_id)
                tasks.append(task)
            
            # Bir vaqtda CONCURRENT_REQUESTS ta so'rov yuboramiz
            await asyncio.gather(*tasks)
    
    total_time = time.time() - start_time
    
    # Yakuniy natijalar
    print(f"\n{'='*60}")
    print(f"TEST COMPLETED")
    print(f"{'='*60}")
    print(f"Total requests: {stats['total_requests']}")
    print(f"Successful: {stats['successful']} ({stats['successful']/stats['total_requests']*100:.1f}%)")
    print(f"Failed: {stats['failed']} ({stats['failed']/stats['total_requests']*100:.1f}%)")
    print(f"Total time: {total_time:.2f}s")
    print(f"Avg time per request: {stats['total_time']/stats['total_requests']:.3f}s")
    print(f"Requests per second: {stats['total_requests']/total_time:.2f}")
    print(f"{'='*60}")
    
    if stats['errors'][:5]:
        print(f"\nFirst 5 errors:")
        for error in stats['errors'][:5]:
            print(f"  - {error}")
    
    print(f"\n{'='*60}")


async def main():
    """Asosiy test funksiyasi"""
    print("\nBot Load Testing Menu:")
    print("1. Registration test (500-1000 users)")
    print("2. Task submission test (500-1000 tasks)")
    print("3. Mixed test (registration + tasks)")
    print("4. Custom test")
    
    choice = input("\nTanlang (1-4): ").strip()
    
    if choice == "1":
        await run_load_test("registration")
    elif choice == "2":
        await run_load_test("task_submission")
    elif choice == "3":
        print("\nMixed test - registration + tasks")
        await run_load_test("registration")
        stats["total_requests"] = 0
        stats["successful"] = 0
        stats["failed"] = 0
        stats["total_time"] = 0
        stats["errors"] = []
        await run_load_test("task_submission")
    elif choice == "4":
        global NUM_USERS, CONCURRENT_REQUESTS
        NUM_USERS = int(input("Userlar soni (500-1000): "))
        CONCURRENT_REQUESTS = int(input("Concurrent requests (10-100): "))
        test_type = input("Test turi (registration/task_submission): ")
        await run_load_test(test_type)
    else:
        print("Noto'g'ri tanlov!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest to'xtatildi!")
