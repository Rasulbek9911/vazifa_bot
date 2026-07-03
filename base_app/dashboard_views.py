from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count
from django.core.paginator import Paginator

from .models import Student, FollowUp, CallHistory, PaymentPlan, Payment, Course


def logout_view(request):
    auth_logout(request)
    return redirect('/accounts/login/')


@login_required
def home(request):
    if request.user.is_superuser:
        return redirect('/dashboard/')
    return redirect('/followup/')


@login_required
def dashboard(request):
    if not request.user.is_superuser:
        return redirect('/followup/')

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # Followup stats
    total_unsubmitted = FollowUp.objects.count()
    called_count = FollowUp.objects.exclude(called_at__isnull=True).count()
    not_called_count = FollowUp.objects.filter(called_at__isnull=True).count()

    # Bugungi calllar
    today_calls = CallHistory.objects.filter(called_at__gte=today_start).count()

    # Operator stats (bugun)
    operator_stats = list(
        CallHistory.objects.filter(called_at__gte=today_start)
        .values('operator__username', 'operator__first_name', 'operator__last_name')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    # Payment stats
    all_plans = list(PaymentPlan.objects.prefetch_related('payments'))
    total_expected = sum(p.total_amount for p in all_plans)
    total_paid = sum(sum(pay.amount for pay in p.payments.all()) for p in all_plans)
    complete_count = sum(1 for p in all_plans if sum(pay.amount for pay in p.payments.all()) >= p.total_amount and p.total_amount > 0)
    partial_count = sum(1 for p in all_plans if 0 < sum(pay.amount for pay in p.payments.all()) < p.total_amount)

    return render(request, 'dashboard/home.html', {
        'total_unsubmitted': total_unsubmitted,
        'called_count': called_count,
        'not_called_count': not_called_count,
        'today_calls': today_calls,
        'operator_stats': operator_stats,
        'total_expected': total_expected,
        'total_paid': total_paid,
        'total_remaining': max(0, total_expected - total_paid),
        'complete_count': complete_count,
        'partial_count': partial_count,
    })


@login_required
def call_history(request):
    if not request.user.is_superuser:
        return redirect('/followup/')

    from django.contrib.auth.models import User
    from django.db.models import Q

    operator_id = request.GET.get('operator_id', '')
    result_filter = request.GET.get('result', '')
    date_filter = request.GET.get('date', '')
    search_q = request.GET.get('q', '').strip().lower()
    page_num = request.GET.get('page', 1)

    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=today_start.weekday())

    # Operator statistikasi (filtrsiz, umumiy)
    from django.db.models import Count as DjCount
    op_stats_qs = (
        CallHistory.objects
        .values('operator__id', 'operator__username', 'operator__first_name', 'operator__last_name')
        .annotate(
            today=DjCount('id', filter=Q(called_at__gte=today_start)),
            this_week=DjCount('id', filter=Q(called_at__gte=week_start)),
            total=DjCount('id'),
            answered=DjCount('id', filter=Q(result='answered')),
            not_answered=DjCount('id', filter=Q(result='not_answered')),
        )
        .filter(total__gt=0)
        .order_by('-total')
    )
    op_stats = list(op_stats_qs)

    qs = CallHistory.objects.select_related('student', 'operator').order_by('-called_at')

    if operator_id:
        qs = qs.filter(operator_id=operator_id)
    if result_filter:
        qs = qs.filter(result=result_filter)
    if date_filter:
        try:
            from datetime import datetime
            d = datetime.strptime(date_filter, '%Y-%m-%d').date()
            qs = qs.filter(called_at__date=d)
        except ValueError:
            pass
    if search_q:
        qs = qs.filter(student__full_name__icontains=search_q)

    operators = User.objects.filter(is_staff=True).order_by('username')
    paginator = Paginator(qs, 50)
    page = paginator.get_page(page_num)

    return render(request, 'dashboard/call_history.html', {
        'page': page,
        'paginator': paginator,
        'operators': operators,
        'op_stats': op_stats,
        'selected_operator': operator_id,
        'result_filter': result_filter,
        'date_filter': date_filter,
        'result_choices': CallHistory.RESULT_CHOICES,
        'total_count': qs.count(),
    })


@login_required
def delete_student(request, student_id):
    if not request.user.is_superuser:
        from django.http import JsonResponse
        return JsonResponse({'ok': False, 'error': 'Ruxsat yo\'q'}, status=403)
    if request.method != 'POST':
        from django.http import JsonResponse
        return JsonResponse({'ok': False}, status=405)

    from django.shortcuts import get_object_or_404
    from django.http import JsonResponse
    student = get_object_or_404(Student, id=student_id)
    name = student.full_name
    student.delete()
    return JsonResponse({'ok': True, 'name': name})
