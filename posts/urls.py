from django.urls import path

from . import views

app_name = "posts"  # base.html에서 썼던 {% url 'posts:feed' %}의 "posts" 부분

urlpatterns = [
    path("", views.feed, name="feed"),  # 루트 경로("/")를 feed 뷰에 연결
]
