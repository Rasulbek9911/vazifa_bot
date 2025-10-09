
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
    Student ro‘yxatdan o‘tadi (telegram_id + full_name + group_id)
    """

    def post(self, request):
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


class TaskSubmitView(APIView):
    """
    Student vazifa yuboradi (telegram_id, topic_id, file_link)
    """

    def post(self, request):
        telegram_id = request.data.get("student_id")   # bu aslida telegram_id
        topic_id = request.data.get("topic_id")
        file_link = request.data.get("file_link")

        # Studentni telegram_id orqali topamiz
        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Serializerga model PKlarini beramiz
        serializer = TaskSerializer(data={
            "student_id": student.id,   # PK kerak
            "topic_id": topic_id,
            "file_link": file_link
        })

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

        start_date = now() - timedelta(days=7)
        students = group.students.all()
        topics = Topic.objects.all()

        # Jadval sarlavhalari
        data = [["Talaba"] + [t.title for t in topics]]

        # Studentlar uchun qatordan-qatordan to‘ldirish
        for student in students:
            row = [student.full_name]
            for topic in topics:
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    submitted_at__gte=start_date
                ).first()
                row.append(task.grade if task and task.grade else "—")
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
                    # 🔔 Adminni ham ogohlantirish kerak bo‘ladi
                    pass

        return Response(data, status=status.HTTP_200_OK)