from django.urls import path

from . import views

app_name = "analysis"

urlpatterns = [
    path("", views.home, name="home"),
    path("api/<int:analysis_id>/callback/", views.analysis_callback, name="callback"),
    path("api/<int:analysis_id>/status/", views.analysis_status, name="status"),  # JS가 폴링으로 호출할 주소
    path("post/<int:post_id>/request/", views.request_analysis, name="request"),
    path("post/<int:post_id>/result/", views.result, name="result"),
    path("upload/", views.upload_and_analyze, name="upload"),
    path("<int:analysis_id>/result/", views.standalone_result, name="standalone_result"),
]
