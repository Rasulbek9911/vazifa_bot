

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
    Agar student allaqachon ro'yxatdan o'tgan bo'lsa, xatolik beradi
    """

    def post(self, request):
        telegram_id = request.data.get("telegram_id")
        
        # Agar student allaqachon ro'yxatdan o'tgan bo'lsa, xatolik beramiz
        if telegram_id:
            try:
                student = Student.objects.get(telegram_id=telegram_id)
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
        from .models import Topic
        from .serializers import TopicSerializer

        topics = Topic.objects.all().order_by('id')
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
    Student vazifa yuboradi (telegram_id, topic_id, task_type, course_type, file_link/test_code/test_answers, grade)
    """

    def post(self, request):
        telegram_id = request.data.get("student_id")   # bu aslida telegram_id
        topic_id = request.data.get("topic_id")
        task_type = request.data.get("task_type", "test")
        course_type = request.data.get("course_type", "milliy_sert")
        file_link = request.data.get("file_link")
        test_code = request.data.get("test_code")
        test_answers = request.data.get("test_answers")
        grade = request.data.get("grade")

        # Studentni telegram_id orqali topamiz
        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Serializerga model PKlarini beramiz
        data = {
            "student_id": student.id,   # PK kerak
            "topic_id": topic_id,
            "task_type": task_type,
            "course_type": course_type,
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
        
        serializer = TaskSerializer(data=data)

        if serializer.is_valid():
            task = serializer.save()
            return Response(TaskSerializer(task).data, status=status.HTTP_201_CREATED)

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
        
        # ✨ YANGI: Guruhning course_type'iga mos mavzularni olamiz
        group_course_type = group.course_type
        topics = Topic.objects.filter(is_active=True, course_type=group_course_type)
        
        # Agar active mavzu yo'q bo'lsa, PDF yaratmaymiz
        if not topics.exists():
            return HttpResponse("No active topics", status=404)

        # Stillar
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        styles = getSampleStyleSheet()
        
        # Ism ustuni uchun stil
        name_style = ParagraphStyle(
            'NameStyle',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
            wordWrap='CJK'
        )
        
        # Vertikal mavzu sarlavhasi uchun stil
        vertical_style = ParagraphStyle(
            'VerticalStyle',
            parent=styles['Normal'],
            fontSize=7,
            leading=8,
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
        
        header.append(Paragraph("<b>O'rtacha</b>", styles['Heading4']))
        data = [header]

        # Studentlar uchun qatordan-qatordan to'ldirish
        student_rows = []
        for student in students:
            # Ismni Paragraph sifatida qo'shamiz - avtomatik word wrap
            row = [Paragraph(student.full_name, name_style)]
            grades = []
            
            for topic in topics:
                task_type = 'test' if topic.correct_answers else 'assignment'
                
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=task_type,
                    course_type=group_course_type
                ).first()
                
                if task and task.grade is not None:
                    grade = task.grade
                else:
                    grade = 0
                
                row.append(str(grade) if grade > 0 else "—")
                grades.append(grade)
            
            # O'rtacha bahoni hisoblash
            if grades:
                average = sum(grades) / len(grades)
                row.append(f"{average:.1f}")
                student_rows.append((row, average))
            else:
                row.append("—")
                student_rows.append((row, 0))
        
        # O'rtacha bo'yicha kamayish tartibida sort
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

        doc = SimpleDocTemplate(response, pagesize=landscape(A4), 
                                leftMargin=20, rightMargin=20, 
                                topMargin=20, bottomMargin=20)
        
        # Sahifa o'lchamlari
        page_width = landscape(A4)[0] - 40  # minus margins
        
        # Ustun kengliklarini hisoblash
        name_col_width = 150  # Ism ustuni uchun keng joy
        num_topics = len(topics)
        
        # Qolgan joy mavzular va o'rtacha uchun
        remaining = page_width - name_col_width
        topic_col_width = remaining / (num_topics + 1)  # +1 o'rtacha uchun
        
        # Agar mavzular juda ko'p bo'lsa, har bir mavzu uchun minimal 25 point
        topic_col_width = max(topic_col_width, 25)
        
        col_widths = [name_col_width]  # Ism
        col_widths.extend([topic_col_width] * num_topics)  # Mavzular
        col_widths.append(topic_col_width)  # O'rtacha
        
        table = Table(data, colWidths=col_widths, repeatRows=1)

        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),  # Ism ustuni chapga
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),  # Qolgan hamma markazga
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),  # Vertikal o'rtaga
            ("FONTNAME", (0, 0), (-1, 0), font_name_bold),
            ("FONTNAME", (0, 1), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
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
