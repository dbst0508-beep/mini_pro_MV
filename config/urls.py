from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("posts.urls")),       # "/" -> posts 앱으로 위임
    path("", include("accounts.urls")),    # "/mypage/", "/login/" -> accounts 앱으로 위임
    path("analysis/", include("analysis.urls")),  # "/analysis/" -> analysis 앱으로 위임
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
