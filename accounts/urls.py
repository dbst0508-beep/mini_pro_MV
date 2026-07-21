from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("mypage/", views.mypage, name="mypage"),
    path("login/", views.login_page, name="login_page"),
    path("signup/", views.signup_page, name="signup_page"),      # /signup/ -> 방금 만든 회원가입 뷰
    path("logout/", views.logout_view, name="logout"),           # /logout/ -> 방금 만든 로그아웃 뷰
]
