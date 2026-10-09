import requests  # Django 콜백 주소로 HTTP 요청을 보낼 때 씀 (Django tasks.py에서 쓰던 것과 동일한 라이브러리)
from .schemas import CallbackPayload  # 보낼 데이터의 모양을 정의해둔 스키마


def send_callback(callback_url: str, payload: CallbackPayload):
    requests.post(callback_url, json=payload.model_dump())  # Pydantic 객체를 dict로 바꿔서 JSON으로 전송