from django.contrib import admin
from .models import Group, Student, Topic, Task

admin.site.register(Group)
admin.site.register(Student)
admin.site.register(Topic)
admin.site.register(Task)