from django import forms  # Django 폼 도구 (이미지 검사 기능이 들어 있음)
from django.core.exceptions import ValidationError  # "검사 실패"를 알리는 Django 표준 에러

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 업로드 최대 크기: 10MB (1024*1024 바이트 = 1MB)


def validate_uploaded_image(file):
    """업로드 파일이 있고, 10MB 이하이고, 진짜 이미지인지 확인. 하나라도 아니면 ValidationError"""
    if file is None:  # 파일 없이 제출된 경우
        raise ValidationError("사진을 선택해 주세요.")
    if file.size > MAX_UPLOAD_SIZE:  # 크기 검사를 먼저: 큰 파일을 굳이 열어 보지 않도록
        raise ValidationError("사진은 10MB 이하만 올릴 수 있습니다.")
    forms.ImageField().clean(file)  # Pillow로 실제로 열어 보고, 이미지가 아니면 ValidationError ("올바른 이미지를 업로드하세요...")