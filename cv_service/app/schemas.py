from pydantic import BaseModel  # 데이터의 "모양"을 정의하는 FastAPI의 기본 클래스
from typing import List  # "이건 리스트(목록) 타입이다"라고 표시할 때 씀

class DetectedItemPayload(BaseModel):
    category: str  # 상의/하의/신발 등 큰 분류
    label: str  # 세부 명칭 (예: "니트", "청바지")
    bbox_x: float  # 바운딩박스 좌측 상단 x 좌표 (0~1 비율)
    bbox_y: float  # 바운딩박스 좌측 상단 y 좌표 (0~1 비율)
    bbox_width: float  # 바운딩박스 너비 (0~1 비율)
    bbox_height: float  # 바운딩박스 높이 (0~1 비율)
    search_url: str = ""  # 쇼핑 검색 링크, 없으면 빈 문자열


class StyleScorePayload(BaseModel):
    style_name: str  # 스타일 이름 (예: "캐주얼", "스트릿")
    ratio: float  # 비율(%), 예: 60.0


class CallbackPayload(BaseModel):
    callback_token: str  # Django가 검증할 토큰 (analysis.callback_token과 비교됨)
    detected_items: List[DetectedItemPayload] = []  # 검출된 아이템 목록, 기본값은 빈 리스트
    style_scores: List[StyleScorePayload] = []  # 스타일 비율 목록, 기본값은 빈 리스트
    interpretation: str = ""  # LLM 해석 텍스트, 기본값은 빈 문자열