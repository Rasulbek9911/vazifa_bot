import pytz
from collections import defaultdict
from datetime import datetime

from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

TASHKENT_TZ = pytz.timezone('Asia/Tashkent')


def _month_bounds(year, month):
    start = TASHKENT_TZ.localize(datetime(year, month, 1))
    end = (
        TASHKENT_TZ.localize(datetime(year + 1, 1, 1)) if month == 12
        else TASHKENT_TZ.localize(datetime(year, month + 1, 1))
    )
    return start, end


def is_monthly_streak_enabled(year, month):
    from .models import MonthlyStreakSetting
    return MonthlyStreakSetting.objects.filter(year=year, month=month, enabled=True).exists()


def _replay_month_txs(txs, all_tasks, active_topics):
    """
    Pure-Python qayta hisoblash — hech qanday DB so'rovi yubormaydi.
    txs: shu oy uchun CoinTransaction'lar ro'yxati (created_at bo'yicha tartiblangan, topic prefetch qilingan)
    all_tasks: [(topic_id, submitted_at), ...] — shu student/kurs uchun barcha Task'lar
    active_topics: [(topic_id, activated_at), ...] — shu kursdagi barcha FAOL mavzular
    Returns: (period_coins, streak_at_end, longest_streak_in_period)
    """
    current_streak = 0
    longest_streak = 0
    last_topic_id = None
    last_activated_at = None
    period_coins = 0

    for tx in txs:
        topic = tx.topic
        completed_ids = {
            tid for tid, sub_at in all_tasks
            if sub_at is not None and sub_at <= tx.created_at
        }

        if last_topic_id is None:
            new_streak = 1
        else:
            if topic.activated_at is not None:
                upper = topic.activated_at
                lower = last_activated_at
                has_gap = any(
                    tid != topic.id
                    and act is not None and act <= upper
                    and (lower is None or act > lower)
                    and tid not in completed_ids
                    for tid, act in active_topics
                )
            else:
                has_gap = any(
                    tid != topic.id and last_topic_id < tid < topic.id and tid not in completed_ids
                    for tid, act in active_topics
                )
            new_streak = 1 if has_gap else current_streak + 1

        period_coins += tx.result_coins + new_streak
        current_streak = new_streak
        longest_streak = max(longest_streak, new_streak)
        last_topic_id = topic.id
        last_activated_at = topic.activated_at

    return period_coins, current_streak, longest_streak


def _compute_reset_month_coins(wallet, start, end):
    """
    Bitta wallet uchun qulay (lekin 2-3 ta so'rov yuboradigan) yordamchi —
    faqat bitta studentni hisoblashda ishlatiladi (masalan Tangalarim).
    Ko'plab wallet'larni bir yo'la hisoblash uchun compute_month_leaderboard'dan
    foydalaning (u N+1 so'rovlarsiz, bulk ishlaydi).
    """
    from .models import CoinTransaction, Task as TaskModel, Topic

    txs = list(
        CoinTransaction.objects.filter(
            wallet=wallet, topic__activated_at__gte=start, topic__activated_at__lt=end
        ).select_related('topic').order_by('created_at')
    )
    if not txs:
        return 0, 0, 0

    all_tasks = list(
        TaskModel.objects.filter(student=wallet.student, topic__course=wallet.course)
        .values_list('topic_id', 'submitted_at')
    )
    active_topics = list(
        Topic.objects.filter(course=wallet.course, is_active=True).values_list('id', 'activated_at')
    )
    return _replay_month_txs(txs, all_tasks, active_topics)


def compute_month_leaderboard(course_id, year, month, student_ids=None):
    """
    Kurs (va ixtiyoriy student_ids filtri) bo'yicha BARCHA wallet'lar uchun
    oy-reset streak asosida (period_coins, streak, longest_streak) bir yo'la,
    atigi 3 ta bulk so'rov bilan hisoblaydi (har wallet uchun alohida so'rov
    yubormasdan — 600+ studentlik kursda ham tez ishlashi uchun).
    Returns: [(wallet, period_coins, streak, longest_streak), ...] kamayish tartibida.
    """
    from .models import CoinWallet, CoinTransaction, Task as TaskModel, Topic

    start, end = _month_bounds(year, month)

    qs = CoinWallet.objects.filter(course_id=course_id).select_related('student', 'course')
    if student_ids is not None:
        qs = qs.filter(student_id__in=student_ids)
    wallets = list(qs)
    if not wallets:
        return []

    course = wallets[0].course
    active_topics = list(
        Topic.objects.filter(course=course, is_active=True).values_list('id', 'activated_at')
    )

    wallet_ids = [w.id for w in wallets]
    txs_by_wallet = defaultdict(list)
    for tx in (
        CoinTransaction.objects.filter(
            wallet_id__in=wallet_ids, topic__activated_at__gte=start, topic__activated_at__lt=end
        ).select_related('topic').order_by('wallet_id', 'created_at')
    ):
        txs_by_wallet[tx.wallet_id].append(tx)

    student_ids_in_wallets = [w.student_id for w in wallets]
    tasks_by_student = defaultdict(list)
    for student_id, topic_id, submitted_at in (
        TaskModel.objects.filter(student_id__in=student_ids_in_wallets, topic__course=course)
        .values_list('student_id', 'topic_id', 'submitted_at')
    ):
        tasks_by_student[student_id].append((topic_id, submitted_at))

    results = []
    for w in wallets:
        txs = txs_by_wallet.get(w.id, [])
        if not txs:
            results.append((w, 0, 0, 0))
            continue
        all_tasks = tasks_by_student.get(w.student_id, [])
        p_coins, streak, longest = _replay_month_txs(txs, all_tasks, active_topics)
        results.append((w, p_coins, streak, longest))

    results.sort(key=lambda t: (-t[1], -t[3]))
    return results


def get_month_period_data(wallet, year, month):
    """
    Tangalarim/reyting/PDF uchun bitta kirish nuqtasi: shu (year, month)
    uchun 'oylik streak rejimi' yoqilgan bo'lsa — streak shu oydan 1 deb
    qayta hisoblanadi (on-the-fly). O'chirilgan bo'lsa — hozirgi (global,
    butun davr davomida uzluksiz) streak bilan hisoblangan saqlangan
    qiymatlar ishlatiladi.
    Returns dict: {period_coins, streak, longest_streak}
    """
    from .models import CoinTransaction

    start, end = _month_bounds(year, month)

    if is_monthly_streak_enabled(year, month):
        period_coins, streak, longest_streak = _compute_reset_month_coins(wallet, start, end)
        return {'period_coins': period_coins, 'streak': streak, 'longest_streak': longest_streak}

    period_coins = CoinTransaction.objects.filter(
        wallet=wallet, topic__activated_at__gte=start, topic__activated_at__lt=end
    ).aggregate(s=Sum('total_coins'))['s'] or 0
    return {
        'period_coins': period_coins,
        'streak': wallet.current_streak,
        'longest_streak': wallet.longest_streak,
    }


def get_monthly_rating_rows(course_id, year, month, student_ids=None):
    """
    Kurs (va ixtiyoriy student_ids filtri) bo'yicha oylik PDF reyting uchun
    qatorlar: [{'wallet__student__full_name': ..., 'oylik': coins}, ...],
    kamayish tartibida. MonthlyStreakSetting shu (year, month) uchun yoqilgan
    bo'lsa, summalar oy-reset streak mantig'i bilan (bulk, N+1 siz) qayta hisoblanadi.
    """
    from .models import CoinWallet, CoinTransaction

    if is_monthly_streak_enabled(year, month):
        computed = compute_month_leaderboard(course_id, year, month, student_ids)
        return [
            {'wallet__student__full_name': w.student.full_name, 'oylik': p_coins}
            for w, p_coins, _streak, _longest in computed[:600]
        ]

    qs = (
        CoinWallet.objects.filter(course_id=course_id)
        .select_related('student')
        .order_by('-total_coins', '-longest_streak')
    )
    if student_ids is not None:
        qs = qs.filter(student_id__in=student_ids)
    all_wallets = list(qs[:600])
    if not all_wallets:
        return []

    txn_qs = CoinTransaction.objects.filter(
        wallet__course_id=course_id,
        topic__activated_at__year=year, topic__activated_at__month=month,
    )
    if student_ids is not None:
        txn_qs = txn_qs.filter(wallet__student_id__in=student_ids)
    monthly = dict(
        txn_qs.values('wallet__student_id')
              .annotate(s=Sum('total_coins'))
              .values_list('wallet__student_id', 's')
    )
    rows = sorted(
        [{'wallet__student__full_name': w.student.full_name,
          'oylik': monthly.get(w.student_id, 0)} for w in all_wallets],
        key=lambda r: r['oylik'], reverse=True
    )
    return rows


def award_task_coins(student, topic, grade, deadline_passed, task_type='test'):
    """
    Student vazifa bajarganida tanga berish.
    grade: already deadline-adjusted grade value
    Returns dict {result_coins, streak_coins, new_streak, total, total_wallet} yoki None.
    """
    from .models import CoinWallet, CoinTransaction, Topic, Task as TaskModel

    course = topic.course
    if not course or grade is None:
        return None

    with db_transaction.atomic():
        wallet, _ = CoinWallet.objects.select_for_update().get_or_create(
            student=student, course=course
        )

        # Bir mavzu uchun bir marta beriladi
        if CoinTransaction.objects.filter(wallet=wallet, topic=topic, task_type=task_type).exists():
            return None

        result_coins = max(0, grade)

        last_topic_id = wallet.last_topic_id
        last_submitted_at = wallet.last_submitted_at

        if last_topic_id is None:
            new_streak = 1
        else:
            completed_ids = list(TaskModel.objects.filter(
                student=student, topic__course=course
            ).values_list('topic_id', flat=True))

            if topic.activated_at is not None:
                # Faqat OXIRGI topshirilgan mavzu bilan hozirgisi orasida (oraliqda)
                # topshirilmagan active topic bor-yo'qligini tekshiramiz — butun kurs
                # tarixi emas. Aks holda bir marta o'tkazib yuborilgan mavzu abadiy
                # "gap" bo'lib qolib, undan keyingi barcha topshiriqlar uchun streak
                # har doim 1 ga tushib qolar edi.
                last_activated_at = Topic.objects.filter(id=last_topic_id).values_list(
                    'activated_at', flat=True
                ).first()
                gap_qs = Topic.objects.filter(
                    course=course,
                    is_active=True,
                    activated_at__lte=topic.activated_at,
                )
                if last_activated_at is not None:
                    gap_qs = gap_qs.filter(activated_at__gt=last_activated_at)
                has_gap = gap_qs.exclude(id__in=completed_ids).exclude(id=topic.id).exists()
            else:
                # activated_at yo'q bo'lsa: id bo'yicha oradagi topiclarni tekshir
                has_gap = Topic.objects.filter(
                    course=course,
                    is_active=True,
                    id__gt=last_topic_id,
                    id__lt=topic.id,
                ).exclude(id__in=completed_ids).exists()

            new_streak = 1 if has_gap else wallet.current_streak + 1

        streak_coins = new_streak
        total = result_coins + streak_coins

        wallet.total_coins += total
        wallet.current_streak = new_streak
        if new_streak > wallet.longest_streak:
            wallet.longest_streak = new_streak
        wallet.last_topic = topic
        wallet.last_submitted_at = timezone.now()
        wallet.save()

        CoinTransaction.objects.create(
            wallet=wallet,
            topic=topic,
            task_type=task_type,
            result_coins=result_coins,
            streak_coins=streak_coins,
            total_coins=total,
            streak_after=new_streak,
            deadline_penalty=deadline_passed,
        )

        return {
            'result_coins': result_coins,
            'streak_coins': streak_coins,
            'new_streak': new_streak,
            'total': total,
            'total_wallet': wallet.total_coins,
            'longest_streak': wallet.longest_streak,
        }


def reverse_task_coins(task):
    """
    Task (test/vazifa natijasi) o'chirilganda unga mos tanga tranzaksiyasini
    bekor qiladi va hamyonni qolgan tranzaksiyalar asosida qayta hisoblaydi
    (delta olib tashlash o'rniga to'liq qayta hisoblash — streak/longest_streak
    ni to'g'ri holatda saqlab qolish uchun).
    """
    from .models import CoinWallet, CoinTransaction

    topic = task.topic
    course = topic.course if topic else None
    if not course:
        return

    with db_transaction.atomic():
        wallet = CoinWallet.objects.select_for_update().filter(
            student=task.student, course=course
        ).first()
        if not wallet:
            return

        tx = CoinTransaction.objects.filter(
            wallet=wallet, topic=topic, task_type=task.task_type
        ).first()
        if not tx:
            return

        tx.delete()

        remaining = list(
            CoinTransaction.objects.filter(wallet=wallet).order_by('created_at')
        )
        wallet.total_coins = sum(r.total_coins for r in remaining)
        wallet.longest_streak = max((r.streak_after for r in remaining), default=0)

        last = remaining[-1] if remaining else None
        if last:
            wallet.current_streak = last.streak_after
            wallet.last_topic = last.topic
            wallet.last_submitted_at = last.created_at
        else:
            wallet.current_streak = 0
            wallet.last_topic = None
            wallet.last_submitted_at = None

        wallet.save()
