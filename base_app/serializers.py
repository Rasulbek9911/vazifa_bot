from rest_framework import serializers
from .models import Group, Student, Topic, Task, InviteCode


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name", "telegram_group_id", "invite_link", "course_type", "is_full"]


class StudentSerializer(serializers.ModelSerializer):
    group = GroupSerializer(read_only=True)
    group_id = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source="group",
        write_only=False,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Student
        fields = ["id", "telegram_id", "full_name", "group", "group_id"]


class TopicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Topic
        fields = ["id", "title", "is_active", "course_type", "correct_answers", "deadline", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    student_id = serializers.PrimaryKeyRelatedField(
        queryset=Student.objects.all(), source="student", write_only=True
    )
    topic = TopicSerializer(read_only=True)
    topic_id = serializers.PrimaryKeyRelatedField(
        queryset=Topic.objects.all(), source="topic", write_only=True
    )

    class Meta:
        model = Task
        fields = [
            "id",
            "student", "student_id",
            "topic", "topic_id",
            "task_type",
            "course_type",
            "file_link", 
            "test_code", "test_answers",
            "grade", "submitted_at"
        ]


class InviteCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InviteCode
        fields = ["id", "code", "created_by", "is_used", "used_by", "created_at", "used_at"]
