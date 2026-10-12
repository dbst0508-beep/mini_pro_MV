import base64  # 이미지(바이트)를 글자(문자열)로 바꿔서 API에 실어 보낼 때 씀
import io  # 파일로 저장하지 않고 메모리 안에서 이미지를 JPEG로 변환할 때 씀
from typing import List  # "이건 리스트 타입이다"라고 표시할 때 씀
from google import genai  # Gemini API 공식 라이브러리
from pydantic import BaseModel, Field  # LLM이 돌려줄 답의 "모양"을 정의

MODEL_NAME = "gemini-3.8-flash"  # 사용할 Gemini 모델 (무료 등급 제공)
FALLBACK_INTERPRETATION = "스타일 해석을 생성하지 못했습니다. 잠시 후 다시 분석을 요청해 주세요."  # LLM 호출 실패 시 대신 보여줄 문구

client = genai.Client()  # 환경변수 GEMINI_API_KEY를 자동으로 읽어서 접속 준비 (서버 뜰 때 한 번만 실행)


class StyleScoreResult(BaseModel):
    style_name: str = Field(description="스타일 이름 (한국어, 예: 캐주얼, 미니멀)")
    ratio: float = Field(description="이 스타일이 차지하는 비율(%), 전체 합은 100")


class StyleAnalysisResult(BaseModel):
    style_scores: List[StyleScoreResult]  # 스타일 비율 목록
    interpretation: str = Field(description="패션 초보자를 위한 쉬운 한국어 해석")


PROMPT_TEMPLATE = """너는 패션을 잘 모르는 사람에게 옷 잘 입는 사람의 착장을 쉽게 설명해주는 스타일 분석가야.
첨부한 사진 속 착장을 분석해줘.

참고로 이 사진에서 자동 탐지된 아이템은 다음과 같아:
{item_lines}

요청:
1. style_scores: 이 착장을 구성하는 스타일을 2~4개 고르고, 각 스타일의 비율(%)을 합이 100이 되게 매겨줘. 스타일 이름은 짧은 한국어 단어로, 서로 겹치지 않게.
2. interpretation: 이 착장이 왜 잘 어울려 보이는지 3~5문장으로 설명해줘. 색 조합, 핏, 아이템 조합을 근거로 들고, 전문 용어는 피하거나 풀어서 써줘.

탐지된 아이템 목록이 사진과 다르면 사진을 우선해."""


def image_to_base64(image):
    """PIL Image를 JPEG로 변환한 뒤 base64 문자열로 바꿈 (API가 요구하는 형식)"""
    buffer = io.BytesIO()  # 메모리 안의 가짜 파일
    image.save(buffer, format="JPEG")  # 그 가짜 파일에 JPEG로 저장
    return base64.b64encode(buffer.getvalue()).decode("utf-8")  # 바이트 → base64 글자


def build_prompt(items):
    """탐지 결과 리스트를 '- 아우터: 블레이저' 같은 줄들로 만들어 프롬프트에 끼워 넣음"""
    lines = [f"- {item['category']}: {item['label'] or '세부 분류 없음'}" for item in items]
    item_lines = "\n".join(lines) if lines else "- (탐지된 아이템 없음)"
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

    return [
        {"style_name": name, "ratio": round(ratio / total * 100, 1)}  # 전체 대비 비율로 다시 계산
        for name, ratio in merged.items()
    ]


def interpret_style(image, items):
    """사진 + 탐지 결과를 Gemini에 보내서 (스타일 비율 리스트, 해석 텍스트)를 돌려받음"""
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
        )
        result = StyleAnalysisResult.model_validate_json(interaction.output_text)  # JSON 글자 → 파이썬 객체 (모양이 틀리면 에러)
    except Exception as error:  # 한도 초과, 네트워크 오류, 이상한 응답 등 뭐가 터져도
        print(f"[interpret_style] LLM 호출 실패: {error}")  # 서버 로그에 원인만 남기고
        return [], FALLBACK_INTERPRETATION  # 탐지 결과는 살릴 수 있게 빈 값으로 돌려줌

    return normalize_scores(result.style_scores), result.interpretation
