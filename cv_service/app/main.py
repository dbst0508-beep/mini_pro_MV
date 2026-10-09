from fastapi import FastAPI, UploadFile, Form  # UploadFile: 업로드 파일 타입, Form: 파일과 같이 오는 텍스트 필드
from .schemas import CallbackPayload, DetectedItemPayload, StyleScorePayload  # 3번에서 만든 스키마들
from .callback import send_callback  # 5번 단계에서 만들 함수 (아직 파일 없어도 지금은 import만 적어둠)

app = FastAPI()  # 이 app 객체가 서버 전체를 대표함. uvicorn이 이 객체를 실행시킴

@app.get("/health")  # GET 요청으로 /health 주소에 접근하면 아래 함수가 실행됨
def health_check():
    return {"status": "ok"}  # 서버가 살아있는지 확인하는 용도, 고정된 응답만 돌려줌

@app.post("/analyze")  # Django가 "이 사진 분석해줘"라고 호출할 주소
def analyze(
    image: UploadFile,                 # 업로드된 이미지 파일 (멀티파트 폼으로 옴)
    callback_url: str = Form(...),       # 결과를 보낼 Django 콜백 전체 URL ("..." = 필수값이라는 뜻)
    callback_token: str = Form(...),     # Django가 검증할 토큰, 받은 그대로 다시 실어서 돌려줄 것
):
    # 지금은 더미 단계라, 이미지 내용은 읽지 않고(아직 모델이 없으니까) 고정된 가짜 결과를 만듦
    payload = CallbackPayload(
        callback_token=callback_token,                 # Django가 준 토큰을 그대로 돌려줌
        detected_items=[
            DetectedItemPayload(
                category="상의", label="니트",
                bbox_x=0.1, bbox_y=0.1, bbox_width=0.4, bbox_height=0.5,
                search_url="https://search.shopping.naver.com/search/all?query=니트",
            ),
            DetectedItemPayload(
                category="하의", label="청바지",
                bbox_x=0.15, bbox_y=0.55, bbox_width=0.35, bbox_height=0.4,
                search_url="https://search.shopping.naver.com/search/all?query=청바지",
            ),
        ],
        style_scores=[
            StyleScorePayload(style_name="캐주얼", ratio=60.0),
            StyleScorePayload(style_name="스트릿", ratio=40.0),
        ],
        interpretation="캐주얼한 니트와 청바지 조합으로, 편안하면서도 트렌디한 스트릿 무드가 느껴지는 룩입니다.",
    )

    send_callback(callback_url, payload)  # 5번에서 만들 함수 — Django로 실제 POST 전송

    return {"ok": True}  # Django(나중엔 Celery task)에게 "요청 잘 받았다"고 바로 응답