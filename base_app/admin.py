from django.contrib import admin
from django.contrib import messages
from django.template.response import TemplateResponse
from django import forms
from django.db.models import Avg, Count, Q
from django.http import HttpResponse
import csv
from .models import Group, Student, Topic, Task


class AddPointsForm(forms.Form):
    points = forms.IntegerField(
        label='Qo\'shmoqchi bo\'lgan ball',
        min_value=1,
        max_value=35,
        initial=5,
        help_text='1 dan 35 gacha ball qo\'shishingiz mumkin'
    )


class SubtractPointsForm(forms.Form):
    points = forms.IntegerField(
        label='Ayirmoqchi bo\'lgan ball',
        min_value=1,
        max_value=35,
        initial=5,
        help_text='1 dan 35 gacha ball ayirishingiz mumkin'
    )


class GroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'course_type', 'is_full', 'telegram_group_id')
    list_filter = ('course_type', 'is_full')
    search_fields = ('name',)
    actions = ['export_group_rating_csv']
    
    def export_group_rating_csv(self, request, queryset):
        """
        Tanlangan guruh(lar)dagi studentlarning reytingini CSV faylga eksport qiladi.
        O'rtacha ball bo'yicha kamayish tartibida.
        """
        if not queryset.exists():
            self.message_user(request, "Hech qanday guruh tanlanmadi!", messages.ERROR)
            return
        
        # Barcha tanlangan guruhlardagi studentlar
        all_students_data = []
        
        for group in queryset:
            students = Student.objects.filter(group=group)
            
            for student in students:
                # Student barcha testlari
                tasks = Task.objects.filter(
                    student=student,
                    task_type='test',
                    grade__isnull=False
                )
                
                if not tasks.exists():
                    continue
                
                # O'rtacha ball
                avg_grade = tasks.aggregate(avg=Avg('grade'))['avg']
                total_tasks = tasks.count()
                total_score = sum(task.grade for task in tasks)
                
                all_students_data.append({
                    'student': student,
                    'group': group,
                    'avg_grade': round(avg_grade, 2) if avg_grade else 0,
                    'total_tasks': total_tasks,
                    'total_score': total_score,
                })
        
        # O'rtacha ball bo'yicha kamayish tartibida
        all_students_data.sort(key=lambda x: x['avg_grade'], reverse=True)
        
        # CSV yaratish
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        group_names = '_'.join([g.name.replace(' ', '_') for g in queryset[:3]])
        filename = f'reyting_{group_names}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # UTF-8 BOM
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow([
            '№',
            'F.I.Sh',
            'Guruh',
            "O'rtacha ball",
            'Testlar soni',
            'Jami ball'
        ])
        
        # Ma'lumotlar
        for idx, data in enumerate(all_students_data, start=1):
            student = data['student']
            writer.writerow([
                idx,
                student.full_name,
                data['group'].name,
                data['avg_grade'],
                data['total_tasks'],
                data['total_score'],
            ])
        
        self.message_user(
            request,
            f"✅ {len(all_students_data)} ta studentning reytingi eksport qilindi!",
            messages.SUCCESS
        )
        
        return response
    
    export_group_rating_csv.short_description = "Tanlangan guruhlar bo'yicha reyting (CSV)"


class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'telegram_id', 'group')
    search_fields = ('full_name', 'telegram_id')
    list_filter = ('group',)


class TaskAdmin(admin.ModelAdmin):
    list_display = ('student', 'topic', 'task_type', 'course_type', 'grade', 'submitted_at')
    search_fields = ('student__full_name', 'student__telegram_id', 'topic__title')
    list_filter = ('topic__title', 'course_type', 'task_type')
    actions = ['add_custom_points_to_tests', 'subtract_custom_points_from_tests']
    
    def add_custom_points_to_tests(self, request, queryset):
        """
        Tanlangan test natijalariga o'zingiz kiritgan ball qo'shadi.
        Faqat test turida va grade mavjud bo'lgan tasklarga amal qiladi.
        """
        if 'apply' in request.POST:
            form = AddPointsForm(request.POST)
            
            if form.is_valid():
                points = form.cleaned_data['points']
                updated_count = 0
                skipped_count = 0
                
                for task in queryset:
                    # Faqat test turida va grade mavjud bo'lgan tasklar
                    if task.task_type != 'test' or task.grade is None:
                        skipped_count += 1
                        continue
                    
                    # Mavzudan maksimal ballni olish
                    topic = task.topic
                    max_grade = 35  # Default maksimal ball
                    
                    if topic.correct_answers:
                        # correct_answers ichidagi birinchi test kodini topish
                        for test_code, answers in topic.correct_answers.items():
                            if isinstance(answers, str) and len(answers) > 0:
                                max_grade = min(len(answers), 35)  # 35 dan oshmasin
                                break
                    
                    # Yangi ball = hozirgi ball + points, lekin max_grade dan oshmasin
                    new_grade = min(task.grade + points, max_grade)
                    
                    if new_grade != task.grade:
                        task.grade = new_grade
                        task.save()
                        updated_count += 1
                    else:
                        skipped_count += 1
                
                self.message_user(
                    request,
                    f"{updated_count} ta test natijasi yangilandi (+{points} ball). "
                    f"{skipped_count} ta task o'tkazildi (test emas yoki maksimal ballda).",
                    messages.SUCCESS
                )
                return None
        
        form = AddPointsForm()
        
        context = {
            'title': 'Testlarga ball qo\'shish',
            'queryset': queryset,
            'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        
        return TemplateResponse(
            request,
            'admin/add_points_confirmation.html',
            context
        )
    
    add_custom_points_to_tests.short_description = "Tanlangan testlarga ball qo'shish"
    
    def subtract_custom_points_from_tests(self, request, queryset):
        """
        Tanlangan test natijalaridan o'zingiz kiritgan ball ayiradi.
        Faqat test turida va grade mavjud bo'lgan tasklarga amal qiladi.
        """
        if 'apply' in request.POST:
            form = SubtractPointsForm(request.POST)
            
            if form.is_valid():
                points = form.cleaned_data['points']
                updated_count = 0
                skipped_count = 0
                
                for task in queryset:
                    # Faqat test turida va grade mavjud bo'lgan tasklar
                    if task.task_type != 'test' or task.grade is None:
                        skipped_count += 1
                        continue
                    
                    # Yangi ball = hozirgi ball - points, lekin 0 dan kam bo'lmasin
                    new_grade = max(task.grade - points, 0)
                    
                    if new_grade != task.grade:
                        task.grade = new_grade
                        task.save()
                        updated_count += 1
                    else:
                        skipped_count += 1
                
                self.message_user(
                    request,
                    f"{updated_count} ta test natijasi yangilandi (-{points} ball). "
                    f"{skipped_count} ta task o'tkazildi (test emas yoki 0 da).",
                    messages.SUCCESS
                )
                return None
        
        form = SubtractPointsForm()
        
        context = {
            'title': 'Testlardan ball ayirish',
            'queryset': queryset,
            'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        
        return TemplateResponse(
            request,
            'admin/subtract_points_confirmation.html',
            context
        )
    
    subtract_custom_points_from_tests.short_description = "Tanlangan testlardan ball ayirish"


class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'course_type', 'is_active', 'created_at')
    list_filter = ('course_type', 'is_active')
    search_fields = ('title',)
    actions = ['add_points_to_topic_tests', 'subtract_points_from_topic_tests', 'export_rating_csv', 'export_detailed_rating_csv']
    
    def export_detailed_rating_csv(self, request, queryset):
        """
        Tanlangan topiklar bo'yicha har bir topic uchun alohida natijalar va umumiy o'rtacha ball.
        O'rtacha ball bo'yicha kamayish tartibida.
        """
        if not queryset.exists():
            self.message_user(request, "Hech qanday topik tanlanmadi!", messages.ERROR)
            return
        
        first_topic = queryset.first()
        course_type = first_topic.course_type
        
        # Barcha tanlangan topiklar bir xil course_type da ekanini tekshirish
        if not all(topic.course_type == course_type for topic in queryset):
            self.message_user(
                request, 
                "Iltimos, faqat bir xil kurs turidan (Milliy yoki Attestatsiya) topiklar tanlang!",
                messages.ERROR
            )
            return
        
        # Tanlangan topiklarning ID lari va tartibi
        topic_ids = [topic.id for topic in queryset]
        topics_dict = {topic.id: topic for topic in queryset}
        
        # Studentlarni olish
        students_data = {}
        students = Student.objects.filter(
            tasks__topic_id__in=topic_ids,
            tasks__task_type='test',
            tasks__course_type=course_type
        ).distinct()
        
        for student in students:
            student_info = {
                'student': student,
                'topics': {},
                'total_score': 0,
                'total_tasks': 0,
            }
            
            # Har bir topic bo'yicha natijalarni yig'ish
            for topic_id in topic_ids:
                task = Task.objects.filter(
                    student=student,
                    topic_id=topic_id,
                    task_type='test',
                    course_type=course_type,
                    grade__isnull=False
                ).first()
                
                if task:
                    student_info['topics'][topic_id] = task.grade
                    student_info['total_score'] += task.grade
                    student_info['total_tasks'] += 1
                else:
                    student_info['topics'][topic_id] = None
            
            # O'rtacha ball - barcha active mavzular soniga bo'lish
            total_topics_count = len(topic_ids)  # Barcha active mavzular soni
            if total_topics_count > 0:
                student_info['avg_grade'] = round(student_info['total_score'] / total_topics_count, 2)
            else:
                student_info['avg_grade'] = 0
            
            students_data[student.id] = student_info
        
        # O'rtacha ball bo'yicha kamayish tartibida saralash
        sorted_students = sorted(
            students_data.values(),
            key=lambda x: x['avg_grade'],
            reverse=True
        )
        
        # CSV yaratish
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        course_name = "Milliy_Sertifikat" if course_type == "milliy_sert" else "Attestatsiya"
        filename = f'reyting_detallari_{course_name}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # UTF-8 BOM
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Header - har bir topic uchun alohida ustun
        header = ['№', 'F.I.Sh', 'Guruh']
        for topic_id in topic_ids:
            topic = topics_dict[topic_id]
            header.append(topic.title)
        header.extend(["O'rtacha ball", 'Topshirgan testlar'])
        
        writer.writerow(header)
        
        # Ma'lumotlar
        for idx, data in enumerate(sorted_students, start=1):
            student = data['student']
            row = [
                idx,
                student.full_name,
                student.group.name if student.group else "Yo'q",
            ]
            
            # Har bir topic bo'yicha ball
            for topic_id in topic_ids:
                grade = data['topics'].get(topic_id)
                row.append(grade if grade is not None else '-')
            
            # O'rtacha va jami
            row.append(data['avg_grade'])
            row.append(data['total_tasks'])
            
            writer.writerow(row)
        
        self.message_user(
            request,
            f"✅ {len(sorted_students)} ta studentning batafsil reytingi eksport qilindi!",
            messages.SUCCESS
        )
        
        return response
    
    export_detailed_rating_csv.short_description = "Tanlangan topiklar bo'yicha batafsil reyting (har bir topic alohida)"
    
    def export_rating_csv(self, request, queryset):
        """
        Tanlangan topiklar bo'yicha studentlarning reytingini CSV faylga eksport qiladi.
        O'rtacha ball bo'yicha kamayish tartibida.
        """
        # Course type ni aniqlash (birinchi topikdan)
        if not queryset.exists():
            self.message_user(request, "Hech qanday topik tanlanmadi!", messages.ERROR)
            return
        
        first_topic = queryset.first()
        course_type = first_topic.course_type
        
        # Barcha tanlangan topiklar bir xil course_type da ekanini tekshirish
        if not all(topic.course_type == course_type for topic in queryset):
            self.message_user(
                request, 
                "Iltimos, faqat bir xil kurs turidan (Milliy yoki Attestatsiya) topiklar tanlang!",
                messages.ERROR
            )
            return
        
        # Tanlangan topiklarning ID lari
        topic_ids = list(queryset.values_list('id', flat=True))
        
        # Studentlarni va ularning o'rtacha ballini hisoblash
        students_data = []
        students = Student.objects.filter(
            tasks__topic_id__in=topic_ids,
            tasks__task_type='test',
            tasks__course_type=course_type
        ).distinct()
        
        for student in students:
            # Shu studentning tanlangan topiklar bo'yicha tasklar
            tasks = Task.objects.filter(
                student=student,
                topic_id__in=topic_ids,
                task_type='test',
                course_type=course_type,
                grade__isnull=False
            )
            
            if not tasks.exists():
                continue
            
            # O'rtacha ball va jami tasklar soni
            avg_grade = tasks.aggregate(avg=Avg('grade'))['avg']
            total_tasks = tasks.count()
            total_score = sum(task.grade for task in tasks)
            
            students_data.append({
                'student': student,
                'avg_grade': round(avg_grade, 2) if avg_grade else 0,
                'total_tasks': total_tasks,
                'total_score': total_score,
            })
        
        # O'rtacha ball bo'yicha kamayish tartibida saralash
        students_data.sort(key=lambda x: x['avg_grade'], reverse=True)
        
        # CSV yaratish
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        course_name = "Milliy_Sertifikat" if course_type == "milliy_sert" else "Attestatsiya"
        filename = f'reyting_{course_name}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        
        # UTF-8 BOM qo'shish (Excel uchun)
        response.write('\ufeff')
        
        writer = csv.writer(response)
        
        # Header
        writer.writerow([
            '№',
            'F.I.Sh',
            'Guruh',
            "O'rtacha ball",
            'Testlar soni',
            'Jami ball'
        ])
        
        # Ma'lumotlar
        for idx, data in enumerate(students_data, start=1):
            student = data['student']
            writer.writerow([
                idx,
                student.full_name,
                student.group.name if student.group else 'Yo\'q',
                data['avg_grade'],
                data['total_tasks'],
                data['total_score'],
            ])
        
        self.message_user(
            request,
            f"✅ {len(students_data)} ta studentning reytingi eksport qilindi!",
            messages.SUCCESS
        )
        
        return response
    
    export_rating_csv.short_description = "Tanlangan topiklar bo'yicha reyting (CSV)"
    
    def add_points_to_topic_tests(self, request, queryset):
        """
        Tanlangan topic(lar)dagi barcha test natijalariga ball qo'shadi.
        """
        if 'apply' in request.POST:
            form = AddPointsForm(request.POST)
            
            if form.is_valid():
                points = form.cleaned_data['points']
                updated_count = 0
                skipped_count = 0
                
                # Barcha tanlangan topiklarni ko'rib chiqish
                for topic in queryset:
                    # Shu topikdagi barcha test tasklar
                    tasks = Task.objects.filter(topic=topic, task_type='test')
                    
                    # Maksimal ballni olish
                    max_grade = 35  # Default
                    if topic.correct_answers:
                        for test_code, answers in topic.correct_answers.items():
                            if isinstance(answers, str) and len(answers) > 0:
                                max_grade = min(len(answers), 35)  # 35 dan oshmasin
                                break
                    
                    for task in tasks:
                        # Faqat grade mavjud bo'lgan (yuborilgan) tasklar
                        if task.grade is None:
                            skipped_count += 1
                            continue
                        
                        # Yangi ball = hozirgi ball + points, lekin max_grade dan oshmasin
                        new_grade = min(task.grade + points, max_grade)
                        
                        if new_grade != task.grade:
                            task.grade = new_grade
                            task.save()
                            updated_count += 1
                        else:
                            skipped_count += 1
                
                self.message_user(
                    request,
                    f"{updated_count} ta test natijasi yangilandi (+{points} ball). "
                    f"{skipped_count} ta task o'tkazildi (yuborilmagan yoki maksimal ballda).",
                    messages.SUCCESS
                )
                return None
        
        form = AddPointsForm()
        
        # Tanlangan topiklarning nomlarini olish
        topic_names = ', '.join([topic.title for topic in queryset])
        
        context = {
            'title': f'Topik testlariga ball qo\'shish',
            'description': f'Siz {queryset.count()} ta topikni tanladingiz: {topic_names}',
            'queryset': queryset,
            'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        
        return TemplateResponse(
            request,
            'admin/add_points_to_topic_confirmation.html',
            context
        )
    
    add_points_to_topic_tests.short_description = "Bu topiklarning barcha testlariga ball qo'shish"
    
    def subtract_points_from_topic_tests(self, request, queryset):
        """
        Tanlangan topic(lar)dagi barcha test natijalaridan ball ayiradi.
        """
        if 'apply' in request.POST:
            form = SubtractPointsForm(request.POST)
            
            if form.is_valid():
                points = form.cleaned_data['points']
                updated_count = 0
                skipped_count = 0
                
                # Barcha tanlangan topiklarni ko'rib chiqish
                for topic in queryset:
                    # Shu topikdagi barcha test tasklar
                    tasks = Task.objects.filter(topic=topic, task_type='test')
                    
                    for task in tasks:
                        # Faqat grade mavjud bo'lgan (yuborilgan) tasklar
                        if task.grade is None:
                            skipped_count += 1
                            continue
                        
                        # Yangi ball = hozirgi ball - points, lekin 0 dan kam bo'lmasin
                        new_grade = max(task.grade - points, 0)
                        
                        if new_grade != task.grade:
                            task.grade = new_grade
                            task.save()
                            updated_count += 1
                        else:
                            skipped_count += 1
                
                self.message_user(
                    request,
                    f"{updated_count} ta test natijasi yangilandi (-{points} ball). "
                    f"{skipped_count} ta task o'tkazildi (yuborilmagan yoki 0 da).",
                    messages.SUCCESS
                )
                return None
        
        form = SubtractPointsForm()
        
        # Tanlangan topiklarning nomlarini olish
        topic_names = ', '.join([topic.title for topic in queryset])
        
        context = {
            'title': f'Topik testlaridan ball ayirish',
            'description': f'Siz {queryset.count()} ta topikni tanladingiz: {topic_names}',
            'queryset': queryset,
            'form': form,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        }
        
        return TemplateResponse(
            request,
            'admin/subtract_points_from_topic_confirmation.html',
            context
        )
    
    subtract_points_from_topic_tests.short_description = "Bu topiklarning barcha testlaridan ball ayirish"

admin.site.register(Group, GroupAdmin)
admin.site.register(Student, StudentAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(Task, TaskAdmin)