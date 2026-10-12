import requests  # Django 콜백 주소로 HTTP 요청을 보낼 때 씀 (Django tasks.py에서 쓰던 것과 동일한 라이브러리)
from .schemas import CallbackPayload  # 보낼 데이터의 모양을 정의해둔 스키마


def send_callback(callback_url: str, payload: CallbackPayload):
    response = requests.post(callback_url, json=payload.model_dump(), timeout=10)  # Pydantic 객체를 dict로 바꿔서 JSON으로 전송, 10초 넘으면 포기
    response.raise_for_status()  # Django가 저장에 실패하면 예외 발생 → /analyze가 500으로 응답 → Celery가 실패로 기록
