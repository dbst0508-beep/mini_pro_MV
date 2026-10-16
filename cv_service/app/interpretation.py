import base64  # 이미지(바이트)를 글자(문자열)로 바꿔서 API에 실어 보낼 때 씀
import io  # 파일로 저장하지 않고 메모리 안에서 이미지를 JPEG로 변환할 때 씀
import logging  # print 대신 쓰는 파이썬 기본 기록 도구 (중요도 단계와 시각이 자동으로 붙음)
from typing import List  # "이건 리스트 타입이다"라고 표시할 때 씀
from google import genai  # Gemini API 공식 라이브러리
from google.genai import types  # 접속 옵션(재시도 횟수 등)을 정하는 도구
from pydantic import BaseModel, Field  # LLM이 돌려줄 답의 "모양"을 정의

MODEL_NAME = "gemini-3.8-flash"  # 사용할 Gemini 모델 (무료 등급 제공)
FALLBACK_INTERPRETATION = "스타일 해석을 생성하지 못했습니다. 잠시 후 다시 분석을 요청해 주세요."  # LLM 호출 실패 시 대신 보여줄 문구
MAX_LABEL_LENGTH = 15  # ★ 라벨 최대 글자 수 (한글은 URL에 넣으면 9배로 길어져서, 쇼핑 검색 링크가 DB 한도 200자를 넘지 않게)

logger = logging.getLogger(__name__)  # 이 파일 전용 기록 담당자 (이름이 "app.interpretation"으로 붙어서 어느 파일의 로그인지 알 수 있음)

LLM_TIMEOUT = 30  # Gemini 답을 기다리는 최대 시간(초). 넘으면 포기하고 탐지 결과만 돌려줌

LLM_RETRY_ATTEMPTS = 1  # 서버가 붐빌 때(503) 다시 시도하는 횟수. 기본값 3은 너무 오래 걸려서 줄임

client = genai.Client(  # 환경변수 GEMINI_API_KEY를 자동으로 읽어서 접속 준비 (서버 뜰 때 한 번만 실행)
    http_options=types.HttpOptions(  # 접속 방식 설정
        retry_options=types.HttpRetryOptions(attempts=LLM_RETRY_ATTEMPTS),  # 재시도 횟수 제한
    ),
)


class StyleScoreResult(BaseModel):
    style_name: str = Field(description="스타일 이름 (한국어, 예: 캐주얼, 미니멀)")
    ratio: float = Field(description="이 스타일이 차지하는 비율(%), 전체 합은 100")


class ItemLabelResult(BaseModel):  # ★ 아이템 하나의 세부 명칭
    number: int = Field(description="아이템 번호 (요청에 적힌 번호 그대로)")
    label: str = Field(description="세부 명칭 (한국어, 15자 이내, 예: 와이드 청바지)")


class StyleAnalysisResult(BaseModel):
    style_scores: List[StyleScoreResult]  # 스타일 비율 목록
    interpretation: str = Field(description="패션 초보자를 위한 쉬운 한국어 해석")
    item_labels: List[ItemLabelResult]  # ★ 탐지된 아이템별 세부 명칭


PROMPT_TEMPLATE = """너는 패션을 잘 모르는 사람에게 옷 잘 입는 사람의 착장을 쉽게 설명해주는 스타일 분석가야.
첨부한 사진 속 착장을 분석해줘.

이 사진에서 자동 탐지된 아이템은 다음과 같아 (위치는 사진 전체 크기 대비 비율):
{item_lines}

요청:
1. style_scores: 이 착장을 구성하는 스타일을 2~4개 고르고, 각 스타일의 비율(%)을 합이 100이 되게 매겨줘. 스타일 이름은 짧은 한국어 단어로, 서로 겹치지 않게.
2. interpretation: 이 착장이 왜 잘 어울려 보이는지 3~5문장으로 설명해줘. 색 조합, 핏, 아이템 조합을 근거로 들고, 전문 용어는 피하거나 풀어서 써줘.
3. item_labels: 위 목록의 번호마다, 그 위치에 있는 아이템의 세부 명칭을 사진을 보고 지어줘. 쇼핑몰에서 검색할 만한 한국어 명칭으로 15자 이내 (예: 와이드 청바지, 차콜 후드티). 양쪽 신발처럼 같은 아이템이 여러 번호로 잡혔으면 완전히 똑같은 명칭을 써줘.

탐지된 아이템 목록이 사진과 다르면 사진을 우선해."""  # ★ 위치 안내 + 3번 요청 추가


def image_to_base64(image):
    """PIL Image를 JPEG로 변환한 뒤 base64 문자열로 바꿈 (API가 요구하는 형식)"""
    buffer = io.BytesIO()  # 메모리 안의 가짜 파일
    image.save(buffer, format="JPEG")  # 그 가짜 파일에 JPEG로 저장
    return base64.b64encode(buffer.getvalue()).decode("utf-8")  # 바이트 → base64 글자


def build_prompt(items):
    """★ 탐지 결과를 '1. 하의 - 왼쪽 20%, 위 35% 지점부터 너비 50%, 높이 55%' 같은 줄들로 만들어 프롬프트에 끼워 넣음"""
    lines = [
        f"{number}. {item['category']} - 왼쪽 {item['bbox_x']:.0%}, 위 {item['bbox_y']:.0%} 지점부터 "
        f"너비 {item['bbox_width']:.0%}, 높이 {item['bbox_height']:.0%}"  # :.0%는 0.35를 "35%"로 적어주는 서식
        for number, item in enumerate(items, start=1)  # 1번부터 번호 매기기
    ]
    item_lines = "\n".join(lines) if lines else "(탐지된 아이템 없음)"
    return PROMPT_TEMPLATE.format(item_lines=item_lines)


def normalize_scores(scores):
    """같은 이름은 합치고, 비율 합이 100이 되도록 맞춤 (Django DB 제약에 걸리지 않게)"""
    merged = {}
    for score in scores:
        name = score.style_name.strip()[:50]  # 앞뒤 공백 제거 + DB 최대 길이(50자)에 맞춤
        if not name or score.ratio <= 0:
            continue  # 이름이 비었거나 비율이 0 이하면 버림
        merged[name] = merged.get(name, 0) + score.ratio  # 같은 이름이 또 나오면 비율을 더함

    total = sum(merged.values())
    if total == 0:
        return []  # 쓸 수 있는 결과가 하나도 없으면 빈 리스트

    names = list(merged)  # 스타일 이름만 순서대로 꺼낸 리스트 (dict를 list로 바꾸면 키만 남음)
    ratios = [round(merged[name] / total * 100, 1) for name in names[:-1]]  # 마지막 하나를 뺀 나머지만 전체 대비 비율로 계산 + 반올림
    ratios.append(round(100.0 - sum(ratios), 1))  # 마지막 스타일은 "100 - 나머지 합"으로 채워서 합이 정확히 100이 되게 함
    return [
        {"style_name": name, "ratio": ratio}  # 이름과 비율을 한 묶음(dict)으로
        for name, ratio in zip(names, ratios)  # zip: 두 리스트를 같은 순서끼리 짝지어 하나씩 꺼냄
    ]


def apply_labels(items, item_labels):
    """★ Gemini가 지어준 세부 명칭으로 각 아이템의 label을 덮어씀 (번호가 이상하거나 빈 값이면 기존 라벨 유지)"""
    for result in item_labels:
        index = result.number - 1  # 프롬프트는 1번부터, 파이썬 리스트는 0번부터라 1을 뺌
        label = result.label.strip()[:MAX_LABEL_LENGTH]  # 앞뒤 공백 제거 + 길이 제한
        if 0 <= index < len(items) and label:  # 실제로 있는 번호이고 라벨이 비어 있지 않을 때만
            items[index]["label"] = label


def interpret_style(image, items):
    """사진 + 탐지 결과를 Gemini에 보내서 (스타일 비율 리스트, 해석 텍스트)를 돌려받고, 아이템 라벨도 갱신함"""
    try:
        interaction = client.interactions.create(
            model=MODEL_NAME,
            input=[
                {"type": "text", "text": build_prompt(items)},  # 글로 된 요청
                {"type": "image", "data": image_to_base64(image), "mime_type": "image/jpeg"},  # 사진
            ],
            response_format={  # "자유로운 글 말고, 이 모양의 JSON으로만 답해"라고 강제
                "type": "text",
                "mime_type": "application/json",
                "schema": StyleAnalysisResult.model_json_schema(),
            },
            timeout=LLM_TIMEOUT,  # 이 시간 안에 답이 안 오면 에러 → 아래 except가 받아서 대체 문구로 처리
        )
        result = StyleAnalysisResult.model_validate_json(interaction.output_text)  # JSON 글자 → 파이썬 객체 (모양이 틀리면 에러)
    except Exception as error:  # 한도 초과, 네트워크 오류, 이상한 응답 등 뭐가 터져도
        logger.warning("LLM 호출 실패: %s", error)  # 경고 단계로 기록 (분석은 계속되므로 에러가 아니라 경고)
        return [], FALLBACK_INTERPRETATION  # 탐지 결과는 살릴 수 있게 빈 값으로 돌려줌

    apply_labels(items, result.item_labels)  # ★ 성공했을 때만 실행됨 → 실패 시엔 FashionCLIP 라벨이 그대로 남음
    return normalize_scores(result.style_scores), result.interpretation
