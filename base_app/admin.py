from django.contrib import admin
from .models import Group, Student, Topic, Task


class StudentAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'telegram_id', 'group')
    search_fields = ('full_name', 'telegram_id')
    list_filter = ('group',)


admin.site.register(Group)
admin.site.register(Student, StudentAdmin)
admin.site.register(Topic)
admin.site.register(Task)