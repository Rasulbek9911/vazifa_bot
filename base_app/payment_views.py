import json
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.core.paginator import Paginator

from .models import Student, Course, Group, PaymentPlan, Payment

PAGE_SIZE = 25


def _superadmin_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        return func(request, *args, **kwargs)
    return wrapper


def _plan_summary(plan):
    payments = list(plan.payments.all())
    paid = sum(p.amount for p in payments)
    remaining = max(0, plan.total_amount - paid)
    if paid == 0:
        status = 'unpaid'
    elif paid >= plan.total_amount:
        status = 'complete'
    else:
        status = 'partial'
    return {'paid': paid, 'remaining': remaining, 'status': status, 'payments': payments}


@_superadmin_required
def payment_list(request):
    course_id = request.GET.get('course_id', '')
    group_id = request.GET.get('group_id', '')
    status_filter = request.GET.get('status', '')
    search_q = request.GET.get('q', '').strip().lower()
    page_num = request.GET.get('page', 1)

    courses = Course.objects.filter(is_active=True).order_by('name')
    groups_qs = Group.objects.filter(course__is_active=True).order_by('name')
    if course_id:
        groups_qs = groups_qs.filter(course_id=course_id)
    groups = list(groups_qs)

    # Studentlar
    students_qs = (
        Student.objects.filter(groups__isnull=False)
        .distinct()
        .prefetch_related('groups__course', 'payment_plans__payments')
        .order_by('full_name')
    )
    if course_id:
        students_qs = students_qs.filter(groups__course_id=course_id)
    if group_id:
        students_qs = students_qs.filter(groups__id=group_id)

    # To'lov rejalari
    plans_qs = PaymentPlan.objects.select_related('student', 'course').prefetch_related('payments')
    if course_id:
        plans_qs = plans_qs.filter(course_id=course_id)
    plans_map = {}
    for plan in plans_qs:
        plans_map[(plan.student_id, plan.course_id)] = plan

    # Kurs IDlarni aniqlash
    if course_id:
        target_course_ids = [int(course_id)]
    else:
        target_course_ids = list(courses.values_list('id', flat=True))

    rows = []
    for student in students_qs:
        if search_q and search_q not in student.full_name.lower():
            continue

        student_grps = [g for g in student.groups.all() if g.course_id in target_course_ids]
        if not student_grps:
            continue

        course_obj = student_grps[0].course if student_grps else None
        if not course_obj:
            continue

        plan = plans_map.get((student.id, course_obj.id))
        if plan:
            summary = _plan_summary(plan)
        else:
            summary = {'paid': 0, 'remaining': 0, 'status': 'no_plan', 'payments': []}

        if status_filter and summary['status'] != status_filter:
            continue

        rows.append({
            'student': student,
            'course': course_obj,
            'groups_list': student_grps,
            'plan': plan,
            'summary': summary,
        })

    # Umumiy statistika
    all_plans = list(PaymentPlan.objects.prefetch_related('payments'))
    if course_id:
        all_plans = [p for p in all_plans if str(p.course_id) == str(course_id)]

    total_expected = sum(p.total_amount for p in all_plans)
    total_paid = sum(sum(pay.amount for pay in p.payments.all()) for p in all_plans)
    total_remaining = max(0, total_expected - total_paid)
    complete_count = sum(1 for p in all_plans if sum(pay.amount for pay in p.payments.all()) >= p.total_amount)
    partial_count = sum(
        1 for p in all_plans
        if 0 < sum(pay.amount for pay in p.payments.all()) < p.total_amount
    )
    unpaid_count = sum(1 for p in all_plans if sum(pay.amount for pay in p.payments.all()) == 0)
    no_plan_count = sum(1 for r in rows if r['summary']['status'] == 'no_plan')

    paginator = Paginator(rows, PAGE_SIZE)
    page = paginator.get_page(page_num)

    return render(request, 'payment/list.html', {
        'rows': page.object_list,
        'page': page,
        'paginator': paginator,
        'courses': courses,
        'groups': groups,
        'selected_course_id': course_id,
        'selected_group_id': group_id,
        'status_filter': status_filter,
        'total_expected': total_expected,
        'total_paid': total_paid,
        'total_remaining': total_remaining,
        'complete_count': complete_count,
        'partial_count': partial_count,
        'unpaid_count': unpaid_count,
        'no_plan_count': no_plan_count,
        'total_students': len(rows),
    })


@_superadmin_required
def payment_detail(request, student_id):
    student = get_object_or_404(Student.objects.prefetch_related('groups__course'), id=student_id)
    course_id = request.GET.get('course_id', '')

    courses_of_student = [g.course for g in student.groups.all() if g.course and g.course.is_active]
    unique_courses = list({c.id: c for c in courses_of_student}.values())

    selected_course = None
    if course_id:
        selected_course = next((c for c in unique_courses if str(c.id) == str(course_id)), None)
    if not selected_course and unique_courses:
        selected_course = unique_courses[0]

    plan = None
    summary = None
    if selected_course:
        plan = PaymentPlan.objects.filter(student=student, course=selected_course).prefetch_related('payments__entered_by').first()
        if plan:
            summary = _plan_summary(plan)

    return render(request, 'payment/detail.html', {
        'student': student,
        'courses': unique_courses,
        'selected_course': selected_course,
        'plan': plan,
        'summary': summary,
        'today': timezone.now().date(),
    })


@_superadmin_required
@require_POST
def payment_set_plan(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    try:
        body = json.loads(request.body)
        course_id = body['course_id']
        total_amount = int(body['total_amount'])
        note = body.get('note', '').strip()
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    course = get_object_or_404(Course, id=course_id)
    plan, created = PaymentPlan.objects.get_or_create(
        student=student, course=course,
        defaults={'total_amount': total_amount, 'note': note, 'created_by': request.user}
    )
    if not created:
        plan.total_amount = total_amount
        plan.note = note
        plan.save(update_fields=['total_amount', 'note', 'updated_at'])

    return JsonResponse({'ok': True, 'plan_id': plan.id, 'created': created})


@_superadmin_required
@require_POST
def payment_add(request, plan_id):
    plan = get_object_or_404(PaymentPlan, id=plan_id)
    try:
        body = json.loads(request.body)
        amount = int(body['amount'])
        paid_at = body['paid_at']
        note = body.get('note', '').strip()
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Noto\'g\'ri ma\'lumot'}, status=400)

    payment = Payment.objects.create(
        plan=plan, amount=amount, paid_at=paid_at,
        note=note, entered_by=request.user,
    )
    summary = _plan_summary(plan)
    return JsonResponse({
        'ok': True,
        'payment_id': payment.id,
        'paid': summary['paid'],
        'remaining': summary['remaining'],
        'status': summary['status'],
    })


@_superadmin_required
@require_POST
def payment_delete(request, payment_id):
    payment = get_object_or_404(Payment, id=payment_id)
    plan = payment.plan
    payment.delete()
    summary = _plan_summary(plan)
    return JsonResponse({
        'ok': True,
        'paid': summary['paid'],
        'remaining': summary['remaining'],
        'status': summary['status'],
    })
