from fastapi import FastAPI, UploadFile, Form, Header, HTTPException  # Header: 요청 헤더 값 받기, HTTPException: 에러 응답 보내기
from PIL import Image  # 업로드된 파일을 실제 이미지 객체로 열기 위한 라이브러리
from urllib.parse import quote  # 한글 라벨을 URL에 안전하게 넣기 위한 인코딩 함수
from .schemas import CallbackPayload, DetectedItemPayload, StyleScorePayload  # 데이터 모양 정의들
from .callback import send_callback, is_allowed_callback_url  # Django로 결과 보내는 함수 + 콜백 주소 검사
from .detection import detect_items  # ①탐지: 박스+카테고리
from .labeling import label_items, merge_duplicates  # ②세부분류: 박스에 세부 라벨 붙이기 + 중복 합치기
from .interpretation import interpret_style  # ③해석: 스타일 비율 + 해석 텍스트 (Gemini)
import logging  # 파이썬 기본 기록 도구
import os  # 환경변수(INTERNAL_API_TOKEN)를 읽을 때 씀
import secrets  # 토큰을 안전하게(상수 시간으로) 비교할 때 씀

logging.basicConfig(  # 서버가 시작될 때 한 번만 하는 기록 설정 (이게 없으면 시각/단계/이름이 안 붙음)
    level=logging.INFO,  # 정보 단계 이상(정보/경고/에러)을 모두 기록
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",  # 한 줄 모양: 시각 / 단계 / 어느 파일인지 / 내용
)

app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/analyze")
def analyze(
    image: UploadFile,
    callback_url: str = Form(...),
    callback_token: str = Form(...),
    x_internal_token: str = Header(default=""),  # "X-Internal-Token" 헤더 값 (없으면 빈 문자열)
):
    expected = os.environ.get("INTERNAL_API_TOKEN", "")  # 내가 알고 있는 정답 출입증
    if not expected or not secrets.compare_digest(x_internal_token.encode(), expected.encode()):  # 정답이 설정 안 됐거나, 보낸 값이 다르면
        raise HTTPException(status_code=401, detail="invalid internal token")  # 분석 시작 전에 거절
    if not is_allowed_callback_url(callback_url):  # 결과를 보낼 주소가 허용 목록 밖이면
        raise HTTPException(status_code=400, detail="callback_url not allowed")  #Gemini를 시작하기 전에 거절    
    pil_image = Image.open(image.file).convert("RGB")  # 업로드된 파일을 이미지 객체로 열고, 모델이 기대하는 RGB로 통일
    items = detect_items(pil_image)        # ①탐지: [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...]
    items = label_items(pil_image, items)   # ②세부분류: 각 아이템에 "label" 키 채워 넣음
    style_scores, interpretation = interpret_style(pil_image, items)  # ③해석: (스타일 비율 리스트, 해석 텍스트)
    items = merge_duplicates(items)  # 같은 아이템(양쪽 신발 등)은 하나만 남김
    

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
        style_scores=[StyleScorePayload(**score) for score in style_scores],  # dict 리스트 → Pydantic 객체 리스트
        interpretation=interpretation,  # Gemini가 생성한 해석 텍스트
    )

    send_callback(callback_url, payload)

    return {"ok": True}