import logging

from reportlab.lib.pagesizes import A4, landscape
from django.http import HttpResponse
from django.utils.timezone import now, timedelta
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Student, Task, Group, Topic
from .serializers import StudentSerializer, TaskSerializer

logger = logging.getLogger(__name__)

class StudentListView(APIView):
    """
    Studentlar ro'yxati (group_id bo'yicha filter)
    GET /api/students/?group_id=1
    """
    def get(self, request):
        group_id = request.query_params.get("group_id")
        if group_id:
            students = Student.objects.filter(group_id=group_id)
        else:
            students = Student.objects.all()
        from .serializers import StudentSerializer
        serializer = StudentSerializer(students, many=True)
        return Response(serializer.data)

class StudentIsRegisteredView(APIView):
    """
    Student ro‘yxatdan o‘tgan yoki yo‘qligini tekshiradi (telegram_id)
    """

    def get(self, request, pk):
        try:
            student = Student.objects.get(telegram_id=pk)
            serializer = StudentSerializer(student)
            return Response(serializer.data)
        except Student.DoesNotExist:
            return Response({"error": "Student not found"}, status=status.HTTP_404_NOT_FOUND)


class StudentRegisterView(APIView):
    """
    Student ro'yxatdan o'tadi (telegram_id + full_name + group_id)
    Agar student mavjud bo'lsa va yangi guruh berilsa, groups ga qo'shadi
    """

    def post(self, request):
        telegram_id = request.data.get("telegram_id")
        group_id = request.data.get("group_id")
        full_name = request.data.get("full_name")
        
        # Agar student allaqachon ro'yxatdan o'tgan bo'lsa
        if telegram_id:
            try:
                student = Student.objects.get(telegram_id=telegram_id)
                
                # Agar yangi guruh berilsa, groups ga qo'shamiz
                if group_id:
                    try:
                        new_group = Group.objects.get(id=group_id)
                        
                        # Avval shu guruhda borligini tekshiramiz
                        all_groups = student.get_all_groups()
                        if new_group not in all_groups:
                            student.groups.add(new_group)
                            return Response(
                                {"message": f"{student.full_name}, siz yangi guruhga qo'shildingiz: {new_group.name}"},
                                status=status.HTTP_200_OK
                            )
                        else:
                            return Response(
                                {"error": f"Siz allaqachon {new_group.name} guruhida ro'yxatdan o'tgansiz"},
                                status=status.HTTP_400_BAD_REQUEST
                            )
                    except Group.DoesNotExist:
                        return Response(
                            {"error": "Guruh topilmadi"},
                            status=status.HTTP_404_NOT_FOUND
                        )
                
                return Response(
                    {"error": f"Siz allaqachon {student.full_name} ismi bilan ro'yxatdan o'tgansiz"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Student.DoesNotExist:
                pass
        
        serializer = StudentSerializer(data=request.data)
        if serializer.is_valid():
            student = serializer.save()
            return Response(StudentSerializer(student).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentChangeGroupView(APIView):
    """
    Student guruhini almashtiradi
    """

    def patch(self, request, pk):
        try:
            student = Student.objects.get(pk=pk)
        except Student.DoesNotExist:
            return Response({"error": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = StudentSerializer(
            student, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class StudentUpdateNameView(APIView):
    """
    Student ismini o'zgartiradi (telegram_id orqali)
    PATCH /api/students/{telegram_id}/update_name/
    Body: {"full_name": "Yangi Ism"}
    """

    def patch(self, request, pk):
        telegram_id = pk
        new_name = request.data.get("full_name", "").strip()
        
        if not new_name:
            return Response({"error": "Ism kiritilmagan"}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_name) < 3:
            return Response({"error": "Ism juda qisqa"}, status=status.HTTP_400_BAD_REQUEST)
        
        if len(new_name) > 100:
            return Response({"error": "Ism juda uzun"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            student = Student.objects.get(telegram_id=telegram_id)
            student.full_name = new_name
            student.save()
            return Response(StudentSerializer(student).data, status=status.HTTP_200_OK)
        except Student.DoesNotExist:
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)


class GroupsListView(APIView):
    """
    Guruhlar ro‘yxatini qaytaradi
    """

    def get(self, request):
        from .serializers import GroupSerializer
        groups = Group.objects.all()
        serializer = GroupSerializer(groups, many=True)
        # current_size ni ham qo'shamiz
        data = serializer.data
        for i, group in enumerate(groups):
            data[i]["current_size"] = group.students.count()
        return Response(data)


class TopicsListView(APIView):
    """
    Mavzular ro‘yxatini qaytaradi
    """

    def get(self, request):
        from .models import Topic, Student, Group
        from .serializers import TopicSerializer
        from django.db.models import Q

        student_id = request.query_params.get('student_id')
        if student_id:
            try:
                student = Student.objects.get(telegram_id=student_id)
            except Student.DoesNotExist:
                return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)
            
            # ✨ YANGI: Student barcha guruhlarini olish (group + groups)
            all_groups = student.get_all_groups()
            
            # Barcha course ID larni yig'ish
            course_ids = set()
            for grp in all_groups:
                if grp.course:
                    course_ids.add(grp.course.id)
            
            # Active topiclarni filter qilish
            topics = Topic.objects.filter(is_active=True, course_id__in=course_ids).order_by('id')
        else:
            # Agar course_id query parametresi bo'lsa, course bo'yicha filter qilamiz
            course_id = request.query_params.get('course_id')
            if course_id:
                topics = Topic.objects.filter(is_active=True, course_id=course_id).order_by('id')
            else:
                topics = Topic.objects.filter(is_active=True, course__isnull=False).order_by('id')
        serializer = TopicSerializer(topics, many=True)
        return Response(serializer.data)

class TopicDetailView(APIView):
    """
    Bitta mavzu detail (GET)
    """
    def get(self, request, pk):
        try:
            topic = Topic.objects.get(pk=pk)
        except Topic.DoesNotExist:
            return Response({"error": "Mavzu topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        from .serializers import TopicSerializer
        serializer = TopicSerializer(topic)
        return Response(serializer.data)

    def patch(self, request, pk):
        try:
            topic = Topic.objects.get(pk=pk)
        except Topic.DoesNotExist:
            return Response({"error": "Mavzu topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        correct_answers = request.data.get("correct_answers")
        if correct_answers is not None:
            topic.correct_answers = correct_answers
            topic.save()
            from .serializers import TopicSerializer
            serializer = TopicSerializer(topic)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response({"error": "correct_answers kerak"}, status=status.HTTP_400_BAD_REQUEST)


class TaskSubmitView(APIView):
    """
    Student vazifa yuboradi (telegram_id, topic_id, task_type, file_link/test_code/test_answers, grade)
    course_type avtomatik topic.course dan olinadi
    """

    def post(self, request):
        telegram_id = request.data.get("student_id")   # bu aslida telegram_id
        topic_id = request.data.get("topic_id")
        task_type = request.data.get("task_type", "test")
        file_link = request.data.get("file_link")
        test_code = request.data.get("test_code")
        test_answers = request.data.get("test_answers")
        grade = request.data.get("grade")

        # Studentni telegram_id orqali topamiz
        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            logger.error(f"Student topilmadi: telegram_id={telegram_id}")
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Topic'ni topib, course_type ni aniqlaymiz
        try:
            topic = Topic.objects.get(id=topic_id)
        except Topic.DoesNotExist:
            logger.error(f"Topic topilmadi: topic_id={topic_id}")
            return Response({"error": "Topic topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Serializerga model PKlarini beramiz
        data = {
            "student_id": student.id,   # PK kerak
            "topic_id": topic_id,
            "task_type": task_type,
            # course_type yubormaslik - u deprecated va validatsiya muammosi keltirib chiqaradi
            # Backend topicdan kerak bo'lsa oladi
        }
        
        # Optional fields
        if file_link:
            data["file_link"] = file_link
        if test_code:
            data["test_code"] = test_code
        if test_answers:
            data["test_answers"] = test_answers
        if grade is not None:
            data["grade"] = grade
        
        logger.info(f"TaskSubmitView payload: {data}")
        
        serializer = TaskSerializer(data=data)

        if serializer.is_valid():
            task = serializer.save()
            logger.info(f"Task saqlandi: task_id={task.id}, student={student.full_name}, topic={topic.title}")
            return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

        logger.error(f"Serializer validation xatolari: {serializer.errors}, telegram_id={telegram_id}, topic_id={topic_id}")
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class TaskListView(APIView):
    """
    Student vazifalari ro'yxati (hamma yoki faqat student_id bo'yicha)
    GET /api/tasks/
    GET /api/tasks/?student_id=123456
    """

    def get(self, request):
        student_id = request.query_params.get("student_id")

        if student_id:
            try:
                student = Student.objects.get(telegram_id=student_id)
            except Student.DoesNotExist:
                return Response(
                    {"error": "Student topilmadi"},
                    status=status.HTTP_404_NOT_FOUND
                )
            tasks = Task.objects.filter(student=student)
        else:
            tasks = Task.objects.all()

        serializer = TaskSerializer(tasks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TaskUpdateView(APIView):
    """
    Taskni yangilash (asosan grade qo‘yish)
    PATCH /api/tasks/<id>/
    """

    def patch(self, request, pk):
        try:
            task = Task.objects.get(pk=pk)
        except Task.DoesNotExist:
            return Response({"error": "Task topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        grade = request.data.get("grade")
        if grade not in [3, 4, 5]:
            return Response({"error": "Noto‘g‘ri baho"}, status=status.HTTP_400_BAD_REQUEST)

        task.grade = grade
        task.save()

        return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)


class WeeklyReportPDFView(APIView):
    def get(self, request, group_id):
        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return HttpResponse("Group not found", status=404)

        students = group.students.all()

        # Guruhning course yoki course_type'iga mos mavzularni olamiz
        group_course = getattr(group, "course", None)
        if group_course:
            # Barcha active topiclarni olamiz (id bo'yicha tartibda)
            all_topics = Topic.objects.filter(is_active=True, course=group_course).order_by('id')
            # Oxirgi 10 ta topicni olamiz (teskari tartibda keyin o'giramiz)
            topics_list = list(all_topics)
            topics = topics_list[-10:] if len(topics_list) >= 10 else topics_list
        else:
            topics = []
            all_topics = Topic.objects.none()

        # Agar active mavzu yo'q bo'lsa, PDF yaratmaymiz
        if not topics:
            return HttpResponse("No active topics", status=404)

        # Stillar
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        styles = getSampleStyleSheet()
        
        # Ism ustuni uchun stil
        name_style = ParagraphStyle(
            'NameStyle',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
            wordWrap='CJK'
        )
        
        # Vertikal mavzu sarlavhasi uchun stil
        vertical_style = ParagraphStyle(
            'VerticalStyle',
            parent=styles['Normal'],
            fontSize=6,
            leading=7,
            alignment=TA_CENTER,
        )
        
        # Jadval sarlavhalari - mavzularni vertikal qilamiz
        header = [Paragraph("<b>Talaba</b>", styles['Heading4'])]
        
        for t in topics:
            # Mavzu nomini vertikal qilish - har bir belgini yangi qatorda
            topic_type = "📝" if t.correct_answers else "📋"
            # Har bir belgini <br/> bilan ajratamiz
            vertical_text = "<br/>".join(list(t.title))
            vertical_text += f"<br/><font size='5'>{topic_type}</font>"
            header.append(Paragraph(vertical_text, vertical_style))
        
        # Umumiy o'rtacha ustuni qo'shamiz
        header.append(Paragraph("<b>U<br/>m<br/>u<br/>m<br/>i<br/>y<br/><br/>o<br/>'<br/>r<br/>t<br/>a<br/>c<br/>h<br/>a</b>", vertical_style))
        data = [header]

        # Studentlar uchun qatordan-qatordan to'ldirish
        student_rows = []
        for student in students:
            # Ismni Paragraph sifatida qo'shamiz - avtomatik word wrap
            row = [Paragraph(student.full_name, name_style)]
            grades_10 = []  # Oxirgi 10 ta topic uchun
            
            for topic in topics:
                task_type = 'test' if topic.correct_answers else 'assignment'

                # Faqat shu kurs uchun taskni olamiz
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=task_type,
                    topic__course=group.course
                ).first()

                if task and task.grade is not None:
                    grade = task.grade
                else:
                    grade = 0

                row.append(str(grade) if grade > 0 else "—")
                grades_10.append(grade)
            
            # Umumiy o'rtacha bahoni hisoblash (barcha active topiclar bo'yicha)
            all_grades = []
            for topic in all_topics:
                task_type = 'test' if topic.correct_answers else 'assignment'
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=task_type,
                    topic__course=group.course
                ).first()
                
                if task and task.grade is not None:
                    all_grades.append(task.grade)
            
            # Umumiy o'rtacha (barcha active topiclar)
            if all_grades:
                overall_avg = sum(all_grades) / len(all_grades)
                row.append(f"{overall_avg:.1f}")
                student_rows.append((row, overall_avg))
            else:
                row.append("—")
                student_rows.append((row, 0))
        
        # Umumiy o'rtacha bo'yicha kamayish tartibida sort
        student_rows.sort(key=lambda x: x[1], reverse=True)
        
        # Qatorlarni qo'shamiz
        for row, _ in student_rows:
            data.append(row)

        # PDF response
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="weekly_report_{group.name}.pdf"'

        # Kiril harflarini qo'llab-quvvatlaydigan font
        try:
            # DejaVu Sans font (ko'pchilik Linux sistemalarida mavjud)
            pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
            font_name = 'DejaVuSans'
            font_name_bold = 'DejaVuSans-Bold'
        except:
            # Agar font topilmasa, standart fontni ishlat
            font_name = 'Helvetica'
            font_name_bold = 'Helvetica-Bold'

        from reportlab.lib.pagesizes import A3
        
        doc = SimpleDocTemplate(response, pagesize=landscape(A3), 
                                leftMargin=15, rightMargin=15, 
                                topMargin=15, bottomMargin=15)
        
        # Sahifa o'lchamlari
        page_width = landscape(A3)[0] - 30  # minus margins
        
        # Ustun kengliklarini hisoblash
        num_topics = len(topics)
        
        # Ism ustuni uchun minimal 150 point
        name_col_width = 150
        
        # Qolgan joy mavzular va umumiy o'rtacha uchun
        remaining = page_width - name_col_width
        topic_col_width = remaining / (num_topics + 1)  # +1 umumiy o'rtacha uchun
        
        # Har bir mavzu uchun minimal 22 point
        topic_col_width = max(topic_col_width, 22)
        
        col_widths = [name_col_width]  # Ism
        col_widths.extend([topic_col_width] * num_topics)  # Mavzular
        col_widths.append(topic_col_width * 1.2)  # Umumiy o'rtacha biroz kengroq
        
        table = Table(data, colWidths=col_widths, repeatRows=1)

        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),  # Ism ustuni chapga
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),  # Qolgan hamma markazga
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),  # Vertikal o'rtaga
            ("FONTNAME", (0, 0), (-1, 0), font_name_bold),
            ("FONTNAME", (0, 1), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ])
        table.setStyle(style)

        doc.build([table])
        return response

# vazifalar topshirmagan studentlarni tekshiradi
class UnsubmittedTasksCheckView(APIView):
    def get(self, request):
        # faqat o‘tilgan mavzular
        active_topics = Topic.objects.filter(is_active=True)

        data = []
        for student in Student.objects.all():
            # studentning bajarganlari
            submitted_tasks = Task.objects.filter(student=student, topic__in=active_topics)

            # qaysi mavzularni bajarmagan
            unsubmitted = active_topics.exclude(id__in=submitted_tasks.values_list("topic_id", flat=True))

            # agar bajarilmagan bo‘lsa – ro‘yxatga qo‘shamiz
            if unsubmitted.exists():
                data.append({
                    "student": student.full_name,
                    "telegram_id": student.telegram_id,
                    "unsubmitted_count": unsubmitted.count(),
                    "unsubmitted_topics": [t.title for t in unsubmitted]
                })

                # 🔔 ogohlantirish (student)
                # Bot orqali yuboriladigan joyda ishlatiladi
                if unsubmitted.count() >= 3:
                    # 🔔 Adminni ham ogohlantirish kerak bo'ladi
                    pass

        return Response(data, status=status.HTTP_200_OK)


# Invite Code views
class CreateInviteCodeView(APIView):
    """
    Admin invite code yaratadi
    POST /api/invites/create/
    """
    def post(self, request):
        from .models import InviteCode
        from .serializers import InviteCodeSerializer
        import uuid
        
        admin_id = request.data.get("admin_id")
        if not admin_id:
            return Response({"error": "admin_id kerak"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Yangi invite code yaratish
        invite = InviteCode.objects.create(
            code=str(uuid.uuid4())[:8],  # 8 belgili kod
            created_by=admin_id
        )
        
        serializer = InviteCodeSerializer(invite)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ValidateInviteCodeView(APIView):
    """
    Invite code ni tekshirish va ishlatish
    POST /api/invites/validate/
    """
    def post(self, request):
        from .models import InviteCode
        from django.utils import timezone
        
        code = request.data.get("code")
        user_id = request.data.get("user_id")
        
        if not code or not user_id:
            return Response({"error": "code va user_id kerak"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invite = InviteCode.objects.get(code=code)
        except InviteCode.DoesNotExist:
            return Response({"error": "Invite code topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        
        if invite.is_used:
            return Response({"error": "Bu invite code allaqachon ishlatilgan"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Invite code ni ishlatilgan deb belgilash
        invite.is_used = True
        invite.used_by = user_id
        invite.used_at = timezone.now()
        invite.save()
        
        return Response({"success": True, "message": "Invite code qabul qilindi"}, status=status.HTTP_200_OK)


class TopicCreateView(APIView):
    """
    Yangi Topic yaratish (Admin uchun)
    POST /api/topics/create/
    Body: {
        "course_id": 1,
        "title": "Mavzu nomi",
        "deadline": "2026-02-15T23:59:59Z",  # optional
        "is_active": false  # default: false
    }
    """
    def post(self, request):
        from .models import Topic, Course
        from .serializers import TopicSerializer
        from django.utils.dateparse import parse_datetime
        
        course_id = request.data.get("course_id")
        title = request.data.get("title")
        deadline_str = request.data.get("deadline")
        is_active = request.data.get("is_active", False)
        
        # Validatsiya
        if not course_id or not title:
            return Response(
                {"error": "course_id va title majburiy"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Course mavjudligini tekshirish
        try:
            course = Course.objects.get(id=course_id)
        except Course.DoesNotExist:
            return Response(
                {"error": "Course topilmadi"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Deadline ni parse qilish
        deadline = None
        if deadline_str:
            deadline = parse_datetime(deadline_str)
            if not deadline:
                return Response(
                    {"error": "Deadline formati noto'g'ri. ISO 8601 format: 2026-02-15T23:59:59Z"},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Topic yaratish
        topic = Topic.objects.create(
            course=course,
            title=title,
            deadline=deadline,
            is_active=is_active
        )
        
        serializer = TopicSerializer(topic)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
