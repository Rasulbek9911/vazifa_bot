import json
import urllib.request
from pathlib import Path
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Count, Q

from .models import Student, Topic, Task, Course, Group, FollowUp, CallHistory, PaymentPlan, Payment, OperatorProfile

PAGE_SIZE = 20
LOCK_MINUTES = 30


def _is_superadmin(user):
    return user.is_superuser


def _get_bot_token():
    try:
        from dotenv import dotenv_values
        env_path = Path(__file__).resolve().parent.parent / 'mukammal-bot-paid' / '.env'
        return dotenv_values(env_path).get('BOT_TOKEN', '')
    except Exception:
        return ''


def _unsubmitted_ids_for_student(student):
    course_ids = {
        g.course_id for g in student.groups.all()
        if g.course and g.course.is_active
    }
    if not course_ids:
        return []
    active_ids = list(
        Topic.objects.filter(is_active=True, course_id__in=course_ids)
        .values_list('id', flat=True)
    )
    submitted = set(
        Task.objects.filter(student=student, topic_id__in=active_ids)
        .values_list('topic_id', flat=True)
    )
    return [tid for tid in active_ids if tid not in submitted]


def _lock_status(fu, current_user):
    """Returns: 'free' | 'locked_by_me' | 'locked_by_other'"""
    if not fu:
        return 'free'
    if not fu.is_locked():
        return 'free'
    if fu.locked_by_id == current_user.id:
        return 'locked_by_me'
    return 'locked_by_other'


def _called_today_by_other(fu, current_user):
    if not fu or not fu.called_at:
        return False
    if fu.called_by_id == current_user.id:
        return False
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return fu.called_at >= today_start


@login_required
def followup_list(request):
    course_id = request.GET.get('course_id', '')
    group_id = request.GET.get('group_id', '')
    search_q = request.GET.get('q', '').strip().lower()
    tab = request.GET.get('tab', 'not_called')
    page_num = request.GET.get('page', 1)
    user = request.user
    is_super = _is_superadmin(user)
    can_block = user.is_staff or user.is_superuser

    topics_qs = Topic.objects.filter(is_active=True, course__is_active=True).select_related('course')
    if course_id:
        topics_qs = topics_qs.filter(course_id=course_id)
    active_topics = list(topics_qs)
    active_topic_ids = [t.id for t in active_topics]
    active_topics_dict = {t.id: t for t in active_topics}

    courses = Course.objects.filter(is_active=True).order_by('name')

    # Operator biriktirilgan guruhlar
    operator_groups = []
    if not is_super:
        try:
            op_profile = user.operator_profile
            operator_groups = list(op_profile.assigned_groups.select_related('course').order_by('name'))
        except OperatorProfile.DoesNotExist:
            pass

    # Guruhlar (kurs filter bo'lsa shu kurs guruhlari; operator uchun faqat o'z guruhlari)
    groups_qs = Group.objects.filter(course__is_active=True).order_by('name')
    if not is_super and operator_groups:
        groups_qs = groups_qs.filter(id__in=[g.id for g in operator_groups])
    if course_id:
        groups_qs = groups_qs.filter(course_id=course_id)
    all_groups_list = list(groups_qs)

    if not active_topics:
        return render(request, 'followup/list.html', {
            'students_data': [], 'courses': courses, 'groups': all_groups_list,
            'selected_course_id': course_id, 'selected_group_id': group_id,
            'tab': tab, 'total_unsubmitted': 0, 'total_called': 0,
            'total_not_called': 0, 'is_super': is_super,
        })

    submitted_pairs = set(
        Task.objects.filter(topic_id__in=active_topic_ids)
        .values_list('student_id', 'topic_id')
    )
    all_followups = {fu.student_id: fu for fu in FollowUp.objects.select_related('called_by', 'locked_by').all()}

    students_qs = (
        Student.objects.filter(groups__isnull=False, is_blocked=False)
        .distinct()
        .prefetch_related('groups__course')
        .order_by('full_name')
    )
    if group_id:
        students_qs = students_qs.filter(groups__id=group_id)
    elif operator_groups:
        # Operator uchun faqat biriktirilgan guruhlar studentlari
        op_group_ids = [g.id for g in operator_groups]
        students_qs = students_qs.filter(groups__id__in=op_group_ids)

    students = list(students_qs)
    now = timezone.now()

    # --- NOT_CALLED ---
    not_called = []
    for student in students:
        if search_q and search_q not in student.full_name.lower():
            continue
        fu = all_followups.get(student.id)
        if fu and fu.called_at:
            continue

        all_grps = list(student.groups.all())
        student_course_ids = {g.course.id for g in all_grps if g.course and g.course.is_active}
        if not student_course_ids:
            continue
        if course_id:
            filtered_topics = [t for t in active_topics if t.course_id in student_course_ids and str(t.course_id) == str(course_id)]
        else:
            filtered_topics = [t for t in active_topics if t.course_id in student_course_ids]

        unsubmitted = [t for t in filtered_topics if (student.id, t.id) not in submitted_pairs]
        if len(unsubmitted) < 3:
            continue

        lock = _lock_status(fu, user)
        called_today_other = _called_today_by_other(fu, user)

        not_called.append({
            'student': student,
            'unsubmitted': unsubmitted,
            'followup': fu,
            'groups_str': ', '.join(g.name for g in all_grps),
            'groups_list': all_grps,
            'progress': None,
            'original_count': None,
            'lock': lock,
            'called_today_other': called_today_other,
        })

    # --- CALLED_PENDING ---
    called_fus = [fu for fu in all_followups.values() if fu.called_at]

    # Operator faqat o'z chaqiruvlarini ko'radi
    if not is_super:
        called_fus = [fu for fu in called_fus if fu.called_by_id == user.id]

    called_student_ids = [fu.student_id for fu in called_fus]
    submitted_for_called = {}
    for row in Task.objects.filter(student_id__in=called_student_ids).values('student_id', 'topic_id'):
        submitted_for_called.setdefault(row['student_id'], set()).add(row['topic_id'])

    called_students_map = {
        s.id: s
        for s in Student.objects.filter(id__in=called_student_ids, is_blocked=False).prefetch_related('groups__course')
    }

    called_pending = []
    for fu in called_fus:
        student = called_students_map.get(fu.student_id)
        if not student:
            continue
        if search_q and search_q not in student.full_name.lower():
            continue
        if group_id and not student.groups.filter(id=group_id).exists():
            continue

        all_grps = list(student.groups.all())
        submitted = submitted_for_called.get(fu.student_id, set())

        if fu.topic_ids_at_call:
            original_ids = set(fu.topic_ids_at_call)
            submitted_from_original = submitted & original_ids
            still_unsubmitted_ids = original_ids - submitted_from_original
            if not still_unsubmitted_ids:
                continue
            if course_id:
                still_unsubmitted_ids = {
                    tid for tid in still_unsubmitted_ids
                    if tid in active_topics_dict and str(active_topics_dict[tid].course_id) == str(course_id)
                }
                if not still_unsubmitted_ids:
                    continue
            still_unsubmitted = [active_topics_dict[tid] for tid in still_unsubmitted_ids if tid in active_topics_dict]
            progress = len(submitted_from_original)
            original_count = len(fu.topic_ids_at_call)
        else:
            student_course_ids = {g.course_id for g in all_grps if g.course and g.course.is_active}
            if course_id:
                relevant = [t for t in active_topics if t.course_id in student_course_ids and str(t.course_id) == str(course_id)]
            else:
                relevant = [t for t in active_topics if t.course_id in student_course_ids]
            still_unsubmitted = [t for t in relevant if t.id not in submitted]
            if not still_unsubmitted:
                continue
            progress = 0
            original_count = None

        lock = _lock_status(fu, user)
        called_today_other = _called_today_by_other(fu, user)

        called_pending.append({
            'student': student,
            'unsubmitted': still_unsubmitted,
            'followup': fu,
            'groups_str': ', '.join(g.name for g in all_grps),
            'groups_list': all_grps,
            'progress': progress,
            'original_count': original_count,
            'lock': lock,
            'called_today_other': called_today_other,
        })

    called_pending.sort(key=lambda x: x['student'].full_name)

    active_list = not_called if tab == 'not_called' else called_pending
    paginator = Paginator(active_list, PAGE_SIZE)
    page = paginator.get_page(page_num)

    # Superadmin statistikasi va payment ma'lumotlari
    stats = None
    payment_map = {}
    if is_super:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_calls = list(
            CallHistory.objects.filter(called_at__gte=today_start)
            .values('operator__username', 'operator__first_name', 'operator__last_name')
            .annotate(today_count=Count('id'))
            .order_by('-today_count')
        )
        total_calls = list(
            CallHistory.objects.values('operator__username', 'operator__first_name', 'operator__last_name')
            .annotate(total_count=Count('id'))
            .order_by('-total_count')
        )
        stats_map = {s['operator__username']: s for s in today_calls}
        for t in total_calls:
            uname = t['operator__username']
            if uname in stats_map:
                stats_map[uname]['total_count'] = t['total_count']
            else:
                stats_map[uname] = {**t, 'today_count': 0}
        stats = list(stats_map.values())

        # Payment ma'lumotlari — har bir itemga to'g'ridan qo'shiladi
        page_student_ids = [item['student'].id for item in page.object_list]
        plans = PaymentPlan.objects.filter(
            student_id__in=page_student_ids
        ).prefetch_related('payments')
        payment_map = {}
        for plan in plans:
            paid = sum(p.amount for p in plan.payments.all())
            remaining = max(0, plan.total_amount - paid)
            status = 'complete' if paid >= plan.total_amount else ('partial' if paid > 0 else 'unpaid')
            payment_map[plan.student_id] = {
                'plan': plan,
                'paid': paid,
                'remaining': remaining,
                'status': status,
            }
        for item in page.object_list:
            item['payment'] = payment_map.get(item['student'].id)

    return render(request, 'followup/list.html', {
        'students_data': page.object_list,  # har bir item['payment'] qo'shilgan (is_super uchun)
        'page': page,
        'paginator': paginator,
        'courses': courses,
        'groups': all_groups_list,
        'selected_course_id': course_id,
        'selected_group_id': group_id,
        'tab': tab,
        'total_unsubmitted': len(not_called) + len(called_pending),
        'total_called': len(called_pending),
        'total_not_called': len(not_called),
        'is_super': is_super,
        'can_block': can_block,
        'current_user': user,
        'stats': stats,
        'operator_groups': operator_groups,
    })


@login_required
@require_POST
def followup_lock(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    fu, _ = FollowUp.objects.get_or_create(student=student)
    now = timezone.now()

    if fu.is_locked() and fu.locked_by_id != request.user.id:
        remaining = int((fu.locked_until - now).total_seconds() / 60)
        return JsonResponse({
            'ok': False,
            'locked_by': fu.locked_by.get_full_name() or fu.locked_by.username,
            'remaining': remaining,
        })

    fu.locked_by = request.user
    fu.locked_until = now + timedelta(minutes=LOCK_MINUTES)
    fu.save(update_fields=['locked_by', 'locked_until'])
    return JsonResponse({'ok': True})


@login_required
@require_POST
def followup_mark(request, student_id):
    student = get_object_or_404(
        Student.objects.prefetch_related('groups__course'), id=student_id
    )
    try:
        body = json.loads(request.body)
        note = body.get('note', '').strip()
        result = body.get('result', 'answered')
        force = body.get('force', False)
    except Exception:
        note = ''
        result = 'answered'
        force = False

    # Boshqa operator bugun chaqirgan — force bo'lmasa blok
    fu, _ = FollowUp.objects.select_related('called_by').get_or_create(student=student)
    now = timezone.now()

    if not force and fu.called_at and fu.called_by_id and fu.called_by_id != request.user.id:
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if fu.called_at >= today_start:
            op_name = fu.called_by.get_full_name() or fu.called_by.username
            return JsonResponse({
                'ok': False,
                'warn': True,
                'message': f"Bu student bugun {fu.called_at.strftime('%H:%M')} da {op_name} tomonidan chaqirilgan.",
            })

    unsubmitted_ids = _unsubmitted_ids_for_student(student)
    fu.called_at = now
    fu.called_by = request.user
    fu.note = note
    fu.topic_ids_at_call = unsubmitted_ids
    fu.locked_by = None
    fu.locked_until = None
    fu.save()

    CallHistory.objects.create(
        student=student,
        operator=request.user,
        note=note,
        result=result,
    )

    return JsonResponse({
        'ok': True,
        'called_at': fu.called_at.strftime('%d.%m.%Y %H:%M'),
    })


@login_required
@require_POST
def followup_unmark(request, student_id):
    if not _is_superadmin(request.user):
        return JsonResponse({'ok': False, 'error': 'Ruxsat yoq'}, status=403)
    student = get_object_or_404(Student, id=student_id)
    try:
        fu = student.followup
        fu.called_at = None
        fu.called_by = None
        fu.note = ''
        fu.topic_ids_at_call = None
        fu.locked_by = None
        fu.locked_until = None
        fu.save()
    except FollowUp.DoesNotExist:
        pass
    return JsonResponse({'ok': True})


@login_required
@require_POST
def followup_block(request, student_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'ok': False, 'error': 'Ruxsat yoq'}, status=403)
    student = get_object_or_404(Student, id=student_id)
    student.is_blocked = True
    student.save(update_fields=['is_blocked'])
    return JsonResponse({'ok': True, 'blocked': True})


@login_required
@require_POST
def followup_unblock(request, student_id):
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'ok': False, 'error': 'Ruxsat yoq'}, status=403)
    student = get_object_or_404(Student, id=student_id)
    student.is_blocked = False
    student.save(update_fields=['is_blocked'])
    return JsonResponse({'ok': True, 'blocked': False})


@login_required
def followup_tg_link(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    telegram_id = student.telegram_id

    # 1-urinish: Bot API orqali username olish
    token = _get_bot_token()
    if token:
        try:
            api_url = f"https://api.telegram.org/bot{token}/getChat?chat_id={telegram_id}"
            with urllib.request.urlopen(api_url, timeout=5) as resp:
                data = json.loads(resp.read())
            if data.get('ok') and data['result'].get('username'):
                return JsonResponse({'url': f"https://t.me/{data['result']['username']}"})
        except Exception:
            pass

    # Fallback: Telegram ID orqali (har doim to'g'ri profil ochadi)
    return JsonResponse({'url': f"tg://user?id={telegram_id}"})
