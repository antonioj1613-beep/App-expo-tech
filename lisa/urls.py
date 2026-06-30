from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("staff/", include("app.staff_urls")),
    path("", include("app.urls")),
]
