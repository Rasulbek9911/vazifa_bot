from django.urls import path
from .views import (
     StudentRegisterView, StudentChangeGroupView, TaskSubmitView,
     StudentIsRegisteredView, GroupsListView, TopicsListView, TopicDetailView,
     TaskListView, TaskUpdateView, WeeklyReportPDFView, StudentListView,
     CreateInviteCodeView, ValidateInviteCodeView, StudentUpdateNameView, TopicCreateView,
     StudentResultsView, CoursesListView, CourseTopicsView,
     TestStatsView, TestResultsJSONView,
     LeaderboardView, StudentWalletView, AdminLeaderboardView,
     AttendanceSessionCreateView, AttendanceMarkView, AttendanceCSVView,
)
from .followup_views import followup_list, followup_mark, followup_unmark, followup_tg_link, followup_lock, followup_block, followup_unblock
from .payment_views import payment_list, payment_detail, payment_set_plan, payment_add, payment_delete

urlpatterns = [
     # Student-related URLs
     path("students/register/", StudentRegisterView.as_view(), name="student-register"),
     path("students/<int:pk>/", StudentIsRegisteredView.as_view(), name="student-detail"),
     path("students/<int:pk>/change-group/", StudentChangeGroupView.as_view(), name="student-change-group"),
     path("students/<str:telegram_id>/update_name/", StudentUpdateNameView.as_view(), name="student-update-name"),
     path("students/<str:telegram_id>/results/", StudentResultsView.as_view(), name="student-results"),
     path("students/", StudentListView.as_view(), name="student-list"),

     # Group and topic-related URLs
     path("courses/", CoursesListView.as_view(), name="courses-list"),
     path("groups/", GroupsListView.as_view(), name="groups-list"),
     path("topics/", TopicsListView.as_view(), name="topics-list"),
     path("topics/create/", TopicCreateView.as_view(), name="topic-create"),
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

     # Tashqi server uchun (AllowAny, auth shart emas)
     path("test-stats/", TestStatsView.as_view(), name="test-stats"),
     path("test-results-json/<str:test_code>/", TestResultsJSONView.as_view(), name="test-results-json"),
     path("kurslar/<int:pk>/topiclar/", CourseTopicsView.as_view(), name="course-topics"),

     # Tanga tizimi
     path("coins/leaderboard/", LeaderboardView.as_view(), name="coin-leaderboard"),
     path("coins/my/", StudentWalletView.as_view(), name="coin-my-wallet"),
     path("coins/admin-leaderboard/", AdminLeaderboardView.as_view(), name="coin-admin-leaderboard"),

     # Davomat
     path("attendance/session/", AttendanceSessionCreateView.as_view(), name="attendance-session-create"),
     path("attendance/mark/", AttendanceMarkView.as_view(), name="attendance-mark"),
     path("attendance/csv/", AttendanceCSVView.as_view(), name="attendance-csv"),
]

payment_urlpatterns = [
    path("", payment_list, name="payment-list"),
    path("<int:student_id>/", payment_detail, name="payment-detail"),
    path("<int:student_id>/set-plan/", payment_set_plan, name="payment-set-plan"),
    path("add/<int:plan_id>/", payment_add, name="payment-add"),
    path("delete/<int:payment_id>/", payment_delete, name="payment-delete"),
]

followup_urlpatterns = [
     path("", followup_list, name="followup-list"),
     path("mark/<int:student_id>/", followup_mark, name="followup-mark"),
     path("unmark/<int:student_id>/", followup_unmark, name="followup-unmark"),
     path("lock/<int:student_id>/", followup_lock, name="followup-lock"),
     path("tg-link/<int:student_id>/", followup_tg_link, name="followup-tg-link"),
     path("block/<int:student_id>/", followup_block, name="followup-block"),
     path("unblock/<int:student_id>/", followup_unblock, name="followup-unblock"),
]
