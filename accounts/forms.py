from django.contrib.auth.forms import UserCreationForm  # 장고가 기본 제공하는 "회원가입 폼" 뼈대
from .models import User  # 우리 프로젝트의 커스텀 User 모델 (accounts.User)


class SignUpForm(UserCreationForm):  # UserCreationForm을 상속받아 model만 바꿔치기
    class Meta(UserCreationForm.Meta):  # 부모의 Meta(필드 구성 등)를 그대로 물려받음
        model = User  # 딱 이 한 줄만 오버라이드: "장고 기본 User" 대신 "우리 User"를 쓰게 지정