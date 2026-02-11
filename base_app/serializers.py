from rest_framework import serializers
from .models import Course, Group, Student, Topic, Task, InviteCode


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ["id", "name", "code", "task_type", "admin_telegram_id", "is_active", "created_at"]


class GroupSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source="course",
        write_only=True,
        required=False,
        allow_null=True
    )
    
    # Backward compatibility
    course_type = serializers.SerializerMethodField()
    
    def get_course_type(self, obj):
        """Backward compatibility: course.code qaytarish"""
        return obj.course.code if obj.course else obj.course_type
    
    class Meta:
        model = Group
        fields = ["id", "name", "telegram_group_id", "invite_link", "course", "course_id", "course_type", "is_full"]


class StudentSerializer(serializers.ModelSerializer):
    # Ko'p guruh (ManyToMany)
    groups = GroupSerializer(many=True, read_only=True)
    groups_ids = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        source="groups",
        many=True,
        write_only=True,
        required=False,
    )
    
    # Helper: Barcha guruhlarni qaytarish
    all_groups = serializers.SerializerMethodField()
    
    def get_all_groups(self, obj):
        """Barcha guruhlarni qaytarish"""
        return GroupSerializer(obj.groups.all(), many=True).data
    
    def create(self, validated_data):
        """Student yaratish"""
        groups_data = validated_data.pop('groups', [])
        student = Student.objects.create(**validated_data)
        
        # groups_ids orqali guruhlar qo'shish
        for group in groups_data:
            student.groups.add(group)
        
        return student

    class Meta:
        model = Student
        fields = ["id", "telegram_id", "full_name", "groups", "groups_ids", "all_groups"]


class TopicSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    course_id = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(),
        source="course",
        write_only=True,
        required=False,
        allow_null=True
    )
    
    # Backward compatibility
    course_type = serializers.SerializerMethodField()
    
    def get_course_type(self, obj):
        """Backward compatibility: course.code qaytarish"""
        return obj.course.code if obj.course else obj.course_type
    
    class Meta:
        model = Topic
        fields = ["id", "title", "is_active", "course", "course_id", "course_type", "correct_answers", "deadline", "show_detailed_results", "created_at"]


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
            "file_link", 
            "test_code", "test_answers",
            "grade", "submitted_at"
        ]


class InviteCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = InviteCode
        fields = ["id", "code", "created_by", "is_used", "used_by", "created_at", "used_at"]
