

from reportlab.lib.pagesizes import A4, landscape
from django.http import HttpResponse
from django.utils.timezone import now, timedelta
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
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

        topics = Topic.objects.all()
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
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Serializerga model PKlarini beramiz
        data = {
            "student_id": student.id,   # PK kerak
            "topic_id": topic_id,
            "task_type": task_type,
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
        
        # FAQAT active mavzularni olish (vaqt chegarasiz - barcha vazifalar)
        topics = Topic.objects.filter(is_active=True)
        
        # Agar active mavzu yo'q bo'lsa, PDF yaratmaymiz
        if not topics.exists():
            return HttpResponse("No active topics", status=404)

        # Jadval sarlavhalari - har bir mavzu uchun turi ko'rsatiladi
        header = ["Talaba"]
        for t in topics:
            # Mavzu turini aniqlash (correct_answers bor bo'lsa Test, yo'q bo'lsa Maxsus)
            topic_type = "📝Test" if t.correct_answers else "📋Maxsus"
            header.append(f"{t.title}\n({topic_type})")
        header.append("O'rtacha")
        data = [header]

        # Studentlar uchun qatordan-qatordan to'ldirish
        student_rows = []
        for student in students:
            row = [student.full_name]
            grades = []
            for topic in topics:
                # Mavzu turiga mos task_type ni qidiramiz
                task_type = 'test' if topic.correct_answers else 'assignment'
                
                # Vaqt chegarasiz - barcha vazifalarni ko'ramiz
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=task_type
                ).first()
                grade = task.grade if task and task.grade else None
                row.append(grade if grade else "—")
                if grade:
                    grades.append(grade)
            
            # O'rtacha bahoni hisoblash
            if grades:
                average = sum(grades) / len(grades)
                row.append(f"{average:.1f}")
                student_rows.append((row, average))
            else:
                row.append("—")
                student_rows.append((row, 0))  # Bahosi yo'q bo'lsa 0
        
        # O'rtacha bo'yicha tartiblash (eng yuqoridan pastga)
        student_rows.sort(key=lambda x: x[1], reverse=True)
        
        # Faqat qatorlarni qo'shamiz (o'rtacha qiymatini emas)
        for row, _ in student_rows:
            data.append(row)

        # PDF response
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="weekly_report_{group.name}.pdf"'

        doc = SimpleDocTemplate(response, pagesize=landscape(A4))
        table = Table(data, repeatRows=1)

        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
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
