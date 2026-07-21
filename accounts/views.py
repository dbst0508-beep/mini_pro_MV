from django.shortcuts import render, redirect
from .forms import SignUpForm
from django.contrib.auth import login,logout
from django.contrib.auth.forms import AuthenticationForm
from django.views.decorators.http import require_POST

def signup_page(request):  # 회원가입 페이지 뷰
    if request.user.is_authenticated:  # 이미 로그인된 상태라면
        return redirect("posts:feed")  # 회원가입 폼 보여줄 필요 없이 바로 피드로 보냄

    if request.method == "POST":  # 폼을 "제출"한 요청인지 구분 (이 줄이 빠져있었음)
        form = SignUpForm(request.POST)  # 사용자가 입력한 데이터를 폼에 채워 넣음
        if form.is_valid():  # username 중복, 비밀번호 일치/강도 등 검증을 여기서 다 실행
            form.save()  # 검증 통과했으면 실제로 User 객체를 DB에 저장
            return redirect("accounts:login_page")  # 가입 완료 -> 로그인 페이지로 이동
    else:  # GET 요청 (페이지를 처음 열었을 때)
        form = SignUpForm()  # 빈 폼 하나를 새로 만듦 (아직 아무 값도 안 채워짐)

    return render(request, "accounts/signup.html", {"form": form})  # POST 실패 시에도 여기로 와서 에러 메시지 포함해 다시 보여줌

def mypage(request):
    return render(request, "accounts/mypage.html")


def login_page(request):  # 로그인 페이지 뷰
    if request.user.is_authenticated:  # 이미 로그인된 상태라면
        return redirect("posts:feed")  # 로그인 폼 보여줄 필요 없이 바로 피드로 보냄
    if request.method == "POST":  # 로그인 폼을 제출한 요청
        form = AuthenticationForm(request, data=request.POST)  # request도 같이 넘겨야 함 (내부적으로 인증 시도에 씀)
        if form.is_valid():  # 아이디/비밀번호가 실제로 맞는지 여기서 authenticate()가 내부적으로 실행됨
            login(request, form.get_user())  # 검증 통과한 유저로 세션을 채워서 "로그인 상태"로 만듦
            return redirect("posts:feed")  # 로그인 성공 -> 피드 페이지로 이동
    else:  # GET 요청 (로그인 페이지 처음 열었을 때)
        form = AuthenticationForm()  # 빈 로그인 폼

    return render(request, "accounts/login.html", {"form": form})  # 실패 시에도 에러 메시지 담긴 폼을 다시 보여줌

@require_POST  # GET으로 들어오면 뷰 실행 전에 자동으로 405(Method Not Allowed) 응답
def logout_view(request):  # 로그아웃 처리 뷰
    logout(request)  # 세션에서 로그인 정보를 지워서 "로그인 안 된 상태"로 되돌림
    return redirect("posts:feed")  # 로그아웃 후 피드 페이지로 이동