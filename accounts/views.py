from django.shortcuts import render


def mypage(request):
    return render(request, "accounts/mypage.html")


def login_page(request):
    return render(request, "accounts/login.html")  # 지금은 자리만, 로그인 로직 없음
