from django.urls import path
from .views import (
     StudentRegisterView, StudentChangeGroupView, TaskSubmitView,
     StudentIsRegisteredView, GroupsListView, TopicsListView, TopicDetailView,
     TaskListView, TaskUpdateView, WeeklyReportPDFView, StudentListView,
     CreateInviteCodeView, ValidateInviteCodeView
)

urlpatterns = [
     # Student-related URLs
     path("students/register/", StudentRegisterView.as_view(), name="student-register"),
     path("students/<int:pk>/", StudentIsRegisteredView.as_view(), name="student-detail"),
     path("students/<int:pk>/change-group/", StudentChangeGroupView.as_view(), name="student-change-group"),
     path("students/", StudentListView.as_view(), name="student-list"),

     # Group and topic-related URLs
     path("groups/", GroupsListView.as_view(), name="groups-list"),
     path("topics/", TopicsListView.as_view(), name="topics-list"),
     path("topics/<int:pk>/", TopicDetailView.as_view(), name="topic-detail"),
     

     # Task-related URLs
     path("tasks/submit/", TaskSubmitView.as_view(), name="task-submit"),
     path("tasks/", TaskListView.as_view(), name="task-list"),
     path("tasks/<int:pk>/", TaskUpdateView.as_view(), name="task-update"),

     # Report-related URLs
     path("reports/<int:group_id>/weekly/pdf/", WeeklyReportPDFView.as_view(), name="weekly_report_pdf"),
     
     # Invite Code URLs
     path("invites/create/", CreateInviteCodeView.as_view(), name="invite-create"),
     path("invites/validate/", ValidateInviteCodeView.as_view(), name="invite-validate"),
]
