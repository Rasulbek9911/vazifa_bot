from django.http import HttpResponse
from django.shortcuts import render
from django.core import signing
from django.views.decorators.clickjacking import xframe_options_exempt

from .models import Topic, Task, Group, Student


SCORE_COLORS = {
    'high':   '#d4edda',  # yashil — yaxshi
    'mid':    '#fff3cd',  # sariq — o'rta
    'low':    '#f8d7da',  # qizil — past
    'none':   '#f0f0f0',  # kulrang — topshirmagan
}

MONTH_NAMES = {
    1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
    5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
    9: 'Sentabr', 10: 'Oktabr', 11: 'Noyabr', 12: 'Dekabr',
}


def generate_matrix_token(group_id, topic_ids, year=0, month=0, group_name=''):
    data = {
        'g': group_id,
        't': topic_ids,
        'y': year,
        'm': month,
        'gn': group_name or '',
    }
    return signing.dumps(data, salt='matrix-report', compress=True)


def group_matrix_report(request, token):
    try:
        data = signing.loads(token, salt='matrix-report', max_age=86400 * 7)
    except signing.SignatureExpired:
        return HttpResponse("<h2>Havola muddati o'tgan (7 kun). Botdan yangisini oling.</h2>", status=403)
    except signing.BadSignature:
        return HttpResponse("<h2>Havola noto'g'ri.</h2>", status=403)

    group_id  = data['g']
    topic_ids = data['t']
    year      = data.get('y', 0)
    month     = data.get('m', 0)
    group_name = data.get('gn', '')

    topics = list(Topic.objects.select_related('course').filter(id__in=topic_ids))
    topics = sorted(topics, key=lambda t: topic_ids.index(t.id))

    if group_id == 0:
        tasks = list(
            Task.objects.filter(topic_id__in=topic_ids, task_type='test')
                .select_related('student')
                .exclude(test_answers__isnull=True)
                .exclude(test_answers='')
        )
        if year and month:
            tasks = [t for t in tasks if t.submitted_at and
                     t.submitted_at.year == year and t.submitted_at.month == month]
        student_map = {t.student_id: t.student for t in tasks}
        students = sorted(student_map.values(), key=lambda s: s.full_name)
    else:
        try:
            group = Group.objects.prefetch_related('enrolled_students').get(id=group_id)
        except Group.DoesNotExist:
            return HttpResponse("<h2>Guruh topilmadi.</h2>", status=404)
        students = list(group.enrolled_students.all().order_by('full_name'))
        student_ids = [s.id for s in students]
        tasks = list(
            Task.objects.filter(
                topic_id__in=topic_ids, task_type='test', student_id__in=student_ids
            ).select_related('student')
             .exclude(test_answers__isnull=True)
             .exclude(test_answers='')
        )
        if year and month:
            tasks = [t for t in tasks if t.submitted_at and
                     t.submitted_at.year == year and t.submitted_at.month == month]

    # tasks_map: {topic_id: {student_id: task}}
    tasks_map = {}
    for task in tasks:
        tasks_map.setdefault(task.topic_id, {})[task.student_id] = task

    # Har bir student uchun qator ma'lumotlari
    def score_info(task, topic):
        if task is None:
            return {'text': '—', 'color': SCORE_COLORS['none'], 'val': -1, 'sub': None}
        total_q = len(topic.correct_answers) if topic.correct_answers else 0
        answers = task.test_answers or ''
        correct = topic.correct_answers or {}
        correct_str = next(iter(correct.values()), '') if correct else ''
        if total_q == 50:
            fan = score_50_fan(answers, correct_str)
            ped = score_50_ped(answers, correct_str)
            pct = ((fan + ped) / 50 * 100)
            return {
                'text': f"{fan}/35",
                'sub':  f"Ped:{ped}/15",
                'color': _grade_color(pct, 100),
                'val': fan + ped,
            }
        else:
            sc = sum(1 for i, ch in enumerate(answers) if i < len(correct_str) and ch == correct_str[i])
            pct = (sc / total_q * 100) if total_q else 0
            return {
                'text': f"{sc}/{total_q}",
                'sub': None,
                'color': _grade_color(pct, 100),
                'val': sc,
            }

    rows = []
    for student in students:
        cells = []
        total_val = 0
        submitted = 0
        for topic in topics:
            task = tasks_map.get(topic.id, {}).get(student.id)
            info = score_info(task, topic)
            cells.append(info)
            if info['val'] >= 0:
                total_val += info['val']
                submitted += 1
        rows.append({
            'name': student.full_name,
            'cells': cells,
            'submitted': submitted,
            'total_val': total_val,
        })

    # Jami ball bo'yicha tartiblash
    rows.sort(key=lambda r: r['total_val'], reverse=True)

    scope = group_name or 'Barcha guruhlar'
    month_label = f"{MONTH_NAMES[month]} {year}" if (year and month) else 'Barcha vaqt'
    course_name = topics[0].course.name if topics else ''

    context = {
        'topics': topics,
        'rows': rows,
        'scope': scope,
        'month_label': month_label,
        'course_name': course_name,
        'total_students': len(rows),
        'total_topics': len(topics),
    }
    return render(request, 'report_matrix.html', context)


def score_50_fan(answers, correct_str):
    return sum(1 for i in range(min(35, len(answers))) if i < len(correct_str) and answers[i] == correct_str[i])


def score_50_ped(answers, correct_str):
    return sum(1 for i in range(35, min(50, len(answers))) if i < len(correct_str) and answers[i] == correct_str[i])


def _grade_color(pct, max_val):
    if pct >= max_val * 0.7:
        return SCORE_COLORS['high']
    if pct >= max_val * 0.5:
        return SCORE_COLORS['mid']
    return SCORE_COLORS['low']
