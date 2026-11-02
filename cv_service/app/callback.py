import requests  # Django 콜백 주소로 HTTP 요청을 보낼 때 씀
from urllib.parse import urlparse  # 주소를 "http / web / 8000 / 경로"처럼 부분별로 쪼개 주는 표준 도구
from .schemas import CallbackPayload  # 보낼 데이터의 모양을 정의해둔 스키마

ALLOWED_CALLBACK_HOSTS = {"web", "localhost", "127.0.0.1"}  # 결과를 보내도 되는 곳: compose의 Django(web), 터미널 실행 시 내 컴퓨터


def is_allowed_callback_url(callback_url: str) -> bool:
    """콜백 주소가 http(s)이고, 호스트가 허용 목록에 있을 때만 True"""
    parsed = urlparse(callback_url)  # 주소를 부분별로 쪼갬
    return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_CALLBACK_HOSTS


def send_callback(callback_url: str, payload: CallbackPayload):
    response = requests.post(
        callback_url,
        json=payload.model_dump(),  # Pydantic 객체를 dict로 바꿔서 JSON으로 전송
        timeout=10,                 # 10초 넘으면 포기
        allow_redirects=False,      # "다른 데로 가세요"(3xx) 응답을 따라가지 않음 → 허용 목록 우회 방지
    )
    response.raise_for_status()  # Django가 저장에 실패하면 예외 발생 → /analyze가 500으로 응답 → Celery가 실패로 기록