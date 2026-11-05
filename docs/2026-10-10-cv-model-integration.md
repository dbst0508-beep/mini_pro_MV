# cv_service 실제 CV 모델 연동 (탐지 + 세부 라벨링) — 2026-10-10

## 1. 기술문서

### 한 줄 요약
어제 만든 `cv_service`(FastAPI) 뼈대의 `/analyze`가 **고정된 더미 결과만 돌려주던 상태**에서, **실제 CV 모델 2개가 추론해서 만든 진짜 결과**를 돌려주도록 바꿨다. 스타일 비율(`style_scores`)과 해석 텍스트(`interpretation`)는 비전 LLM 연동 전이라 아직 고정값이고, **탐지(위치+큰 카테고리) + 세부 라벨링**만 실제 모델로 교체됐다.

### 사용한 모델 2개

| 역할 | 모델 | 방식 |
|---|---|---|
| ① 탐지 | `yainage90/fashion-object-detection` (conditional-detr-resnet-50 파인튜닝) | 객체 탐지 — 사진에서 bbox + 큰 카테고리(bag/bottom/dress/hat/outer/shoes/top) 7종을 직접 출력 |
| ② 세부 라벨링 | `patrickjohncyh/fashion-clip` (CLIP 기반) | zero-shot 분류 — ①에서 잘라낸 크롭 이미지를, 미리 정의한 한글 후보 라벨 목록 중 가장 유사한 것으로 매칭 |

### 전체 흐름
```
이미지 업로드 (PIL Image로 열기, RGB 통일)
      ↓
detect_items(image)          ← ① 탐지 모델
  → [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...]  (bbox는 0~1 정규화)
      ↓
label_items(image, items)    ← ② FashionCLIP (박스 영역 크롭 후 zero-shot 분류)
  → 각 item에 "label" 키 채워짐
      ↓
DetectedItemPayload 리스트로 변환 (search_url도 라벨 기반으로 동적 조립)
      ↓
CallbackPayload 조립 (style_scores/interpretation은 여전히 고정값)
      ↓
Django 콜백으로 전송
```

### 신규/변경 파일

| 파일 | 상태 | 역할 |
|---|---|---|
| `cv_service/pyproject.toml` | 수정 | `torch`, `transformers`, `timm` 의존성 추가 |
| `cv_service/app/ml_models.py` | 신규 | 모델/전처리기를 모듈 레벨에서 한 번만 로딩 |
| `cv_service/app/detection.py` | 신규 | 탐지 모델 추론 + bbox 정규화 + 영어→한글 카테고리 매핑 |
| `cv_service/app/labeling.py` | 신규 | 카테고리별 세부 라벨 후보 목록 + 크롭 + FashionCLIP zero-shot 분류 |
| `cv_service/app/main.py` | 수정 | `/analyze`가 더미 대신 위 두 모듈을 실제로 호출 |
| `README.md` | 수정 | cv_service 섹션, 기술 스택, 실행 안내 갱신 |

### 추가된 의존성과 그 이유
- `torch` — PyTorch, 두 모델이 공통으로 쓰는 딥러닝 프레임워크
- `transformers` — 허깅페이스 모델을 코드 몇 줄로 불러와 실행하는 라이브러리
- `timm` — 탐지 모델의 백본(ResNet-50)을 `transformers`가 내부적으로 가져다 쓰는 보조 라이브러리. 처음 서버 실행 시 `ImportError`로 발견되어 추가됨 (트러블슈팅 1번 참고)

---

## 2. 클래스·함수 단위 코드리뷰

### `ml_models.py` — 모듈 레벨 로딩 선택
모델 로딩 코드를 함수 안이 아니라 **파일 최상단**에 뒀다. `main.py`가 이 파일을 import하는 순간(서버 기동 시) 딱 한 번만 실행되게 하려는 의도 — `/analyze` 함수 안에 넣으면 요청마다 모델을 다시 불러와 치명적으로 느려진다. 다만 이 설계는 **서버가 뜨는 시점에 반드시 인터넷 연결(또는 로컬 캐시)이 있어야 한다**는 전제를 깐다 — 모델 다운로드가 실패하면 서버 자체가 기동 실패한다. 지금은 로컬 개발 단계라 문제없지만, 배포 시엔 "모델을 미리 이미지에 구워 넣거나, 기동 재시도 로직을 넣는" 고려가 필요할 수 있다.

### `detection.py`의 `CONFIDENCE_THRESHOLD = 0.5`
이 값보다 확신도가 낮은 탐지는 버린다. 지금은 임의로 0.5(50%)를 선택했는데, **왜 0.5가 적정한지 실험적으로 검증한 적은 없다.** 실제 테스트에서 "맞는 아이템이 안 잡힌다"거나 "말도 안 되는 게 잡힌다"는 패턴이 보이면 이 값을 조정해야 할 1순위 튜닝 포인트.

### `CATEGORY_KR` 매핑의 `.get(label_en, label_en)` 기본값 처리
모델이 내놓는 7개 카테고리는 다 매핑 테이블에 있지만, 혹시 모델이 업데이트되어 새 카테고리가 추가되는 극단적인 경우에도 **에러 없이 영어 원문을 그대로 쓰도록** 방어적으로 짜뒀다. 다만 이 경우 `labeling.py`의 `LABEL_CANDIDATES.get(item["category"], [])`가 매칭되는 후보가 없어 **세부 라벨이 항상 빈 문자열("")이 되는 조용한 실패**로 이어진다 — 에러는 안 나지만 결과 품질이 떨어지는 경로라 로그를 남기지 않은 건 아쉬운 지점.

### `labeling.py`의 `crop_item` — bbox를 다시 픽셀로 환산
`detect_items`가 이미 0~1로 정규화해서 돌려준 bbox를, `crop_item`에서 **다시 픽셀로 곱해서 되돌린다.** "정규화했다가 다시 되돌리는" 게 비효율로 보일 수 있지만, **DB 저장용 포맷(정규화)과 이미지 처리용 포맷(픽셀)의 책임을 각 함수가 자기 용도에 맞게 깔끔히 나눠 가진 것**이라 의도적인 설계다. 다만 `detect_items`가 애초에 픽셀 좌표도 함께 돌려줬다면 이 재계산 자체가 필요 없었을 거라, "약간의 중복 계산 vs 함수 책임 분리" 사이의 트레이드오프 선택.

### `main.py`의 `search_url` 조립 — `item["label"]`이 빈 문자열일 때
`if item["label"] else ""`로, 라벨링이 실패(빈 문자열)한 아이템은 검색 링크도 비워둔다. 합리적인 처리지만, **`DetectedItem.label`이 `blank=True`라서 Django 쪽도 빈 문자열을 그대로 받아들인다** — 화면(`result.html`)에서 `{{ item.category }} - {{ item.label }}`로 렌더링되면 "상의 - " 처럼 어색하게 보일 수 있다. 지금은 실제 테스트에서 라벨이 거의 다 채워져서 드러나지 않았지만, 템플릿 쪽 방어(라벨 없으면 카테고리만 표시)는 아직 안 돼 있는 지점.

---

## 3. 코드 한 줄 한 줄 주석

### `cv_service/pyproject.toml` (전체)
```toml
[project]
name = "cv-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",        # FastAPI 프레임워크 본체
    "uvicorn[standard]>=0.32.0",  # FastAPI 앱 실행 서버
    "python-multipart>=0.0.12",   # 이미지 업로드(멀티파트) 파싱
    "pillow>=12.3.0",          # 이미지 처리
    "requests>=2.34.2",        # Django 콜백 전송
    "torch>=2.5.0",            # PyTorch 본체
    "transformers>=4.46.0",    # 허깅페이스 모델 로딩/실행
    "timm>=1.0.0",             # 탐지 모델의 ResNet-50 백본 구현체 (transformers가 내부적으로 사용)
]
```

### `cv_service/app/ml_models.py` (전체)
```python
from transformers import AutoImageProcessor, AutoModelForObjectDetection  # ①탐지 모델 불러오는 클래스들
from transformers import CLIPModel, CLIPProcessor  # ②세부 라벨링(FashionCLIP) 불러오는 클래스들

DETECTION_MODEL_NAME = "yainage90/fashion-object-detection"  # ①번: 옷 위치(bbox) + 큰 카테고리 탐지
LABELING_MODEL_NAME = "patrickjohncyh/fashion-clip"  # ②번: 세부 라벨링 (zero-shot 분류)

# 탐지 모델 로딩 — 이 파일이 import되는 순간(서버가 뜰 때) 딱 한 번만 실행됨
detection_processor = AutoImageProcessor.from_pretrained(DETECTION_MODEL_NAME)  # 이미지를 모델 입력 형태로 전처리
detection_model = AutoModelForObjectDetection.from_pretrained(DETECTION_MODEL_NAME)  # 탐지 모델 본체
detection_model.eval()  # 추론 전용 모드로 전환 (학습 때만 쓰는 기능들을 꺼서 결과를 일정하게 만듦)

# 세부 라벨링 모델(FashionCLIP) 로딩
labeling_processor = CLIPProcessor.from_pretrained(LABELING_MODEL_NAME)  # 이미지+텍스트를 모델 입력 형태로 전처리
labeling_model = CLIPModel.from_pretrained(LABELING_MODEL_NAME)  # FashionCLIP 모델 본체
labeling_model.eval()  # 역시 추론 전용 모드로 전환
```

### `cv_service/app/detection.py` (전체)
```python
import torch  # 추론 중 불필요한 계산(역전파)을 끄는 데 씀
from .ml_models import detection_processor, detection_model  # 방금 만든 모델/전처리기

# 모델이 영어로 내놓는 카테고리명 → 우리 DB에 저장할 한글 카테고리명 매핑
CATEGORY_KR = {
    "bag": "가방",
    "bottom": "하의",
    "dress": "원피스",
    "hat": "모자",
    "outer": "아우터",
    "shoes": "신발",
    "top": "상의",
}

CONFIDENCE_THRESHOLD = 0.5  # 모델이 "이거 맞다"고 확신하는 정도가 이 값 미만이면 결과에서 버림


def detect_items(image):
    """PIL Image를 받아서 [{category, bbox_x, bbox_y, bbox_width, bbox_height}, ...] 형태로 반환"""
    inputs = detection_processor(images=image, return_tensors="pt")  # 이미지를 모델이 이해하는 숫자 배열(텐서)로 변환

    with torch.no_grad():  # 추론만 할 거라 학습용 계산(기울기 추적)을 꺼서 속도/메모리 절약
        outputs = detection_model(**inputs)  # 실제 모델 추론 실행

    image_width, image_height = image.size  # bbox를 0~1로 정규화할 때 쓸 원본 이미지 크기(픽셀)
    target_sizes = torch.tensor([[image_height, image_width]])  # 후처리 함수가 요구하는 (세로, 가로) 순서

    results = detection_processor.post_process_object_detection(
        outputs, threshold=CONFIDENCE_THRESHOLD, target_sizes=target_sizes
    )[0]  # 모델의 날것 출력을 "박스+라벨+확신도" 형태로 정리해줌. [0]은 이미지 1장 중 첫 번째라는 뜻

    items = []
    for score, label_id, box in zip(results["scores"], results["labels"], results["boxes"]):
        label_en = detection_model.config.id2label[label_id.item()]  # 숫자 라벨(예: 3) → 영어 이름("top")으로 변환
        category = CATEGORY_KR.get(label_en, label_en)  # 위 매핑 테이블로 한글 변환, 매핑에 없으면 영어 그대로

        x_min, y_min, x_max, y_max = box.tolist()  # 픽셀 좌표 4개 (좌상단 x,y / 우하단 x,y)

        items.append({
            "category": category,
            "bbox_x": x_min / image_width,                    # 0~1 비율로 정규화
            "bbox_y": y_min / image_height,
            "bbox_width": (x_max - x_min) / image_width,
            "bbox_height": (y_max - y_min) / image_height,
        })

    return items
```

### `cv_service/app/labeling.py` (전체)
```python
import torch  # 추론 중 불필요한 계산을 끄는 데 씀
from .ml_models import labeling_processor, labeling_model  # FashionCLIP 모델/전처리기

# 카테고리별 세부 라벨 후보: (영어 후보 텍스트, 한글 라벨)
LABEL_CANDIDATES = {
    "상의": [
        ("a photo of a t-shirt", "반팔 티셔츠"),
        ("a photo of a long sleeve t-shirt", "긴팔 티셔츠"),
        ("a photo of a shirt", "셔츠"),
        ("a photo of a blouse", "블라우스"),
        ("a photo of a knit sweater", "니트"),
        ("a photo of a hoodie", "후드티"),
        ("a photo of a sweatshirt", "맨투맨"),
        ("a photo of a crop top", "크롭탑"),
    ],
    "하의": [
        ("a photo of jeans", "청바지"),
        ("a photo of slacks", "슬랙스"),
        ("a photo of chino pants", "치노팬츠"),
        ("a photo of shorts", "반바지"),
        ("a photo of a skirt", "스커트"),
        ("a photo of leggings", "레깅스"),
        ("a photo of jogger pants", "조거팬츠"),
        ("a photo of cargo pants", "카고팬츠"),
    ],
    "아우터": [
        ("a photo of a coat", "코트"),
        ("a photo of a jacket", "자켓"),
        ("a photo of a cardigan", "가디건"),
        ("a photo of a puffer jacket", "패딩"),
        ("a photo of a blazer", "블레이저"),
        ("a photo of a trench coat", "트렌치코트"),
        ("a photo of a denim jacket", "데님자켓"),
    ],
    "원피스": [
        ("a photo of a mini dress", "미니드레스"),
        ("a photo of a midi dress", "미디드레스"),
        ("a photo of a maxi dress", "맥시드레스"),
        ("a photo of a shirt dress", "셔츠원피스"),
        ("a photo of a knit dress", "니트원피스"),
    ],
    "신발": [
        ("a photo of sneakers", "스니커즈"),
        ("a photo of dress shoes", "구두"),
        ("a photo of loafers", "로퍼"),
        ("a photo of boots", "부츠"),
        ("a photo of sandals", "샌들"),
        ("a photo of heels", "힐"),
    ],
    "가방": [
        ("a photo of a backpack", "백팩"),
        ("a photo of a tote bag", "토트백"),
        ("a photo of a crossbody bag", "크로스백"),
        ("a photo of a clutch", "클러치"),
        ("a photo of a shoulder bag", "숄더백"),
    ],
    "모자": [
        ("a photo of a baseball cap", "볼캡"),
        ("a photo of a bucket hat", "버킷햇"),
        ("a photo of a beanie", "비니"),
    ],
}


def crop_item(image, item):
    """정규화된 bbox(0~1)를 원본 이미지 픽셀 크기로 환산해서 그 영역만 잘라냄"""
    image_width, image_height = image.size
    x_min = item["bbox_x"] * image_width
    y_min = item["bbox_y"] * image_height
    x_max = x_min + item["bbox_width"] * image_width
    y_max = y_min + item["bbox_height"] * image_height
    return image.crop((x_min, y_min, x_max, y_max))


def label_item(image, item):
    """탐지된 아이템 하나를 크롭해서 FashionCLIP으로 세부 라벨을 붙임"""
    candidates = LABEL_CANDIDATES.get(item["category"], [])  # 이 카테고리의 후보 목록 꺼내기
    if not candidates:
        return ""  # 후보 목록에 없는 카테고리면 라벨 없이 넘어감

    cropped = crop_item(image, item)  # 박스 영역만 잘라낸 이미지
    texts = [text for text, _ in candidates]  # 영어 후보 텍스트만 리스트로 추출

    inputs = labeling_processor(text=texts, images=cropped, return_tensors="pt", padding=True)

    with torch.no_grad():
        outputs = labeling_model(**inputs)

    probs = outputs.logits_per_image.softmax(dim=1)  # 후보들 각각에 대한 확률로 변환
    best_index = probs.argmax().item()  # 확률이 가장 높은 후보의 인덱스

    return candidates[best_index][1]  # 그 인덱스의 한글 라벨 반환


def label_items(image, items):
    """detect_items()가 만든 리스트 각각에 label 필드를 채워서 돌려줌"""
    for item in items:
        item["label"] = label_item(image, item)
    return items
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
```

---

## 4. 복습 (오늘 새로 익힌 개념)

### Hugging Face `Auto*` 클래스의 역할
`AutoImageProcessor`, `AutoModelForObjectDetection`처럼 앞에 `Auto`가 붙은 클래스는, 모델 저장소의 설정 파일을 읽어서 **그 모델에 맞는 구체적인 클래스를 자동으로 골라 불러와준다.** 모델마다 세부 구조가 달라도, 우리는 "어떤 클래스를 써야 하는지" 직접 알 필요 없이 이름만 주면 된다.

### `with torch.no_grad():`의 의미
PyTorch는 기본적으로 모든 계산에서 "나중에 거꾸로 되짚어 학습에 반영할 준비"(기울기 추적)를 해둔다. 순수하게 **예측만 할 때**는 이 준비가 필요 없어서, `no_grad()` 블록으로 꺼주면 속도가 빨라지고 메모리도 아낀다.

### `.eval()` 모드가 필요한 이유
학습 중에만 쓰이는 일부 레이어(dropout 등, 일부러 랜덤하게 일부를 꺼서 과적합을 막는 기법)가, `.eval()`을 안 하면 추론 때도 계속 랜덤하게 동작해서 **같은 입력을 넣어도 실행할 때마다 결과가 미묘하게 달라질 수 있다.** `.eval()`로 이런 랜덤 요소를 끄고 "항상 같은 방식으로 예측하도록" 고정한다.

### `post_process_object_detection`과 `softmax`
- 탐지 모델의 날것 출력은 사람이 바로 읽을 수 없는 형태라, `post_process_object_detection`이 "확신도 기준으로 거르고 좌표를 원본 이미지 크기에 맞게 변환"하는 정리 작업을 대신 해준다.
- `softmax`는 모델이 내놓는 점수들을 **합이 100%가 되는 확률 분포**로 바꿔주는 표준 수학 함수 — FashionCLIP이 여러 후보 중 "이게 몇 % 확률로 맞다"를 비교할 수 있게 해준다.

### 백본(backbone)이라는 개념과 `timm`
딥러닝 비전 모델은 보통 "기본 특징을 뽑는 밑단 구조(백본)" + "그 위에서 특정 작업을 하는 전용 레이어"로 나뉜다. `transformers`는 유명한 백본(ResNet 등)을 직접 재구현하지 않고 `timm`이라는 전문 라이브러리의 구현체를 가져다 쓰는 식으로 설계돼 있다 — 그래서 모델에 따라 `timm`이 추가로 필요할 수 있다는 걸 이번에 실제로 겪으며 알게 됐다.

---

## 5. 트러블슈팅

### 1) 서버 기동 시 `ImportError: TimmBackbone requires the timm library`
- **증상**: `cv_service` 서버를 처음 실행하자마자, 모델 로딩 단계(`ml_models.py`의 `AutoModelForObjectDetection.from_pretrained(...)`)에서 서버 자체가 기동 실패
- **원인**: 탐지 모델(`conditional-detr-resnet-50`)의 백본인 ResNet-50을, `transformers`가 자체 구현이 아니라 **`timm` 라이브러리의 구현체를 가져다 쓰는 방식**으로 로딩하는데, `timm`이 설치돼 있지 않았음
- **해결**: `cv_service/pyproject.toml`에 `timm>=1.0.0` 추가 후 `uv sync` 재실행 → 정상 기동. 처음부터 예측하기 어려운 간접 의존성이라, "에러로 드러나면 그때 추가한다"는 방식이 합리적이었던 사례.

### 결과 검증
실제 사진(검은 블레이저 + 흰 티셔츠 + 청바지 + 구두 착장)으로 테스트한 결과:
- 큰 카테고리(아우터/하의/신발) + bbox 위치: 전부 정확
- 세부 라벨: 7~8할 정확, 다만 흰 반팔 티셔츠가 "셔츠"로 분류된 경우 1건 — zero-shot 분류의 한계로, 에러는 아니고 향후 후보 텍스트 문구 튜닝 대상으로 기록만 해둠 (지금 당장 수정하지 않기로 결정)
