from django.urls import path
from django.views.generic import RedirectView

from . import views
from . import exam_views
from . import reading_views
from . import listening_views
from . import speaking_views
from . import vocabulary_views
from . import writing_views

urlpatterns = [
    path(
        "favicon.ico",
        RedirectView.as_view(url="/static/app/logo.svg", permanent=True),
        name="favicon",
    ),
    path("", views.landing, name="landing"),
    path("login/", views.login_view, name="login"),
    path("register/", views.register_view, name="register"),
    path("logout/", views.logout_view, name="logout"),
    path("dev/database/", views.database_browser, name="database_browser"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("levels/", views.levels, name="levels"),
    path("listening/", listening_views.listening, name="listening"),
    path("listening/api/submit/", listening_views.listening_submit, name="listening_submit"),
    path("reading/", reading_views.reading, name="reading"),
    path("reading/api/submit/", reading_views.reading_submit, name="reading_submit"),
    path("writing/", writing_views.writing, name="writing"),
    path("writing/api/submit/", writing_views.writing_submit, name="writing_submit"),
    path("vocabulary/", vocabulary_views.vocabulary, name="vocabulary"),
    path("vocabulary/api/submit/", vocabulary_views.vocabulary_submit, name="vocabulary_submit"),
    path("speaking/", speaking_views.speaking, name="speaking"),
    path("speaking/api/start/", speaking_views.speaking_start, name="speaking_start"),
    path("speaking/api/chat/", speaking_views.speaking_chat, name="speaking_chat"),
    path("speaking/api/transcribe/", speaking_views.speaking_transcribe, name="speaking_transcribe"),
    path("speaking/api/end/", speaking_views.speaking_end, name="speaking_end"),
    path("exams/", exam_views.exams, name="exams"),
    path("exams/<slug:slug>/", exam_views.exam_take, name="exam_take"),
    path("exams/api/<int:attempt_id>/submit/", exam_views.exam_submit, name="exam_submit"),
    path("exams/results/<int:attempt_id>/", exam_views.exam_results, name="exam_results"),
    path("progress/", views.progress, name="progress"),
    path("statistics/", views.statistics, name="statistics"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("profile/", views.profile, name="profile"),
    path("notifications/", views.notifications, name="notifications"),
    path("settings/", views.settings_view, name="settings"),
    path("premium/", views.premium, name="premium"),
]
