# 세부 라벨링 개선 (Gemini 라벨 생성 + 중복 아이템 합치기) — 2026-10-13

## 1. 기술문서

### 한 줄 요약
아이템의 세부 명칭(라벨)을 **FashionCLIP이 후보 중에서 고르던 방식**에서 **Gemini가 사진을 보고 직접 짓는 방식**으로 바꿨다. FashionCLIP은 없애지 않고 Gemini가 실패했을 때 쓰는 예비용으로 남겼다. 또 좌우 신발처럼 같은 아이템이 두 번 표시되던 문제를 합치기 처리로 없앴다.

### 왜 바꿨나
비전 LLM 연동 직후 테스트에서 두 가지가 보였다.

| 증상 | 원인 |
|---|---|
| 와이드 청바지가 "하의 - 레깅스"로 표시 | FashionCLIP은 미리 적어 둔 후보 8개 중 하나를 **반드시** 골라야 해서, 딱 맞는 후보가 없으면 엉뚱한 것을 고른다 |
| "신발 - 스니커즈"가 두 줄 | 탐지 모델이 왼발과 오른발을 따로 잡았다 |

게다가 같은 화면에서 해석문은 "빈티지 청바지"라고 쓰는데 목록에는 "레깅스"라고 나와 서로 어긋났다.

### 검토한 두 가지 방법

| | A. Gemini에게 라벨도 맡기기 (선택) | B. FashionCLIP 후보 문구 다듬기 |
|---|---|---|
| 정확도 | 높음. 사진 전체를 보고 이름을 지음 | 낮음. 한 군데를 고치면 다른 사진에서 또 틀림 |
| 작업량 | 적음. 기존 호출에 요청 한 줄 추가 | 많음. 문구 수정과 재테스트를 반복 |
| 추가 비용 | 거의 없음. 호출 횟수는 그대로 1번 | 없음 |
| 단점 | Gemini 의존도가 커짐 | 구조적 한계가 남음 |

A의 단점은 FashionCLIP을 예비로 남겨서 줄였다.

### 전체 흐름
```
detect_items(image)              ← ① 탐지 (위치 + 큰 카테고리)
      ↓
label_items(image, items)        ← ② FashionCLIP (예비 라벨을 먼저 채워 둠)
      ↓
interpret_style(image, items)    ← ③ Gemini (스타일 비율 + 해석문 + 아이템별 라벨)
      │   성공 → 라벨을 Gemini 것으로 덮어씀   ★
      │   실패 → 손대지 않음 (②의 라벨이 그대로 남음)
      ↓
merge_duplicates(items)          ← ④ 카테고리와 라벨이 같은 아이템은 하나만 남김   ★
      ↓
CallbackPayload 조립 → Django 콜백으로 전송
```

### 신규/변경 파일

| 파일 | 상태 | 내용 |
|---|---|---|
| `cv_service/app/interpretation.py` | 수정 | 응답 모양에 아이템 라벨 추가, 프롬프트에 번호·위치·3번 요청 추가, `apply_labels` 함수 추가 |
| `cv_service/app/labeling.py` | 수정 | `merge_duplicates` 함수 추가 |
| `cv_service/app/main.py` | 수정 | `merge_duplicates` 호출 한 줄 추가 |
| `.gitignore` | 수정 | `.vscode/` 추가 (에디터 개인 설정 폴더) |

Django 쪽과 `schemas.py`는 수정하지 않았다. 콜백으로 보내는 데이터의 모양은 그대로이고 라벨 칸에 들어가는 글자만 달라졌기 때문이다.

### Gemini에게 주는 정보
- 사진
- 탐지된 아이템의 **번호, 큰 카테고리, 위치**(사진 크기 대비 비율)
- FashionCLIP이 고른 라벨은 **주지 않는다.** "레깅스"라고 미리 알려 주면 거기에 끌려갈 수 있어서다.

### 라벨 길이 제한 (15자)
쇼핑 검색 링크에 라벨이 들어가는데, 한글은 주소에 넣으면 한 글자가 9글자로 늘어난다. Django의 `search_url` 칸은 최대 200자라서, 라벨을 15자로 제한해 링크가 그 안에 들어오게 했다.

---

## 2. 클래스·함수 단위 코드리뷰

### `ItemLabelResult` — 번호로 짝을 맞추는 이유
Gemini의 답을 "몇 번 아이템의 이름은 무엇"이라는 쌍으로 받는다. 이름만 순서대로 받는 방법도 있지만, LLM이 하나를 빼먹거나 순서를 바꾸면 그 뒤가 전부 밀려서 잘못 붙는다. 번호를 함께 받으면 빠진 것은 빠진 대로 두고 나머지는 정확히 붙일 수 있다.

### `build_prompt` — 위치를 함께 알려 주는 이유
상의가 두 개(후드티와 그 안의 티셔츠) 잡힌 경우, 카테고리만 알려 주면 Gemini가 어느 것이 몇 번인지 알 수 없다. 그래서 "왼쪽 20%, 위 35% 지점부터 너비 50%, 높이 55%"처럼 위치를 적어 준다. `:.0%`는 0.35 같은 숫자를 "35%"로 적어 주는 서식이다.

이전에는 이 함수가 FashionCLIP 라벨을 프롬프트에 넣었는데, 이제는 넣지 않는다.

### `apply_labels` — 이상한 답에 대한 방어
세 가지를 걸러 낸다.
- **없는 번호**: 아이템이 4개인데 Gemini가 7번을 답하면 무시한다. 이 검사가 없으면 리스트 범위를 벗어나 에러가 난다.
- **빈 라벨**: 빈 문자열이면 덮어쓰지 않는다. FashionCLIP 라벨이 남는 편이 낫다.
- **긴 라벨**: 15자에서 자른다.

아쉬운 점: 15자에서 기계적으로 자르기 때문에 단어 중간에서 끊길 수 있다. 프롬프트에서 15자 이내로 요청하므로 실제로 잘리는 일은 드물 것으로 본다.

### `interpret_style` — `apply_labels`의 위치가 곧 예비 장치
`apply_labels`는 `try / except` **뒤에** 있다. Gemini 호출이 실패하면 `except`에서 바로 `return`하므로 이 줄까지 오지 않는다. 그래서 따로 "실패하면 FashionCLIP을 써라"라는 코드를 쓰지 않아도, 먼저 채워 둔 FashionCLIP 라벨이 저절로 남는다.

짚어 둘 점: 이 함수는 값을 돌려주는 동시에 넘겨받은 `items`의 내용도 바꾼다. 함수 이름만 봐서는 라벨까지 바뀐다는 것을 알기 어렵다. `label_items`도 같은 방식이라 일관성은 있지만, 독스트링에 "아이템 라벨도 갱신함"이라고 적어 두었다.

### `merge_duplicates` — 무엇을 "같다"고 보는가
큰 카테고리와 세부 라벨이 **둘 다** 같을 때만 같은 아이템으로 본다. 그래서 후드티와 그 안의 티셔츠처럼 카테고리가 같아도 라벨이 다르면 둘 다 남는다.

좌우 신발이 합쳐지려면 Gemini가 두 신발에 똑같은 이름을 붙여야 한다. 프롬프트에 "같은 아이템이 여러 번호로 잡혔으면 완전히 똑같은 명칭을 써줘"라고 요청한 이유다.

아쉬운 점 두 가지.
- 합칠 때 첫 번째 것의 위치(bbox)만 남고 두 번째 것의 위치는 버려진다. 지금은 화면에 박스를 그리지 않아서 문제가 없지만, 나중에 사진 위에 박스를 그리게 되면 신발 한 짝에만 박스가 생긴다.
- Gemini가 좌우 신발에 조금이라도 다른 이름을 붙이면 합쳐지지 않는다.

### `main.py` — 순서가 중요한 한 줄
`merge_duplicates`는 `interpret_style` **다음에** 불러야 한다. Gemini가 라벨을 덮어쓴 뒤의 최종 라벨을 기준으로 중복을 걸러야 하기 때문이다.

### 지금은 하지 않기로 한 최적화
Gemini가 성공하면 FashionCLIP이 채운 라벨은 덮어써지므로 그 계산 시간은 버려진다. "Gemini가 실패했을 때만 FashionCLIP을 돌리는" 구조로 바꾸면 시간을 줄일 수 있다. 하지만 두 번째 분석부터 전체가 3초 안에 끝나는 것을 확인했기 때문에 지금은 손대지 않았다. 느려지는 것이 체감되면 그때 한다.

---

## 3. 코드 한 줄 한 줄 주석

### `.gitignore` (추가한 부분)
```
.vscode/
```
VS Code가 만드는 개인 설정 폴더를 깃이 무시하게 한다.

### `cv_service/app/interpretation.py` (전체)
```python
import base64  # 이미지(바이트)를 글자(문자열)로 바꿔서 API에 실어 보낼 때 씀
import io  # 파일로 저장하지 않고 메모리 안에서 이미지를 JPEG로 변환할 때 씀
from typing import List  # "이건 리스트 타입이다"라고 표시할 때 씀
from google import genai  # Gemini API 공식 라이브러리
from pydantic import BaseModel, Field  # LLM이 돌려줄 답의 "모양"을 정의

MODEL_NAME = "gemini-3.8-flash"  # 사용할 Gemini 모델 (무료 등급 제공)
FALLBACK_INTERPRETATION = "스타일 해석을 생성하지 못했습니다. 잠시 후 다시 분석을 요청해 주세요."  # LLM 호출 실패 시 대신 보여줄 문구
MAX_LABEL_LENGTH = 15  # 라벨 최대 글자 수 (한글은 URL에 넣으면 9배로 길어져서, 쇼핑 검색 링크가 DB 한도 200자를 넘지 않게)  ★추가

client = genai.Client()  # 환경변수 GEMINI_API_KEY를 자동으로 읽어서 접속 준비 (서버 뜰 때 한 번만 실행)


class StyleScoreResult(BaseModel):  # 스타일 하나의 모양
    style_name: str = Field(description="스타일 이름 (한국어, 예: 캐주얼, 미니멀)")  # description은 LLM이 읽는 설명
    ratio: float = Field(description="이 스타일이 차지하는 비율(%), 전체 합은 100")  # 숫자(소수 가능)로 받음


class ItemLabelResult(BaseModel):  # 아이템 하나의 세부 명칭  ★추가
    number: int = Field(description="아이템 번호 (요청에 적힌 번호 그대로)")  # 어느 아이템의 이름인지 짝을 맞추는 번호
    label: str = Field(description="세부 명칭 (한국어, 15자 이내, 예: 와이드 청바지)")  # Gemini가 지은 이름


class StyleAnalysisResult(BaseModel):  # LLM 답 전체의 모양
    style_scores: List[StyleScoreResult]  # 스타일 비율 목록
    interpretation: str = Field(description="패션 초보자를 위한 쉬운 한국어 해석")  # 해석 문장
    item_labels: List[ItemLabelResult]  # 탐지된 아이템별 세부 명칭  ★추가


# LLM에게 보낼 요청문. {item_lines} 자리에 탐지 결과가 끼워 넣어짐  ★위치 안내와 3번 요청 추가
PROMPT_TEMPLATE = """너는 패션을 잘 모르는 사람에게 옷 잘 입는 사람의 착장을 쉽게 설명해주는 스타일 분석가야.
첨부한 사진 속 착장을 분석해줘.

이 사진에서 자동 탐지된 아이템은 다음과 같아 (위치는 사진 전체 크기 대비 비율):
{item_lines}

요청:
1. style_scores: 이 착장을 구성하는 스타일을 2~4개 고르고, 각 스타일의 비율(%)을 합이 100이 되게 매겨줘. 스타일 이름은 짧은 한국어 단어로, 서로 겹치지 않게.
2. interpretation: 이 착장이 왜 잘 어울려 보이는지 3~5문장으로 설명해줘. 색 조합, 핏, 아이템 조합을 근거로 들고, 전문 용어는 피하거나 풀어서 써줘.
3. item_labels: 위 목록의 번호마다, 그 위치에 있는 아이템의 세부 명칭을 사진을 보고 지어줘. 쇼핑몰에서 검색할 만한 한국어 명칭으로 15자 이내 (예: 와이드 청바지, 차콜 후드티). 양쪽 신발처럼 같은 아이템이 여러 번호로 잡혔으면 완전히 똑같은 명칭을 써줘.

탐지된 아이템 목록이 사진과 다르면 사진을 우선해."""


def image_to_base64(image):
    """PIL Image를 JPEG로 변환한 뒤 base64 문자열로 바꿈 (API가 요구하는 형식)"""
    buffer = io.BytesIO()  # 메모리 안의 가짜 파일
    image.save(buffer, format="JPEG")  # 그 가짜 파일에 JPEG로 저장
    return base64.b64encode(buffer.getvalue()).decode("utf-8")  # 바이트 → base64 글자


def build_prompt(items):
    """탐지 결과를 '1. 하의 - 왼쪽 20%, 위 35% 지점부터 너비 50%, 높이 55%' 같은 줄들로 만들어 프롬프트에 끼워 넣음"""
    lines = [
        f"{number}. {item['category']} - 왼쪽 {item['bbox_x']:.0%}, 위 {item['bbox_y']:.0%} 지점부터 "  # 번호, 카테고리, 박스 시작 위치
        f"너비 {item['bbox_width']:.0%}, 높이 {item['bbox_height']:.0%}"  # 박스 크기. :.0%는 0.35를 "35%"로 적어주는 서식
        for number, item in enumerate(items, start=1)  # 아이템마다 1번부터 번호를 매기며 반복
    ]
    item_lines = "\n".join(lines) if lines else "(탐지된 아이템 없음)"  # 줄바꿈으로 이어 붙임, 하나도 없으면 대체 문구
    return PROMPT_TEMPLATE.format(item_lines=item_lines)  # 요청문의 {item_lines} 자리에 끼워 넣음


def normalize_scores(scores):
    """같은 이름은 합치고, 비율 합이 100이 되도록 맞춤 (Django DB 제약에 걸리지 않게)"""
    merged = {}  # {스타일 이름: 비율 합계}를 담을 빈 dict
    for score in scores:  # LLM이 준 스타일을 하나씩 살펴봄
        name = score.style_name.strip()[:50]  # 앞뒤 공백 제거 + DB 최대 길이(50자)에 맞춤
        if not name or score.ratio <= 0:  # 이름이 비었거나 비율이 0 이하면
            continue  # 버리고 다음 것으로
        merged[name] = merged.get(name, 0) + score.ratio  # 같은 이름이 또 나오면 비율을 더함

    total = sum(merged.values())  # 모든 비율의 합
    if total == 0:  # 쓸 수 있는 결과가 하나도 없으면
        return []  # 빈 리스트 (0으로 나누는 에러도 방지)

    return [
        {"style_name": name, "ratio": round(ratio / total * 100, 1)}  # 전체 대비 비율로 다시 계산, 소수 첫째 자리까지
        for name, ratio in merged.items()  # 합쳐진 스타일마다
    ]


def apply_labels(items, item_labels):  # ★추가
    """Gemini가 지어준 세부 명칭으로 각 아이템의 label을 덮어씀 (번호가 이상하거나 빈 값이면 기존 라벨 유지)"""
    for result in item_labels:  # Gemini가 준 (번호, 이름) 쌍을 하나씩
        index = result.number - 1  # 프롬프트는 1번부터, 파이썬 리스트는 0번부터라 1을 뺌
        label = result.label.strip()[:MAX_LABEL_LENGTH]  # 앞뒤 공백 제거 + 길이 제한
        if 0 <= index < len(items) and label:  # 실제로 있는 번호이고 라벨이 비어 있지 않을 때만
            items[index]["label"] = label  # 그 아이템의 라벨을 Gemini 것으로 교체


def interpret_style(image, items):
    """사진 + 탐지 결과를 Gemini에 보내서 (스타일 비율 리스트, 해석 텍스트)를 돌려받고, 아이템 라벨도 갱신함"""
    try:  # 여기서부터 except 전까지는 실패할 수 있는 구간
        interaction = client.interactions.create(  # Gemini에 요청 보내기
            model=MODEL_NAME,  # 어떤 모델을 쓸지
            input=[  # 보낼 재료 목록
                {"type": "text", "text": build_prompt(items)},  # 글로 된 요청
                {"type": "image", "data": image_to_base64(image), "mime_type": "image/jpeg"},  # 사진
            ],
            response_format={  # "자유로운 글 말고, 이 모양의 JSON으로만 답해"라고 강제
                "type": "text",  # 답은 글자로
                "mime_type": "application/json",  # 그 글자의 형식은 JSON
                "schema": StyleAnalysisResult.model_json_schema(),  # 위에서 정의한 클래스를 JSON 모양 설명서로 변환
            },
        )
        result = StyleAnalysisResult.model_validate_json(interaction.output_text)  # JSON 글자 → 파이썬 객체 (모양이 틀리면 에러)
    except Exception as error:  # 한도 초과, 네트워크 오류, 이상한 응답 등 뭐가 터져도
        print(f"[interpret_style] LLM 호출 실패: {error}")  # 서버 로그에 원인만 남기고
        return [], FALLBACK_INTERPRETATION  # 여기서 끝냄 → 아래 apply_labels는 실행되지 않음

    apply_labels(items, result.item_labels)  # 성공했을 때만 실행됨 → 실패 시엔 FashionCLIP 라벨이 그대로 남음  ★추가
    return normalize_scores(result.style_scores), result.interpretation  # (정리된 스타일 비율, 해석문) 두 개를 묶어서 반환
```

### `cv_service/app/labeling.py` (추가한 함수)
```python
def merge_duplicates(items):
    """카테고리와 라벨이 모두 같은 아이템은 첫 번째 것만 남김 (예: 왼발/오른발 신발)"""
    seen = set()  # 이미 나온 (카테고리, 라벨) 조합을 기억해 두는 집합
    unique = []  # 중복을 뺀 결과를 담을 리스트
    for item in items:  # 아이템을 하나씩 살펴봄
        key = (item["category"], item["label"])  # 이 아이템을 구분하는 기준: (카테고리, 라벨) 한 쌍
        if key in seen:  # 이미 나온 조합이면
            continue  # 건너뜀
        seen.add(key)  # 처음 보는 조합이면 기억해 두고
        unique.append(item)  # 결과에 넣음
    return unique  # 중복이 빠진 리스트 반환
```

### `cv_service/app/main.py` (전체)
```python
from fastapi import FastAPI, UploadFile, Form  # UploadFile: 업로드 파일 타입, Form: 파일과 같이 오는 텍스트 필드
from PIL import Image  # 업로드된 파일을 실제 이미지 객체로 열기 위한 라이브러리
from urllib.parse import quote  # 한글 라벨을 URL에 안전하게 넣기 위한 인코딩 함수
from .schemas import CallbackPayload, DetectedItemPayload, StyleScorePayload  # 데이터 모양 정의들
from .callback import send_callback  # Django로 결과 POST 보내는 함수
from .detection import detect_items  # ①탐지: 박스+카테고리
from .labeling import label_items, merge_duplicates  # ②세부분류: 박스에 세부 라벨 붙이기 + 중복 합치기  ★변경
from .interpretation import interpret_style  # ③해석: 스타일 비율 + 해석 텍스트 (Gemini)


app = FastAPI()  # FastAPI 앱 본체 생성

@app.get("/health")  # 서버가 살아 있는지 확인하는 주소
def health_check():
    return {"status": "ok"}  # 살아 있으면 이 답을 돌려줌

@app.post("/analyze")  # 분석 요청을 받는 주소
def analyze(
    image: UploadFile,  # 업로드된 사진 파일
    callback_url: str = Form(...),  # 결과를 돌려보낼 Django 주소 (필수)
    callback_token: str = Form(...),  # Django가 검증할 토큰 (필수)
):
    pil_image = Image.open(image.file).convert("RGB")  # 업로드된 파일을 이미지 객체로 열고, 모델이 기대하는 RGB로 통일

    items = detect_items(pil_image)        # ①탐지: [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...]
    items = label_items(pil_image, items)   # ②세부분류: FashionCLIP으로 예비 라벨을 먼저 채워 둠
    style_scores, interpretation = interpret_style(pil_image, items)  # ③해석: 성공하면 라벨도 Gemini 것으로 덮어씀
    items = merge_duplicates(items)  # ④같은 아이템(양쪽 신발 등)은 하나만 남김 — 반드시 ③ 다음에  ★추가

    detected_item_payloads = [
        DetectedItemPayload(
            category=item["category"],  # 큰 분류
            label=item["label"],  # 세부 명칭 (Gemini 성공 시 Gemini 라벨)
            bbox_x=item["bbox_x"],  # 박스 왼쪽 위 x (0~1)
            bbox_y=item["bbox_y"],  # 박스 왼쪽 위 y (0~1)
            bbox_width=item["bbox_width"],  # 박스 너비 (0~1)
            bbox_height=item["bbox_height"],  # 박스 높이 (0~1)
            search_url=(
                f"https://search.shopping.naver.com/search/all?query={quote(item['label'])}"  # 라벨로 쇼핑 검색 주소 조립
                if item["label"] else ""  # 라벨이 없으면 링크도 비움
            ),
        )
        for item in items  # 중복이 빠진 아이템마다
    ]  # dict 리스트를 CallbackPayload가 요구하는 Pydantic 객체 리스트로 변환

    payload = CallbackPayload(
        callback_token=callback_token,  # Django가 준 토큰을 그대로 돌려보냄
        detected_items=detected_item_payloads,     # 탐지+라벨링 결과
        style_scores=[StyleScorePayload(**score) for score in style_scores],  # dict 리스트 → Pydantic 객체 리스트
        interpretation=interpretation,  # Gemini가 생성한 해석 텍스트
    )

    send_callback(callback_url, payload)  # Django 콜백 주소로 결과 전송

    return {"ok": True}  # 요청한 쪽(Celery 작업)에 "처리 끝"을 알림
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### zero-shot 분류의 한계
FashionCLIP은 "이 사진이 후보 문장들 중 어느 것과 가장 비슷한가"를 고른다. 후보에 정답이 없어도 그중 하나를 반드시 고르기 때문에, 후보 목록이 현실의 다양한 옷을 다 담지 못하면 틀린 답이 나온다. 후보를 늘려도 끝이 없다. 반면 LLM은 후보 없이 이름을 직접 지을 수 있다.

### 예비 장치 (fallback)
주된 방법이 실패했을 때 대신 쓰는 방법. 여기서는 Gemini가 주된 방법이고 FashionCLIP이 예비다. 예비 값을 **먼저 채워 두고** 주된 방법이 성공하면 덮어쓰는 순서로 짜면, "실패하면 이렇게 해라"라는 코드를 따로 쓰지 않아도 된다.

### 한 번의 호출에 여러 일을 시키기
LLM 호출은 횟수가 늘수록 시간과 한도를 더 쓴다. 스타일 비율, 해석문, 아이템 라벨을 한 번의 호출로 함께 받으면 호출 횟수가 그대로라 추가 부담이 거의 없다. 토큰(LLM이 글을 세는 단위)의 대부분은 사진과 해석문이 차지하고, 라벨은 짧은 단어 몇 개라 미미하다.

### LLM에게 힌트를 주지 않는 판단
틀렸을 수 있는 정보("레깅스")를 미리 알려 주면 LLM이 그쪽으로 끌려갈 수 있다. 확실한 정보(카테고리, 위치)만 주고 불확실한 정보는 빼는 것도 프롬프트 설계의 일부다.

### `enumerate(items, start=1)`
리스트를 돌면서 번호도 함께 받는 방법. `start=1`을 주면 0이 아니라 1부터 센다. 사람이 읽는 번호는 1부터, 파이썬 리스트의 위치는 0부터라서 `apply_labels`에서는 다시 1을 뺀다.

### `set`과 "이미 본 것" 기억하기
`set`(집합)은 같은 값을 한 번만 담는 자료 구조이고, 어떤 값이 들어 있는지 확인하는 속도가 빠르다. "이미 나온 조합인가"를 확인하는 용도에 잘 맞는다.

### 튜플을 구분 기준으로 쓰기
`(item["category"], item["label"])`처럼 값 두 개를 괄호로 묶은 것이 튜플이다. 두 값이 모두 같아야 같은 것으로 취급되므로, "카테고리와 라벨이 둘 다 같은 경우"를 한 번에 비교할 수 있다.

### 서버를 켠 직후의 첫 요청이 느린 이유 (워밍업)
모델은 서버가 켜질 때 불러오지만, 실제 계산에 필요한 준비의 일부는 첫 요청 때 이뤄진다. 그래서 첫 분석은 오래 걸리고 두 번째부터 빨라진다.

### 단계별 사양 영향
탐지와 FashionCLIP은 내 노트북 CPU로 계산하므로 노트북 사양의 영향을 받는다. Gemini는 구글 서버에서 계산하므로 사양과 무관하고 인터넷과 구글 서버 상황에 좌우된다.

---

## 5. 트러블슈팅

### 1) 와이드 청바지가 "레깅스"로 분류 — 라벨링 주체를 변경
- **증상**: 후드티 + 와이드 청바지 사진에서 "하의 - 레깅스"로 표시. 같은 화면의 해석문은 "빈티지 청바지"라고 써서 서로 어긋났다. 이전 테스트에서 흰 반팔 티셔츠가 "셔츠"로 나온 것과 같은 종류의 문제다.
- **원인**: FashionCLIP이 후보 8개 중 하나를 반드시 골라야 하는 구조. 후보에 "와이드 청바지"가 없었다.
- **해결**: 후보 문구를 다듬는 대신, 이미 사진을 보고 있는 Gemini에게 라벨도 짓게 했다. FashionCLIP은 예비용으로 남겼다.

### 2) 서버를 켠 뒤 첫 분석이 1분 30초 이상 걸림
- **증상**: 코드를 적용하고 서버를 다시 켠 뒤 첫 분석을 요청하자, 결과 페이지가 3초마다 상태만 확인할 뿐 한참 동안 바뀌지 않았다.
- **의심한 것**: 라벨링을 Gemini로 넘겨서 느려졌나, 노트북 사양이 부족한가.
- **확인 결과**: 같은 사진으로 두 번째 분석을 하니 3초 안에 끝났다. 서버를 켠 직후 첫 요청의 준비 시간(워밍업) 때문이었다. 라벨을 Gemini에게 추가로 요청한 것은 호출 횟수가 그대로라 원인이 아니었다.
- **결론**: 코드 수정 없음. 서버를 다시 켠 뒤 첫 분석만 느리다는 것을 알아 두면 된다.

### 결과 검증
가죽 자켓 + 가죽 미니스커트 착장 사진으로 브라우저 전체 흐름을 확인했다.
- 라벨: 하의 - 레더 미니스커트 / 모자 - 블랙 로고 볼캡 / 상의 - 블랙 크롭 티셔츠 / 아우터 - 크롭 레더 자켓 / 가방 - 블랙 미니 토트백. 색과 소재까지 담긴 이름이 나왔고 해석문과 어긋나지 않는다.
- 스타일 비율: 락시크 50 / 스트리트 30 / 캐주얼 20.

### 남은 관찰 사항
- **신발이 목록에 없다.** 사진에는 부츠가 보이는데 목록에는 없다. 라벨링이 아니라 그 앞 단계인 탐지 모델이 놓친 것으로 보인다. `detection.py`의 `CONFIDENCE_THRESHOLD = 0.5`를 조정해 볼 지점이다.
- **스타일 이름 표기가 흔들린다.** 이전 분석에서는 "스트릿", 이번에는 "스트리트"로 나왔다. 스타일 이름을 자유 생성으로 정했을 때 예상한 부작용이다. 여러 분석을 서로 비교하는 기능을 만들게 되면 고정 목록으로 바꾸는 것을 다시 검토해야 한다.
