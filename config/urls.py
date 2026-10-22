from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView  # 명세 데이터 뷰, Swagger 화면 뷰

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("posts.urls")),       # "/" -> posts 앱으로 위임
    path("", include("accounts.urls")),    # "/mypage/", "/login/" -> accounts 앱으로 위임
    path("analysis/", include("analysis.urls")),  # "/analysis/" -> analysis 앱으로 위임
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),  # API 명세 데이터(YAML)를 내려주는 주소 (화면을 그리는 재료)
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),  # Swagger 화면. url_name="schema"는 위 주소에서 명세를 가져오라는 뜻
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
