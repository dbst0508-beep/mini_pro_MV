# cv_service 비전 LLM(Gemini) 연동 (스타일 비율 + 해석 텍스트) — 2026-10-13

## 1. 기술문서

### 한 줄 요약
`cv_service`(FastAPI)의 `/analyze`가 **고정된 더미 값으로 돌려주던 스타일 비율(`style_scores`)과 해석 텍스트(`interpretation`)**를, **Gemini가 실제 사진을 보고 만든 결과**로 바꿨다. 이로써 분석 결과의 모든 항목(탐지, 세부 라벨, 스타일 비율, 해석문)이 진짜 모델 결과가 됐다.

### 비전 LLM이란
글만 읽는 것이 아니라 **사진도 함께 보고** 글로 답할 수 있는 AI 모델. 이 프로젝트에서는 착장 사진을 보여 주고 "어떤 스타일이 몇 %씩 섞여 있는지, 왜 잘 어울려 보이는지"를 쓰게 한다.

### 결정 사항과 이유

| 결정 | 선택 | 이유 |
|---|---|---|
| 모델을 어디서 돌릴까 | 내 PC가 아니라 **외부 API 호출** | 내 PC는 인텔 내장 그래픽이라 비전 LLM을 돌릴 수 없음 (트러블슈팅 1번) |
| 어떤 API | **Gemini** (`gemini-3.8-flash`) | 결제 수단 없이 무료 등급 키로 시작할 수 있어 과금 걱정이 없음 |
| 스타일 이름 | **LLM 자유 생성** | 미리 정한 목록 없이 LLM이 사진에 맞는 이름을 지음 |
| LLM에 주는 재료 | **사진 + CV 탐지 결과** | 해석문이 화면에 표시된 탐지 아이템과 어긋나지 않게 하려고 |

### 전체 흐름
```
이미지 업로드
      ↓
detect_items(image)              ← ① 탐지 모델 (위치 + 큰 카테고리)
      ↓
label_items(image, items)        ← ② FashionCLIP (세부 라벨)
      ↓
interpret_style(image, items)    ← ③ Gemini (스타일 비율 + 해석 텍스트)  ★ 이번에 추가
      ↓
CallbackPayload 조립 → Django 콜백으로 전송
```

### 신규/변경 파일

| 파일 | 상태 | 역할 |
|---|---|---|
| `cv_service/app/interpretation.py` | 신규 | Gemini 호출, 응답 모양 정의, 결과 정리, 실패 처리 |
| `cv_service/app/main.py` | 수정 | 더미 값 대신 `interpret_style()` 결과를 사용 |
| `cv_service/pyproject.toml` | 수정 | `google-genai` 의존성 추가 |
| `cv_service/.env` | 신규 (깃에 올리지 않음) | Gemini API 키 보관 |
| `.gitignore` | 수정 | `.env`를 깃 추적에서 제외 |
| `README.md` | 수정 | 키 설정 안내, 서버 실행 명령 갱신 |

Django 쪽 코드는 수정하지 않았다. 콜백으로 보내는 데이터의 모양이 더미 때와 똑같기 때문이다.

### API 키 관리
- 키는 `cv_service/.env` 파일에 `GEMINI_API_KEY=키값` 형태로 둔다.
- `GEMINI_API_KEY`는 Gemini 라이브러리가 자동으로 찾는 정해진 이름이다.
- `.env`는 `.gitignore`에 등록돼 있어 깃허브에 올라가지 않는다.
- 서버를 켤 때 `--env-file .env` 옵션으로 이 파일의 값을 읽혀야 한다.

### 서버 실행 명령 (변경됨)
```bash
# cv_service 폴더에서
uv run --env-file .env uvicorn app.main:app --reload --port 8001
```
`--env-file .env`가 없으면 키를 찾지 못해 서버가 켜지는 단계에서 실패한다.

### 과금 관련
- AI Studio의 키 목록에서 결제 등급이 "무료 등급"이면 요금이 나가지 않는다. 그 위의 파란 "결제 설정"은 유료로 올리는 링크일 뿐, 누르지 않으면 무료로 유지된다.
- 무료 등급에서 한도를 넘으면 요금이 붙는 것이 아니라 요청이 거절된다.
- 무료 등급으로 보낸 내용은 구글이 제품 개선에 사용한다. 실제 서비스로 남의 사진을 받게 되면 유료 등급 전환을 검토해야 한다.

---

## 2. 클래스·함수 단위 코드리뷰

### `client = genai.Client()` — 파일 최상단에 둔 이유
`ml_models.py`에서 모델을 파일 최상단에서 한 번만 불러온 것과 같은 생각이다. 서버가 켜질 때 딱 한 번 접속 준비를 하고, 요청마다 다시 만들지 않는다. 대신 **키가 없으면 서버 자체가 안 켜진다.** 요청을 받고 나서야 "키가 없네"를 알게 되는 것보다 켤 때 바로 알게 되는 쪽이 낫다고 봤다.

### `StyleScoreResult`, `StyleAnalysisResult` — LLM 답의 모양을 강제
LLM은 원래 글을 자유롭게 쓴다. 그런데 우리는 답에서 스타일 이름과 숫자를 코드로 꺼내 써야 한다. 그래서 Pydantic 클래스로 "이런 칸이 있는 JSON으로만 답해"라고 모양을 정해 줬다. `schemas.py`에서 콜백 데이터 모양을 정의한 것과 같은 도구를 LLM 응답에 쓴 것이다.

`schemas.py`의 `StyleScorePayload`와 칸 구성이 같은데도 따로 만든 이유는, 이쪽에는 `Field(description=...)`로 **LLM에게 주는 설명**이 붙어 있기 때문이다. 하나는 Django와의 약속이고 하나는 Gemini와의 약속이라 역할이 다르다. 다만 칸 이름이 바뀌면 두 군데를 같이 고쳐야 하는 부담은 있다.

### `PROMPT_TEMPLATE` — 프로젝트의 핵심 가치를 담은 부분
"패션을 잘 모르는 사람에게 옷 잘 입는 사람의 착장을 쉽게 설명"이라는 역할을 첫 줄에 줬다. 이 프로젝트의 대상 사용자 정의를 그대로 옮긴 것이다. "전문 용어는 피하거나 풀어서", "색 조합, 핏, 아이템 조합을 근거로"처럼 구체적으로 요구했고, 마지막 줄에 "탐지 목록이 사진과 다르면 사진을 우선해"를 넣어 CV 모델의 오분류에 끌려가지 않게 했다.

아쉬운 점: 프롬프트가 코드 안에 문자열로 박혀 있어서, 문구를 고치려면 코드를 수정해야 한다. 지금 규모에서는 문제없다.

### `image_to_base64` — 사진을 글자로 바꾸는 이유
API는 인터넷으로 글자(JSON)를 주고받는다. 사진은 글자가 아니라서 그대로는 실을 수 없다. base64는 사진 데이터를 알파벳과 숫자로만 이루어진 긴 문자열로 바꿔 주는 표준 방식이다.

아쉬운 점: 원본 크기 그대로 보낸다. 휴대폰 원본처럼 큰 사진이면 전송량이 커지고 느려질 수 있다. 문제가 되면 보내기 전에 줄이는 처리를 추가할 자리다.

### `build_prompt` — 탐지 결과를 글로 바꾸기
탐지 결과 리스트를 `- 아우터: 블레이저` 같은 줄들로 바꿔 프롬프트에 끼운다. 라벨이 빈 문자열이면 "세부 분류 없음"으로, 탐지된 것이 하나도 없으면 "(탐지된 아이템 없음)"으로 적어서 프롬프트가 어색하게 비지 않게 했다.

### `normalize_scores` — 자유 생성의 부작용을 막는 방어
스타일 이름을 LLM이 자유롭게 짓게 했기 때문에 필요한 함수다.
- **같은 이름 합치기**: Django의 `StyleScore`에는 "한 분석 안에 같은 스타일 이름이 두 번 들어갈 수 없다"는 규칙(`unique_together`)이 있다. LLM이 "캐주얼"을 두 번 내면 콜백 저장이 에러로 죽는다. 그래서 미리 합친다.
- **합을 100으로 맞추기**: LLM이 합을 95나 110으로 내도 전체 대비 비율로 다시 계산한다.
- **50자 자르기**: DB의 `style_name` 최대 길이에 맞춘다.

아쉬운 점: 소수 첫째 자리로 반올림하므로 합이 99.9나 100.1이 될 수 있다. 화면 표시에는 지장이 없다. 또 "스트릿"과 "스트리트"처럼 표기만 다른 이름은 같은 것으로 묶지 못한다. 자유 생성을 고른 대가다.

### `interpret_style` — 실패해도 탐지 결과는 살린다
`try / except`로 전체를 감쌌다. 한도 초과, 인터넷 문제, 이상한 응답 등 무엇이 터져도 서버는 죽지 않고 **빈 스타일 목록 + 안내 문구**를 돌려준다. 덕분에 탐지와 라벨링 결과는 정상적으로 Django에 저장된다.

아쉬운 점 두 가지.
- `except Exception`은 모든 에러를 한꺼번에 잡는다. 코드 오타 같은 내 실수까지 조용히 삼킬 수 있어서, 문제가 생기면 서버 로그의 `[interpret_style] LLM 호출 실패` 줄을 꼭 봐야 한다.
- 로그를 `print`로 남긴다. 지금은 충분하지만 배포 단계에서는 정식 로깅 도구로 바꾸는 것이 좋다.

### `main.py` 변경 — 호출 한 줄, 교체 두 줄
`interpret_style`이 값 두 개를 묶어 돌려주므로 `style_scores, interpretation = ...`으로 나눠 받는다. `StyleScorePayload(**score)`는 dict를 풀어서 칸에 맞춰 넣는 문법이다.

`/analyze`는 Gemini 응답을 기다리는 몇 초 동안 응답을 돌려주지 않는다. 원래도 CV 모델 추론 동안 기다리던 구조라 달라진 것은 없지만, 분석 한 건이 전보다 몇 초 길어졌다.

---

## 3. 코드 한 줄 한 줄 주석

### `.gitignore` (추가한 부분)
```
# 환경변수 (API 키 등 비밀값)
.env
```
이름이 `.env`인 파일은 어느 폴더에 있든 깃이 무시한다.

### `cv_service/.env` (형식만, 실제 키는 적지 않음)
```
GEMINI_API_KEY=여기에_발급받은_키
```

### `cv_service/pyproject.toml` (전체)
```toml
[project]
name = "cv-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",           # FastAPI 프레임워크 본체
    "uvicorn[standard]>=0.32.0",  # FastAPI 앱 실행 서버
    "python-multipart>=0.0.12",   # 이미지 업로드(멀티파트) 파싱
    "pillow>=12.3.0",             # 이미지 처리
    "requests>=2.34.2",           # Django 콜백 전송
    "torch>=2.5.0",               # PyTorch 본체
    "transformers>=4.46.0",       # 허깅페이스 모델 로딩/실행
    "timm>=1.0.0",                # 탐지 모델의 ResNet-50 백본 구현체
    "google-genai>=2.29.0",       # Gemini API 공식 라이브러리 (이번에 추가, `uv add google-genai`로 설치)
]
```

### `cv_service/app/interpretation.py` (전체)
```python
import base64  # 이미지(바이트)를 글자(문자열)로 바꿔서 API에 실어 보낼 때 씀
import io  # 파일로 저장하지 않고 메모리 안에서 이미지를 JPEG로 변환할 때 씀
from typing import List  # "이건 리스트 타입이다"라고 표시할 때 씀
from google import genai  # Gemini API 공식 라이브러리
from pydantic import BaseModel, Field  # LLM이 돌려줄 답의 "모양"을 정의

MODEL_NAME = "gemini-3.8-flash"  # 사용할 Gemini 모델 (무료 등급 제공)
FALLBACK_INTERPRETATION = "스타일 해석을 생성하지 못했습니다. 잠시 후 다시 분석을 요청해 주세요."  # LLM 호출 실패 시 대신 보여줄 문구

client = genai.Client()  # 환경변수 GEMINI_API_KEY를 자동으로 읽어서 접속 준비 (서버 뜰 때 한 번만 실행)


class StyleScoreResult(BaseModel):  # 스타일 하나의 모양
    style_name: str = Field(description="스타일 이름 (한국어, 예: 캐주얼, 미니멀)")  # description은 LLM이 읽는 설명
    ratio: float = Field(description="이 스타일이 차지하는 비율(%), 전체 합은 100")  # 숫자(소수 가능)로 받음


class StyleAnalysisResult(BaseModel):  # LLM 답 전체의 모양
    style_scores: List[StyleScoreResult]  # 스타일 비율 목록
    interpretation: str = Field(description="패션 초보자를 위한 쉬운 한국어 해석")  # 해석 문장


# LLM에게 보낼 요청문. {item_lines} 자리에 탐지 결과가 끼워 넣어짐
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
    lines = [f"- {item['category']}: {item['label'] or '세부 분류 없음'}" for item in items]  # 아이템마다 한 줄씩, 라벨이 비었으면 대체 문구
    item_lines = "\n".join(lines) if lines else "- (탐지된 아이템 없음)"  # 줄바꿈으로 이어 붙임, 하나도 없으면 대체 문구
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


def interpret_style(image, items):
    """사진 + 탐지 결과를 Gemini에 보내서 (스타일 비율 리스트, 해석 텍스트)를 돌려받음"""
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
        return [], FALLBACK_INTERPRETATION  # 탐지 결과는 살릴 수 있게 빈 값으로 돌려줌

    return normalize_scores(result.style_scores), result.interpretation  # (정리된 스타일 비율, 해석문) 두 개를 묶어서 반환
```

### `cv_service/app/main.py` (전체)
```python
from fastapi import FastAPI, UploadFile, Form  # UploadFile: 업로드 파일 타입, Form: 파일과 같이 오는 텍스트 필드
from PIL import Image  # 업로드된 파일을 실제 이미지 객체로 열기 위한 라이브러리
from urllib.parse import quote  # 한글 라벨을 URL에 안전하게 넣기 위한 인코딩 함수
from .schemas import CallbackPayload, DetectedItemPayload, StyleScorePayload  # 데이터 모양 정의들
from .callback import send_callback  # Django로 결과 POST 보내는 함수
from .detection import detect_items  # ①탐지: 박스+카테고리
from .labeling import label_items  # ②세부분류: 박스에 세부 라벨 붙이기
from .interpretation import interpret_style  # ③해석: 스타일 비율 + 해석 텍스트 (Gemini)  ★추가


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
    items = label_items(pil_image, items)   # ②세부분류: 각 아이템에 "label" 키 채워 넣음
    style_scores, interpretation = interpret_style(pil_image, items)  # ③해석: (스타일 비율 리스트, 해석 텍스트)  ★추가

    detected_item_payloads = [
        DetectedItemPayload(
            category=item["category"],  # 큰 분류
            label=item["label"],  # 세부 명칭
            bbox_x=item["bbox_x"],  # 박스 왼쪽 위 x (0~1)
            bbox_y=item["bbox_y"],  # 박스 왼쪽 위 y (0~1)
            bbox_width=item["bbox_width"],  # 박스 너비 (0~1)
            bbox_height=item["bbox_height"],  # 박스 높이 (0~1)
            search_url=(
                f"https://search.shopping.naver.com/search/all?query={quote(item['label'])}"  # 라벨로 쇼핑 검색 주소 조립
                if item["label"] else ""  # 라벨이 없으면 링크도 비움
            ),
        )
        for item in items  # 탐지된 아이템마다
    ]  # dict 리스트를 CallbackPayload가 요구하는 Pydantic 객체 리스트로 변환

    payload = CallbackPayload(
        callback_token=callback_token,  # Django가 준 토큰을 그대로 돌려보냄
        detected_items=detected_item_payloads,     # 탐지+라벨링 결과
        style_scores=[StyleScorePayload(**score) for score in style_scores],  # dict 리스트 → Pydantic 객체 리스트  ★더미에서 교체
        interpretation=interpretation,  # Gemini가 생성한 해석 텍스트  ★더미에서 교체
    )

    send_callback(callback_url, payload)  # Django 콜백 주소로 결과 전송

    return {"ok": True}  # 요청한 쪽(Celery 작업)에 "처리 끝"을 알림
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 로컬 모델과 API의 차이
- **로컬 모델**: 모델 파일을 내 컴퓨터에 내려받아 내 컴퓨터의 힘으로 돌린다. 탐지 모델과 FashionCLIP이 이 방식이다. 돈은 안 들지만 컴퓨터 성능이 받쳐 줘야 한다.
- **API**: 모델은 회사(구글)의 서버에 있고, 나는 인터넷으로 "이 사진 분석해 줘"라고 요청만 보낸다. 내 컴퓨터 성능과 무관하지만 사용량에 따라 요금이나 한도가 있다.

비전 LLM은 탐지 모델보다 몇십 배 크기 때문에, 전용 그래픽카드(GPU)가 없으면 로컬로는 사실상 못 돌린다.

### GPU와 `nvidia-smi`
GPU는 그래픽카드의 연산 장치로, AI 모델 계산을 CPU보다 훨씬 빨리 한다. `nvidia-smi`는 NVIDIA 그래픽카드의 상태를 보여 주는 명령어다. 이 명령어가 없다고 나오면 NVIDIA 카드가 없거나 드라이버가 없다는 뜻이다. 확실한 확인은 윈도우 작업 관리자 → 성능 탭 → GPU 항목 이름으로 한다.

### API 키와 `.env`
API 키는 "이 요청은 내 계정이 보낸 것"임을 증명하는 비밀번호 같은 문자열이다. 남이 알면 내 계정으로 마음대로 쓸 수 있다. 그래서 코드에 직접 적지 않고 `.env`라는 별도 파일에 두고, 그 파일은 `.gitignore`로 깃에서 빼 둔다. **`.gitignore`에 먼저 등록하고 그다음에 `.env`를 만드는 순서**가 안전하다.

### 환경변수와 `--env-file`
환경변수는 프로그램이 실행될 때 바깥에서 건네받는 설정값이다. `uv run --env-file .env ...`는 `.env` 파일 안의 값들을 환경변수로 넣어 준 뒤 프로그램을 실행한다. Gemini 라이브러리는 `GEMINI_API_KEY`라는 이름의 환경변수를 스스로 찾아 읽는다.

### 구조화 출력 (structured output)
LLM에게 "이 모양의 JSON으로만 답해"라고 강제하는 기능. 자유로운 글에서 숫자를 골라내는 불안한 작업 없이, 정해진 칸에서 값을 바로 꺼낼 수 있다. Pydantic 클래스를 `model_json_schema()`로 모양 설명서로 바꿔 보내고, 받은 답을 `model_validate_json()`으로 다시 파이썬 객체로 만든다.

### base64
사진 같은 데이터를 알파벳과 숫자로만 된 문자열로 바꾸는 표준 방식. 글자만 실을 수 있는 통로(JSON)에 사진을 실어 보낼 때 쓴다.

### 함수가 값 두 개를 돌려주기
`return a, b`처럼 쓰면 두 값이 한 묶음(튜플)으로 나간다. 받는 쪽에서 `x, y = 함수()`라고 쓰면 하나씩 나눠 담긴다. 출력해 보면 `([...], '...')`처럼 괄호로 묶여 보인다.

### `**` 로 dict 풀어 넣기
`StyleScorePayload(**{'style_name': '캐주얼', 'ratio': 45.0})`는 `StyleScorePayload(style_name='캐주얼', ratio=45.0)`과 같다. dict의 키와 값을 함수의 칸 이름과 값으로 펼쳐 준다.

### 상대 경로와 `..`
경로는 "지금 터미널이 있는 폴더에서 그 파일까지 가는 길"이다. `..`는 한 칸 위 폴더를 뜻한다. `cv_service` 폴더에서 `../media/analysis_uploads/test.jpg`라고 쓰면 "한 칸 올라가서 media → analysis_uploads → test.jpg"가 된다.

### 가상환경이 두 개인 구조
이 프로젝트는 Django용(`mini_project1/.venv`)과 cv_service용(`cv_service/.venv`) 가상환경이 따로 있다. `uv run`과 `uv add`는 켜져 있는 가상환경이 아니라 **지금 있는 폴더의 프로젝트 환경**을 기준으로 동작한다.

---

## 5. 트러블슈팅

### 1) `nvidia-smi: command not found` — 로컬 모델 계획을 API로 변경
- **상황**: 처음에는 과금 걱정 때문에 허깅페이스에서 비전 LLM을 받아 로컬로 돌리는 쪽을 생각했다. 가능한지 보려고 `nvidia-smi`를 실행했더니 명령어가 없다고 나왔다.
- **원인**: 내 PC는 인텔 내장 그래픽이라 NVIDIA GPU가 없다. WSL2에서는 윈도우에 NVIDIA 드라이버가 있어야 이 명령어가 따라 들어온다.
- **주의**: 에러 아래에 뜬 `apt install nvidia-utils-...` 목록은 우분투의 자동 안내일 뿐이다. WSL2는 윈도우의 드라이버를 빌려 쓰는 구조라 리눅스 쪽에 설치하면 해결되지 않고 꼬일 수 있다. 설치하지 않았다.
- **결정**: 로컬 비전 LLM을 포기하고 API 방식으로 확정. 과금 걱정은 결제 수단을 등록하지 않은 Gemini 무료 등급 키로 해결했다. 기존 CV 모델 2개는 CPU로 잘 돌아가므로 그대로 둔다.

### 2) `warning: VIRTUAL_ENV=... does not match the project environment path` 경고
- **상황**: `cv_service` 폴더에서 `uv add`, `uv run`을 실행할 때마다 이 경고가 떴다.
- **원인**: 터미널에 Django용 가상환경이 켜진 상태(`(mini_project1)` 표시)로 `cv_service` 폴더에 들어갔기 때문. uv가 "켜져 있는 환경은 무시하고 이 폴더의 `.venv`를 쓰겠다"고 알려 준 것이다.
- **결론**: 에러가 아니고 원하던 동작이다. 설치와 실행은 `cv_service/.venv`에 정상적으로 됐다. 경고가 거슬리면 그 터미널에서 `deactivate`를 하면 된다.

### 결과 검증
- **단독 테스트**(블레이저 + 흰 티 + 청바지 + 구두 사진): 캐주얼 45 / 미니멀 30 / 댄디 25. 탐지 결과로는 블레이저와 청바지만 넘겼는데 해석문에 흰 티셔츠와 구두도 언급됐다. LLM이 사진을 직접 보고 있다는 확인.
- **브라우저 전체 흐름 테스트**(후드티 + 와이드 청바지 사진): 캐주얼 45 / 스트릿 35 / 빈티지 20. 해석문이 "후드티 아래로 흰색 티셔츠를 살짝 드러내어" 같은 세부까지 짚었다.
- **남은 문제** (다음 브랜치 `feature/labeling-improve`에서 처리):
  - 와이드 청바지가 "하의 - 레깅스"로 표시됨 (FashionCLIP zero-shot 분류의 한계)
  - 좌우 신발이 따로 탐지돼 "신발 - 스니커즈"가 두 줄로 표시됨
