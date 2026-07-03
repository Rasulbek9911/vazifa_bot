import logging

from reportlab.lib.pagesizes import A4, landscape
from django.http import HttpResponse
from django.utils.timezone import now, timedelta
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Flowable
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Student, Task, Group, Topic, CoinWallet, CoinTransaction, AttendanceSession, Attendance
from .serializers import StudentSerializer, TaskSerializer
from .coins import award_task_coins

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

    def patch(self, request, telegram_id):
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


class StudentResultsView(APIView):
    """
    Student natijalarini mavzular bo'yicha olish
    GET /api/students/{telegram_id}/results/
    
    Natija:
    {
        "full_name": "Student Nomi",
        "total_score": 100,
        "results": [
            {
                "topic_id": 1,
                "topic_title": "Mavzu nomi",
                "course_type": "milliy_sert",
                "tasks": [
                    {
                        "task_type": "test",
                        "grade": 45,
                        "submitted_at": "2026-01-15T10:30:00Z"
                    },
                    {
                        "task_type": "assignment",
                        "grade": 50,
                        "submitted_at": "2026-01-16T14:20:00Z"
                    }
                ],
                "average_score": 47.5
            }
        ]
    }
    """

    def get(self, request, pk):
        telegram_id = pk
        
        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)
        
        # Studentning barcha vazifalarini mavzular bo'yicha guruhlash
        tasks = Task.objects.filter(
            student=student
        ).select_related('topic', 'topic__course').order_by('submitted_at')
        
        # Mavzular bo'yicha guruhlash
        results_by_topic = {}
        total_score = 0
        task_count = 0
        
        for task in tasks:
            topic_id = task.topic.id
            
            if topic_id not in results_by_topic:
                results_by_topic[topic_id] = {
                    "topic_id": topic_id,
                    "topic_title": task.topic.title,
                    "course_type": task.topic.course.code if task.topic.course else None,
                    "tasks": []
                }
            
            # Vazifa ma'lumotlarini qo'shish
            task_info = {
                "task_type": task.task_type,
                "task_type_display": "📝 Test" if task.task_type == "test" else "📋 Maxsus topshiriq",
                "grade": task.grade if task.grade else 0,
                "submitted_at": task.submitted_at.isoformat() if task.submitted_at else None
            }
            
            results_by_topic[topic_id]["tasks"].append(task_info)
            
            if task.grade:
                total_score += task.grade
                task_count += 1
        
        # O'rtacha ballni hisoblash har bir mavzu uchun
        for topic_data in results_by_topic.values():
            if topic_data["tasks"]:
                avg_score = sum(t["grade"] for t in topic_data["tasks"]) / len(topic_data["tasks"])
                topic_data["average_score"] = round(avg_score, 2)
            else:
                topic_data["average_score"] = 0
        
        # Natijani qaytarish
        return Response({
            "full_name": student.full_name,
            "total_score": total_score,
            "total_tasks": task_count,
            "average_score": round(total_score / task_count, 2) if task_count > 0 else 0,
            "results": list(results_by_topic.values())
        }, status=status.HTTP_200_OK)


class GroupsListView(APIView):
    """
    Guruhlar ro‘yxatini qaytaradi
    """

    def get(self, request):
        from .serializers import GroupSerializer
        groups = Group.objects.filter(course__is_active=True)
        serializer = GroupSerializer(groups, many=True)
        # current_size ni ham qo'shamiz
        data = serializer.data
        for i, group in enumerate(groups):
            data[i]["current_size"] = group.enrolled_students.count()
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
            
            # Active topiclarni filter qilish (faqat faol kurslar)
            topics = Topic.objects.filter(is_active=True, course_id__in=course_ids, course__is_active=True).order_by('id')
        else:
            course_id = request.query_params.get('course_id')
            show_all = request.query_params.get('all')  # admin: barcha topiclar (inactive ham)
            if show_all and course_id:
                topics = Topic.objects.filter(course_id=course_id).order_by('id')
            elif course_id:
                topics = Topic.objects.filter(is_active=True, course_id=course_id).order_by('id')
            elif show_all:
                topics = Topic.objects.filter(course__isnull=False).order_by('id')
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

            # Test uchun tanga berish (grade set bo'lsa)
            coin_info = None
            if task.task_type == 'test' and task.grade is not None:
                from django.utils import timezone as tz
                deadline_passed = bool(topic.deadline and tz.now() > topic.deadline)
                try:
                    coin_info = award_task_coins(student, topic, task.grade, deadline_passed, 'test')
                except Exception as e:
                    logger.error(f"Tanga berish xatoligi: {e}")

            resp_data = TaskSerializer(task).data
            if coin_info:
                resp_data['coin_info'] = coin_info
            return Response(resp_data, status=status.HTTP_201_CREATED)

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

        # Assignment uchun tanga berish (bir marta)
        try:
            award_task_coins(task.student, task.topic, task.grade, False, 'assignment')
        except Exception as e:
            logger.error(f"Assignment tanga berish xatoligi: {e}")

        return Response(TaskSerializer(task).data, status=status.HTTP_200_OK)


class RotatedText(Flowable):
    """Matnni 90 daraja aylantiradi (pastdan tepaga)"""
    def __init__(self, text, font_name='Helvetica', font_size=6):
        Flowable.__init__(self)
        self.text = text
        self.font_name = font_name
        self.font_size = font_size

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        canvas.rotate(90)
        canvas.setFont(self.font_name, self.font_size)
        canvas.drawString(3, -self.font_size * 0.8, self.text)
        canvas.restoreState()

    def wrap(self, availWidth, availHeight):
        text_width = stringWidth(self.text, self.font_name, self.font_size)
        self.width = availWidth
        self.height = text_width + 6
        return self.width, self.height


class WeeklyReportPDFView(APIView):
    def get(self, request, group_id):
        try:
            group = Group.objects.get(id=group_id)
        except Group.DoesNotExist:
            return HttpResponse("Group not found", status=404)

        students = group.enrolled_students.all()

        # Guruhning course yoki course_type'iga mos mavzularni olamiz
        group_course = getattr(group, "course", None)
        if group_course:
            # Barcha active topiclarni olamiz (id bo'yicha tartibda)
            all_topics = Topic.objects.filter(is_active=True, course=group.course, course__is_active=True).order_by('id')
            # Oxirgi 10 ta topicni olamiz
            topics_list = list(all_topics)
            topics = topics_list[-10:] if len(topics_list) >= 10 else topics_list
        else:
            topics = []
            all_topics = Topic.objects.none()

        # Agar active mavzu yo'q bo'lsa, PDF yaratmaymiz
        if not topics:
            return HttpResponse("No active topics", status=404)

        # Font
        try:
            pdfmetrics.registerFont(TTFont('DejaVuSans', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
            font_name = 'DejaVuSans'
            font_name_bold = 'DejaVuSans-Bold'
        except:
            font_name = 'Helvetica'
            font_name_bold = 'Helvetica-Bold'

        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from django.utils import timezone as tz

        # Sarlavha stillari
        title_style = ParagraphStyle(
            'WeeklyTitle',
            fontName=font_name_bold,
            fontSize=14,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1A3A6E"),
            spaceAfter=4,
        )
        subtitle_style = ParagraphStyle(
            'WeeklySubtitle',
            fontName=font_name,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#444444"),
            spaceAfter=8,
        )

        course_name = group.course.name if group.course else "—"
        today = tz.localtime(tz.now()).strftime("%d.%m.%Y")
        title_para = Paragraph("HAFTALIK HISOBOT", title_style)
        subtitle_para = Paragraph(
            f"Guruh: <b>{group.name}</b>  |  Kurs: <b>{course_name}</b>  |  Sana: <b>{today}</b>",
            subtitle_style,
        )

        # Ism ustuni stili
        name_style = ParagraphStyle(
            'NameStyle',
            fontName=font_name,
            fontSize=7,
            leading=9,
            alignment=TA_LEFT,
            wordWrap='LTR',
        )

        # Header qatori
        talaba_style = ParagraphStyle(
            'TalabaHdr',
            fontName=font_name_bold,
            fontSize=8,
            alignment=TA_CENTER,
            textColor=colors.white,
        )
        header = [Paragraph("Talaba", talaba_style)]
        for t in topics:
            header.append(RotatedText(t.title, font_name, 6))
        header.append(RotatedText("Umumiy o'rtacha", font_name_bold, 6))
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
            # Bajarmagan mavzular ham 0 ball sifatida hisobga olinadi
            total_topics_count = all_topics.count()
            all_grades_sum = 0
            for topic in all_topics:
                task_type = 'test' if topic.correct_answers else 'assignment'
                task = Task.objects.filter(
                    student=student,
                    topic=topic,
                    task_type=task_type,
                    topic__course=group.course
                ).first()
                
                if task and task.grade is not None:
                    all_grades_sum += task.grade
            
            # Umumiy o'rtacha (barcha active topiclar soniga bo'linadi, bajarmagan = 0)
            if total_topics_count > 0:
                overall_avg = all_grades_sum / total_topics_count
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

        from reportlab.lib.pagesizes import A3
        
        doc = SimpleDocTemplate(response, pagesize=landscape(A3), 
                                leftMargin=15, rightMargin=15, 
                                topMargin=15, bottomMargin=15)
        
        # Sahifa o'lchamlari
        page_width = landscape(A3)[0] - 30  # minus margins
        
        # Ustun kengliklarini hisoblash
        num_topics = len(topics)

        # Ism ustuni uchun 200 point (uzun ismlar wrap bo'lib to'liq ko'rinadi)
        name_col_width = 200

        # Qolgan joy mavzular va umumiy o'rtacha uchun
        # avg ustun topic_col_width * 1.2 bo'lgani uchun (num_topics + 1.2) ga bo'lamiz
        topic_col_width = (page_width - name_col_width) / (num_topics + 1.2)

        # Har bir mavzu uchun minimal 22 point
        topic_col_width = max(topic_col_width, 22)

        col_widths = [name_col_width]  # Ism
        col_widths.extend([topic_col_width] * num_topics)  # Mavzular
        col_widths.append(topic_col_width * 1.2)  # Umumiy o'rtacha biroz kengroq
        
        table = Table(data, colWidths=col_widths, repeatRows=1)

        # Header ranglari: "Talaba" — to'q ko'k, mavzular — navbatma-navbat 2 ko'k,
        # "Umumiy o'rtacha" — yashil
        COLOR_DARK   = colors.HexColor("#1A3A6E")
        COLOR_ODD    = colors.HexColor("#2E5596")
        COLOR_EVEN   = colors.HexColor("#3A6BC4")
        COLOR_GREEN  = colors.HexColor("#1B6B3A")
        COLOR_ROW_ALT = colors.HexColor("#EEF2FA")

        hdr_cmds = [
            ("BACKGROUND", (0, 0), (0, 0), COLOR_DARK),   # Talaba ustuni
        ]
        for i in range(num_topics):
            col = i + 1
            bg = COLOR_ODD if i % 2 == 0 else COLOR_EVEN
            hdr_cmds.append(("BACKGROUND", (col, 0), (col, 0), bg))
        last_col = num_topics + 1
        hdr_cmds.append(("BACKGROUND", (last_col, 0), (last_col, 0), COLOR_GREEN))

        style = TableStyle([
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), font_name_bold),
            ("FONTNAME", (0, 1), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAAAAA")),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, colors.HexColor("#0D2347")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, COLOR_ROW_ALT]),
        ] + hdr_cmds)
        table.setStyle(style)

        doc.build([title_para, subtitle_para, table])
        return response

# vazifalar topshirmagan studentlarni tekshiradi
class UnsubmittedTasksCheckView(APIView):
    def get(self, request):
        # faqat faol kurslarning o’tilgan mavzulari
        active_topics = Topic.objects.filter(is_active=True, course__is_active=True)

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
        show_detailed_results = request.data.get("show_detailed_results", False)
        
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
            is_active=is_active,
            show_detailed_results=show_detailed_results
        )
        
        serializer = TopicSerializer(topic)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class StudentResultsView(APIView):
    """
    Studentning barcha mavzulardagi natijalarini qaytaradi
    GET /api/student/<telegram_id>/results/
    
    Javob formati:
    {
        "telegram_id": "123456",
        "full_name": "Ali Valiyev",
        "results": [
            {
                "topic_id": 1,
                "topic_title": "1-mavzu",
                "grade": 35
            },
            {
                "topic_id": 2,
                "topic_title": "2-mavzu", 
                "grade": 34
            },
            {
                "topic_id": 5,
                "topic_title": "5-mavzu",
                "grade": 0
            }
        ]
    }
    """
    
    def get(self, request, telegram_id):
        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response(
                {"error": "Student not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Studentning guruhlarini olish
        student_groups = student.groups.all()
        if not student_groups.exists():
            return Response(
                {"error": "Student has no groups"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Studentning faqat faol kurslarini olish
        student_courses = []
        for group in student_groups:
            if group.course and group.course.is_active:
                student_courses.append(group.course)

        # Agar faol kurs bo'lmasa, bo'sh javob qaytaramiz
        if not student_courses:
            response_data = {
                "telegram_id": student.telegram_id,
                "full_name": student.full_name,
                "results": []
            }
            return Response(response_data, status=status.HTTP_200_OK)

        # Faqat student tegishli faol kurslar bo'yicha mavzularni olish
        all_topics = Topic.objects.filter(
            is_active=True,
            course__in=student_courses
        ).order_by('id')
        
        results = []
        for topic in all_topics:
            # Ushbu mavzudan studentning vazifasini qidirish
            try:
                task = Task.objects.get(student=student, topic=topic)
                grade = task.grade if task.grade is not None else 0
            except Task.DoesNotExist:
                # Agar student bu mavzuda topshirmagan bo'lsa
                grade = 0
            
            results.append({
                "topic_id": topic.id,
                "topic_title": topic.title,
                "grade": grade
            })
        
        response_data = {
            "telegram_id": student.telegram_id,
            "full_name": student.full_name,
            "results": results
        }
        
        return Response(response_data, status=status.HTTP_200_OK)


class CoursesListView(APIView):
    """Barcha kurslar ro'yxati. ?all=1 — nofaol kurslar ham (admin uchun)"""
    def get(self, request):
        from .models import Course
        show_all = request.query_params.get('all')
        if show_all:
            courses = Course.objects.all().order_by('id')
        else:
            courses = Course.objects.filter(is_active=True).order_by('id')
        data = [{"id": c.id, "name": c.name} for c in courses]
        return Response(data)


class CourseTopicsView(APIView):
    """
    Kurs bo'yicha topiclar va har biridagi unique qatnashuvchilar soni
    GET /api/kurslar/<id>/topiclar/
    Response: [{code, name, count}]
    """
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from django.db.models import Count
        from .models import Course, Topic

        if not Course.objects.filter(pk=pk).exists():
            return Response({"error": "Kurs topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        topics = Topic.objects.filter(course_id=pk).order_by('-id')

        results = []
        for topic in topics:
            if not topic.correct_answers:
                continue
            for code in topic.correct_answers:
                count = (
                    Task.objects
                    .filter(task_type='test', test_code=code)
                    .values('student')
                    .distinct()
                    .count()
                )
                results.append({
                    "code": code,
                    "name": topic.title,
                    "count": count,
                })

        return Response(results)


# ─────────────────────────────────────────────
# Tashqi server uchun endpointlar
# ─────────────────────────────────────────────

class TestStatsView(APIView):
    """
    Barcha testlar ro'yxati (sahifalab, 8 ta/sahifa)
    GET /api/test-stats/?page=1

    Response:
    {
        "results": [{"code": "TEST001", "name": "...", "count": 87}],
        "current_page": 1,
        "total_pages": 4,
        "total": 30
    }
    """
    PAGE_SIZE = 8

    def get(self, request):
        from django.core.paginator import Paginator
        from django.db.models import Count

        try:
            page_num = max(1, int(request.query_params.get("page", 1)))
        except (ValueError, TypeError):
            page_num = 1

        # Har bir test_code uchun distinct studentlar soni
        test_stats = (
            Task.objects
            .filter(task_type='test')
            .exclude(test_code__isnull=True)
            .exclude(test_code='')
            .values('test_code')
            .annotate(count=Count('student', distinct=True))
            .order_by('test_code')
        )

        paginator = Paginator(test_stats, self.PAGE_SIZE)
        page = paginator.get_page(page_num)

        results = []
        for item in page.object_list:
            tc = item['test_code']
            topic = Topic.objects.filter(correct_answers__has_key=tc).first()
            name = topic.title if topic else tc
            results.append({
                "code": tc,
                "name": name,
                "count": item['count'],
            })

        return Response({
            "results": results,
            "current_page": page_num,
            "total_pages": paginator.num_pages,
            "total": paginator.count,
        })


class TestResultsJSONView(APIView):
    """
    Bitta test natijalari (fan_ball, ped_ball, umumiy_ball bilan)
    GET /api/test-results-json/<test_code>/

    Response:
    {
        "code": "TEST001",
        "name": "Matematika - Mart 2025",
        "total_questions": 50,
        "results": [
            {"first_name": "Ali", "last_name": "Valiyev",
             "fan_ball": 52, "ped_ball": 20, "umumiy_ball": 72}
        ]
    }
    """

    def _parse_correct(self, correct_str):
        """Admin to'g'ri javoblar satrini listga aylantirish"""
        import re
        correct = correct_str.lower().strip()
        result = []
        has_numbers = bool(re.search(r'\d', correct))
        if has_numbers:
            for match in re.finditer(r'\d+([a-zx]+)', correct):
                letters = match.group(1)
                result.append(['x'] if letters == 'x' else list(letters))
        elif re.match(r'^[a-zx]+$', correct):
            result = [[ch] for ch in correct]
        else:
            filtered = ''.join(ch for ch in correct if ch.isalpha() or ch == 'x')
            result = [[ch] for ch in filtered]
        return result

    def _parse_student(self, answer_str):
        """Student javoblar satrini listga aylantirish"""
        import re
        user = answer_str.lower().strip()
        has_numbers = bool(re.search(r'\d', user))
        if has_numbers:
            return [m.group(1) for m in re.finditer(r'\d+([a-zx])', user)]
        filtered = ''.join(ch for ch in user if ch.isalpha() or ch == 'x')
        return list(filtered)

    def get(self, request, test_code):
        # Bu test_code ga ega topic ni topish
        topic = Topic.objects.filter(correct_answers__has_key=test_code).first()
        if not topic:
            return Response({"error": "Test topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        correct_str = topic.correct_answers.get(test_code, "")
        correct_list = self._parse_correct(correct_str) if correct_str else []
        total_questions = len(correct_list)

        tasks = (
            Task.objects
            .filter(test_code=test_code, task_type='test')
            .select_related('student')
        )

        results = []
        for task in tasks:
            name_parts = (task.student.full_name or "").strip().split()
            first_name = name_parts[0] if name_parts else "-"
            last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else "-"

            fan_ball = 0
            ped_ball = 0

            if task.test_answers and correct_list:
                student_list = self._parse_student(task.test_answers)
                if len(student_list) == len(correct_list):
                    for i, (s_ans, c_ans) in enumerate(zip(student_list, correct_list)):
                        if s_ans in c_ans:
                            if i < 35:      # 1-35 → Fan bloki
                                fan_ball += 2
                            else:           # 36-50 → Ped bloki
                                ped_ball += 2
                else:
                    # Javoblar soni mos kelmasa — grade dan foydalanamiz
                    fan_ball = (task.grade or 0) * 2
            else:
                fan_ball = (task.grade or 0) * 2

            results.append({
                "first_name": first_name,
                "last_name": last_name,
                "fan_ball": fan_ball,
                "ped_ball": ped_ball,
                "umumiy_ball": fan_ball + ped_ball,
                "created_at": task.submitted_at,
            })

        return Response({
            "code": test_code,
            "name": topic.title,
            "total_questions": total_questions,
            "results": results,
        })


# ─────────────────────────────────────────────
# Tanga tizimi endpointlari
# ─────────────────────────────────────────────

class LeaderboardView(APIView):
    """
    Kurs bo'yicha reyting (top 600, tanga bo'yicha)
    GET /api/coins/leaderboard/?course_id=1&telegram_id=xxx

    Response:
    {
        "top10": [{rank, telegram_id, full_name, total_coins, current_streak, longest_streak}],
        "my_rank": 15,          # null if >600 or not found
        "my_coins": 123,
        "my_streak": 2,
        "my_longest_streak": 5
    }
    """

    def get(self, request):
        course_id = request.query_params.get('course_id')
        telegram_id = request.query_params.get('telegram_id')

        if not course_id:
            return Response({"error": "course_id kerak"}, status=status.HTTP_400_BAD_REQUEST)

        wallets = (
            CoinWallet.objects
            .filter(course_id=course_id)
            .select_related('student', 'course')
            .order_by('-total_coins', '-longest_streak')
        )

        ranked = []
        for rank, w in enumerate(wallets, start=1):
            if rank <= 600:
                ranked.append({
                    "rank": rank,
                    "telegram_id": w.student.telegram_id,
                    "full_name": w.student.full_name,
                    "total_coins": w.total_coins,
                    "current_streak": w.current_streak,
                    "longest_streak": w.longest_streak,
                })

        top10 = ranked[:10]

        my_rank = None
        my_coins = 0
        my_streak = 0
        my_longest = 0

        if telegram_id:
            for entry in ranked:
                if entry["telegram_id"] == telegram_id:
                    my_rank = entry["rank"]
                    my_coins = entry["total_coins"]
                    my_streak = entry["current_streak"]
                    my_longest = entry["longest_streak"]
                    break
            # Agar >600 bo'lsa, tangalarini topib qaytaramiz
            if my_rank is None:
                try:
                    student = Student.objects.get(telegram_id=telegram_id)
                    w = CoinWallet.objects.filter(student=student, course_id=course_id).first()
                    if w:
                        my_coins = w.total_coins
                        my_streak = w.current_streak
                        my_longest = w.longest_streak
                except Student.DoesNotExist:
                    pass

        return Response({
            "top10": top10,
            "my_rank": my_rank,
            "my_coins": my_coins,
            "my_streak": my_streak,
            "my_longest_streak": my_longest,
        })


class StudentWalletView(APIView):
    """
    Student barcha kurslar bo'yicha hamyonini ko'rish
    GET /api/coins/my/?telegram_id=xxx
    """

    def get(self, request):
        telegram_id = request.query_params.get('telegram_id')
        if not telegram_id:
            return Response({"error": "telegram_id kerak"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response({"error": "Student topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        wallets = CoinWallet.objects.filter(student=student).select_related('course')
        result = []
        for w in wallets:
            result.append({
                "course_id": w.course.id,
                "course_name": w.course.name,
                "total_coins": w.total_coins,
                "current_streak": w.current_streak,
                "longest_streak": w.longest_streak,
            })

        return Response({
            "full_name": student.full_name,
            "wallets": result,
        })


class AdminLeaderboardView(APIView):
    """
    Admin uchun filtrlangan reyting
    GET /api/coins/admin-leaderboard/?course_id=1&from=2026-01-01&to=2026-05-06&sort=coins|streak
    """

    def get(self, request):
        from django.db.models import Sum, Max
        from django.utils.dateparse import parse_date
        import pytz

        course_id = request.query_params.get('course_id')
        sort_by = request.query_params.get('sort', 'coins')  # coins | streak
        from_date_str = request.query_params.get('from')
        to_date_str = request.query_params.get('to')

        if not course_id:
            return Response({"error": "course_id kerak"}, status=status.HTTP_400_BAD_REQUEST)

        local_tz = pytz.timezone('Asia/Tashkent')

        # Sana filtri
        tx_filter = {'wallet__course_id': course_id}
        if from_date_str:
            fd = parse_date(from_date_str)
            if fd:
                from datetime import datetime
                tx_filter['created_at__gte'] = local_tz.localize(
                    datetime.combine(fd, datetime.min.time())
                )
        if to_date_str:
            td = parse_date(to_date_str)
            if td:
                from datetime import datetime
                tx_filter['created_at__lte'] = local_tz.localize(
                    datetime.combine(td, datetime.max.time())
                )

        # Sana oralig'idagi yig'ilgan tanga yoki streak bo'yicha saralash
        if sort_by == 'streak':
            # Eng uzun streak bo'yicha (all-time, walletdan)
            wallets = (
                CoinWallet.objects
                .filter(course_id=course_id)
                .select_related('student')
                .order_by('-longest_streak', '-total_coins')
            )
            results = []
            for rank, w in enumerate(wallets[:50], start=1):
                results.append({
                    "rank": rank,
                    "telegram_id": w.student.telegram_id,
                    "full_name": w.student.full_name,
                    "total_coins": w.total_coins,
                    "longest_streak": w.longest_streak,
                    "current_streak": w.current_streak,
                })
        else:
            # Tanlangan davr ichida eng ko'p tanga
            from django.db.models import Sum
            tx_agg = (
                CoinTransaction.objects
                .filter(**tx_filter)
                .values('wallet__student__telegram_id', 'wallet__student__full_name', 'wallet__id')
                .annotate(period_coins=Sum('total_coins'), max_streak=Max('streak_after'))
                .order_by('-period_coins')
            )
            results = []
            for rank, row in enumerate(tx_agg[:50], start=1):
                results.append({
                    "rank": rank,
                    "telegram_id": row['wallet__student__telegram_id'],
                    "full_name": row['wallet__student__full_name'],
                    "period_coins": row['period_coins'],
                    "max_streak_in_period": row['max_streak'],
                })

        return Response({"results": results, "sort_by": sort_by})


# ─── Davomat ───────────────────────────────────────────────────────────────────

class AttendanceSessionCreateView(APIView):
    """
    Admin davomat sessiyasi ochadi
    POST /api/attendance/session/
    Body: { "code": "3847", "expires_at": "2026-05-16T15:00:00", "created_by": "1811507184" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        code = request.data.get("code", "").strip()
        expires_at = request.data.get("expires_at")
        created_by = request.data.get("created_by", "")

        if not code or not expires_at:
            return Response({"error": "code va expires_at majburiy"}, status=status.HTTP_400_BAD_REQUEST)

        # Oldingi aktiv sessiyalarni o'chirish (faqat shu adminniki)
        AttendanceSession.objects.filter(created_by=created_by, is_active=True).update(is_active=False)

        session = AttendanceSession.objects.create(
            code=code,
            expires_at=expires_at,
            created_by=created_by,
            is_active=True,
        )
        return Response({"id": session.id, "code": session.code, "expires_at": session.expires_at}, status=status.HTTP_201_CREATED)


class AttendanceMarkView(APIView):
    """
    Talaba davomat qo'yadi
    POST /api/attendance/mark/
    Body: { "telegram_id": "123456789", "code": "3847" }
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from django.utils import timezone

        telegram_id = str(request.data.get("telegram_id", "")).strip()
        code = str(request.data.get("code", "")).strip()

        if not telegram_id or not code:
            return Response({"error": "telegram_id va code majburiy"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(telegram_id=telegram_id)
        except Student.DoesNotExist:
            return Response({"error": "Talaba topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # Aktiv va muddati o'tmagan sessiyani topish
        session = AttendanceSession.objects.filter(
            code=code,
            is_active=True,
            expires_at__gt=timezone.now(),
        ).first()

        if not session:
            return Response({"error": "Kod noto'g'ri yoki muddati tugagan"}, status=status.HTTP_400_BAD_REQUEST)

        # Takroriy tasdiq tekshiruvi
        if Attendance.objects.filter(student=student, session=session).exists():
            return Response({"error": "already_marked"}, status=status.HTTP_409_CONFLICT)

        Attendance.objects.create(student=student, session=session)
        return Response({"ok": True, "session_date": session.created_at.strftime("%d.%m.%Y")}, status=status.HTTP_201_CREATED)


class AttendanceCSVView(APIView):
    """
    Haftalik davomat CSV hisobot
    GET /api/attendance/csv/?from=2026-05-10&to=2026-05-16
    """
    permission_classes = [AllowAny]

    def get(self, request):
        import csv
        from django.utils import timezone
        from datetime import datetime
        import io

        from_str = request.query_params.get("from")
        to_str = request.query_params.get("to")

        try:
            import pytz
            tz = pytz.timezone("Asia/Tashkent")
            from_dt = tz.localize(datetime.strptime(from_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0))
            to_dt = tz.localize(datetime.strptime(to_str, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
        except Exception:
            return Response({"error": "from va to parametrlari kerak (YYYY-MM-DD)"}, status=status.HTTP_400_BAD_REQUEST)

        sessions = list(
            AttendanceSession.objects.filter(
                created_at__gte=from_dt,
                created_at__lte=to_dt,
            ).order_by("created_at")
        )

        # Barcha davomatlarni bir so'rovda olish
        attendances = Attendance.objects.filter(
            session__in=sessions
        ).select_related("student").values("student_id", "session_id")

        # (student_id, session_id) set
        marked_set = {(a["student_id"], a["session_id"]) for a in attendances}

        # Guruhi bor barcha studentlar (kelgan-kelmaganidan qatʼi nazar)
        students = list(Student.objects.filter(groups__isnull=False).distinct().order_by("full_name"))

        output = io.StringIO()
        # UTF-8 BOM — Excel uchun
        output.write("﻿")
        writer = csv.writer(output)

        # Sarlavha
        session_labels = [s.created_at.astimezone(tz).strftime("%d.%m") for s in sessions]
        writer.writerow(["Ism Familya", "Telefon"] + session_labels + ["Jami"])

        for student in students:
            row = [student.full_name, student.phone or "—"]
            count = 0
            for s in sessions:
                if (student.id, s.id) in marked_set:
                    row.append("✅")
                    count += 1
                else:
                    row.append("❌")
            row.append(f"{count}/{len(sessions)}")
            writer.writerow(row)

        csv_bytes = output.getvalue().encode("utf-8")
        response = HttpResponse(csv_bytes, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="davomat_{from_str}_{to_str}.csv"'
        return response
