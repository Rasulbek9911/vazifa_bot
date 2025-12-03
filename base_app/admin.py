from django.contrib import admin
from django.contrib import messages
from django.template.response import TemplateResponse
from django import forms
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
    actions = ['add_points_to_topic_tests', 'subtract_points_from_topic_tests']
    
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

admin.site.register(Group)
admin.site.register(Student, StudentAdmin)
admin.site.register(Topic, TopicAdmin)
admin.site.register(Task, TaskAdmin)