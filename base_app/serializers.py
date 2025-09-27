from rest_framework import serializers
from .models import Group, Student, Topic, Task


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "name", "telegram_group_id"]


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
        fields = ["id", "title", "created_at"]


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
            "file_link", "grade", "submitted_at"
        ]
