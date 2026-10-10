from fastapi import FastAPI, UploadFile, Form  # UploadFile: 업로드 파일 타입, Form: 파일과 같이 오는 텍스트 필드
from PIL import Image  # 업로드된 파일을 실제 이미지 객체로 열기 위한 라이브러리
from urllib.parse import quote  # 한글 라벨을 URL에 안전하게 넣기 위한 인코딩 함수
from .schemas import CallbackPayload, DetectedItemPayload, StyleScorePayload  # 데이터 모양 정의들
from .callback import send_callback  # Django로 결과 POST 보내는 함수
from .detection import detect_items  # ①탐지: 박스+카테고리
from .labeling import label_items  # ②세부분류: 박스에 세부 라벨 붙이기

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/analyze")
def analyze(
    image: UploadFile,
    callback_url: str = Form(...),
    callback_token: str = Form(...),
):
    pil_image = Image.open(image.file).convert("RGB")  # 업로드된 파일을 이미지 객체로 열고, 모델이 기대하는 RGB로 통일

    items = detect_items(pil_image)        # ①탐지: [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...]
    items = label_items(pil_image, items)   # ②세부분류: 각 아이템에 "label" 키 채워 넣음

    detected_item_payloads = [
        DetectedItemPayload(
            category=item["category"],
            label=item["label"],
            bbox_x=item["bbox_x"],
            bbox_y=item["bbox_y"],
            bbox_width=item["bbox_width"],
            bbox_height=item["bbox_height"],
            search_url=(
                f"https://search.shopping.naver.com/search/all?query={quote(item['label'])}"
                if item["label"] else ""
            ),
        )
        for item in items
    ]  # dict 리스트를 CallbackPayload가 요구하는 Pydantic 객체 리스트로 변환

    payload = CallbackPayload(
        callback_token=callback_token,
        detected_items=detected_item_payloads,     # 이제 진짜 탐지+라벨링 결과
        # 스타일 비율/해석은 아직 더미 — 비전 LLM 연동은 다음 작업 범위
        style_scores=[
            StyleScorePayload(style_name="캐주얼", ratio=60.0),
            StyleScorePayload(style_name="스트릿", ratio=40.0),
        ],
        interpretation="(더미) 비전 LLM 연동 전이라 해석 텍스트는 임시 고정값입니다.",
    )

    send_callback(callback_url, payload)

    return {"ok": True}