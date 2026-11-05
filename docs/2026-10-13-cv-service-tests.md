# cv_service 테스트 작성 (Gemini 없이 Gemini 코드를 검증하기) — 2026-10-13

## 1. 기술문서

### 한 줄 요약
테스트가 하나도 없던 `cv_service`에 17개의 테스트를 추가했습니다. 인터넷, Gemini 사용량, 서버 실행 없이 돌아갑니다.

### 왜 필요했나
Django 쪽(`analysis`)은 테스트가 18개였지만 `cv_service`는 0개였습니다. 그런데 `cv_service`에는 **우리가 통제할 수 없는 Gemini의 답**을 받아 정리하는 코드가 있습니다. 이상한 답이 와도 망가지지 않는지는 손으로 확인하기 어렵습니다. Gemini가 일부러 이상한 답을 주게 만들 수 없기 때문입니다.

바로 앞 작업에서 "Gemini가 안 될 때 대체 문구로 끝난다"를 확인하려고 구글이 혼잡한 시간을 이용했는데, 테스트가 있으면 그런 때를 기다릴 필요가 없습니다.

### 무엇을 테스트했나
| 대상 | 파일 | 개수 | 확인하는 것 |
|---|---|---|---|
| `normalize_scores` | `interpretation.py` | 4 | 비율 합 100 맞추기, 같은 이름 합치기, 빈 값 버리기, 전부 버려질 때 빈 리스트 |
| `apply_labels` | `interpretation.py` | 4 | 번호에 맞게 라벨 붙이기, 없는 번호 무시, 빈 라벨 무시, 15자에서 자르기 |
| `interpret_style` | `interpretation.py` | 4 | 실패 시 대체 문구, 성공 시 결과 반영, 잘못된 모양의 답, 제한 시간 전달 |
| `merge_duplicates` | `labeling.py` | 5 | 같은 아이템 합치기, 라벨이 다르면 유지, 카테고리가 다르면 유지, 순서 유지, 빈 리스트 |

### 테스트하지 않은 것
| 대상 | 이유 |
|---|---|
| `detect_items`, `label_items` | 실제 모델을 돌려야 해서 느리고, 결과가 모델에 달려 있어 "정답"을 정하기 어려움 |
| `/analyze` 엔드포인트 | 탐지·라벨링·Gemini·콜백을 모두 가짜로 바꿔야 해서 이번 범위에서 제외 |
| `send_callback` | 한 줄짜리 요청 전달. Django 쪽 콜백 테스트가 받는 쪽을 확인하고 있음 |
| `build_prompt` | 문구가 바뀔 때마다 테스트도 고쳐야 해서 얻는 것이 적음 |

### 실행 방법
```bash
cd cv_service
uv run --env-file .env python -m unittest -v
```

- `python -m unittest`는 현재 폴더에서 `test`로 시작하는 파일을 찾아 실행합니다.
- `-v`는 테스트 이름을 하나씩 보여 줍니다.
- `--env-file .env`가 필요한 이유: `interpretation.py`를 불러오는 순간 `genai.Client()`가 API 키를 찾습니다. 실제 요청은 나가지 않습니다.
- 시작할 때 모델이 올라와 8초쯤 걸리지만 테스트 자체는 0.01초에 끝납니다.

### 폴더 구조
```
cv_service/
├── app/
│   ├── interpretation.py
│   └── labeling.py
└── tests/
    ├── __init__.py              # 빈 파일. 이 폴더를 파이썬 묶음으로 표시
    ├── test_interpretation.py   # 12개
    └── test_labeling.py         # 5개
```

---

## 2. 클래스·함수 단위 코드리뷰

### Django `TestCase` 대신 `unittest.TestCase`
`cv_service`에는 Django가 없어서 `manage.py test`를 쓸 수 없습니다. Django의 `TestCase`는 파이썬 기본 도구인 `unittest.TestCase`에 DB 초기화 같은 기능을 더한 것입니다. `cv_service` 테스트는 DB를 쓰지 않으므로 기본 도구로 충분합니다. `assertEqual` 같은 문법이 같아서 새로 배울 것이 거의 없고, 패키지를 추가로 설치하지 않아도 됩니다.

### `make_scores`, `make_items`, `make_detected_items` — 도우미 함수
테스트마다 같은 준비물을 반복해 적지 않으려고 만든 함수입니다. 값을 변수 하나로 만들어 여러 테스트가 같이 쓰지 않고, **부를 때마다 새로 만들게** 한 것이 중요합니다. `apply_labels`는 받은 리스트를 직접 고치는 함수라, 같은 리스트를 돌려 쓰면 앞 테스트가 바꾼 값이 뒤 테스트에 남습니다.

### `NormalizeScoresTests` — 계산 결과를 통째로 비교
결과 리스트 전체를 기대값과 `assertEqual`로 비교합니다. 개수만 세거나 일부만 보면 놓치는 것이 생기기 때문입니다. 마지막 테스트(`test_returns_empty_list_when_nothing_usable`)는 합계가 0일 때 0으로 나누는 에러가 나지 않는지 확인합니다.

**살펴볼 점:** 비율을 소수 첫째 자리로 반올림하기 때문에, 세 개로 나누면 합이 99.9나 100.1이 될 수 있습니다(예: 33.3 × 3). 이 경우는 테스트하지 않았습니다. Django 쪽 저장 조건이 합계를 엄격히 따진다면 문제가 될 수 있어 확인이 필요합니다.

### `ApplyLabelsTests` — 이상한 답에 대한 방어
네 테스트 중 세 개가 "Gemini가 이상하게 답했을 때"입니다.

- **없는 번호:** 번호 0이 오면 계산상 `리스트[-1]`이 되는데, 파이썬에서 이것은 에러가 아니라 **맨 마지막 아이템**입니다. 확인하지 않으면 조용히 엉뚱한 아이템의 라벨이 바뀝니다. 코드의 `0 <= index` 조건이 이를 막고, 테스트가 그 조건을 지킵니다.
- **빈 라벨:** 공백만 있는 라벨로 멀쩡한 FashionCLIP 라벨을 지우지 않는지 확인합니다.
- **긴 라벨:** 숫자 15를 직접 쓰지 않고 `MAX_LABEL_LENGTH`를 불러와 비교했습니다. 나중에 한도를 바꿔도 테스트를 고칠 필요가 없습니다.

### `InterpretStyleTests` — 가짜 Gemini
`@patch("app.interpretation.client")`를 클래스 위에 붙여, 이 클래스의 모든 테스트에서 Gemini 접속 객체를 가짜로 바꿨습니다. 가짜로 바꾸는 위치는 "만든 곳"이 아니라 **쓰는 곳**(`app.interpretation` 안의 `client`)입니다. 지난 Django 테스트에서 `analysis.tasks.requests.post`를 바꿨던 것과 같은 원칙입니다.

- **실패:** `side_effect = Exception(...)`으로 에러를 내게 하고, 대체 문구·빈 비율·원래 라벨 유지를 확인합니다. 바로 앞 작업에서 손으로 확인한 동작입니다.
- **성공:** 가짜가 돌려줄 답을 `json.dumps`로 만들어 `output_text`에 넣습니다. 답에 포함된 1번 라벨은 바뀌고, 포함되지 않은 2번은 그대로인지까지 봅니다.
- **잘못된 모양:** JSON이 아닌 글이 와도 에러로 죽지 않고 대체 경로로 가는지 확인합니다.
- **제한 시간 전달:** 가짜가 기억한 호출 기록(`call_args.kwargs`)에서 `timeout`을 꺼내 확인합니다. 앞 작업에서 넣은 `timeout=LLM_TIMEOUT` 줄을 누가 실수로 지우면 이 테스트가 알려 줍니다.

**살펴볼 점:** 재시도 횟수(`LLM_RETRY_ATTEMPTS`)는 테스트하지 못했습니다. 이 값은 `client`를 만들 때 들어가는데, 테스트에서는 그 `client`를 통째로 가짜로 바꾸기 때문입니다. 재시도 동작은 실제 라이브러리 안에서 일어나므로 가짜로는 확인할 수 없고, 시간을 재는 방식으로만 확인됩니다.

### `MergeDuplicatesTests` — 순서를 확인하는 이유
결과 화면에서 사진 위 박스 번호와 아이템 카드 번호는 아이템 순서로 매겨집니다. 중복을 빼다가 순서가 바뀌면 번호가 엉뚱한 옷을 가리킵니다. `test_order_is_preserved`가 이를 지킵니다.

**살펴볼 점:** 같은 카테고리·같은 라벨이면 실제로는 다른 옷이어도 합쳐집니다(예: 똑같은 이름이 붙은 겹쳐 입은 상의 두 벌). 지금 테스트는 이 동작을 "의도한 것"으로 확인하고 있습니다.

### 테스트 중 출력되는 `[interpret_style] LLM 호출 실패`
실패 테스트를 돌리면 코드의 `print`가 터미널에 찍힙니다. 테스트가 실패한 것이 아니라 정상입니다. 다만 결과 화면이 지저분해지므로, `print`를 정식 로깅으로 바꾸면 테스트 중에는 숨길 수 있습니다.

---

## 3. 코드 한 줄 한 줄 주석

### `cv_service/tests/test_interpretation.py` (전체)

```python
import json  # 파이썬 값을 JSON 글자로 바꾸는 도구 (가짜 Gemini 답을 만들 때 씀)
import unittest  # 파이썬 기본 테스트 도구 (Django TestCase의 바탕)
from unittest.mock import patch  # 진짜를 잠깐 가짜로 바꿔치기하는 도구

from PIL import Image  # 테스트용 작은 사진을 만들 때 씀

from app.interpretation import (  # 테스트할 대상 불러오기
    FALLBACK_INTERPRETATION,  # Gemini 실패 시 대신 보여 주는 문구
    LLM_TIMEOUT,  # Gemini 답을 기다리는 최대 시간 (30초)
    MAX_LABEL_LENGTH,  # 라벨 최대 글자 수 (15)
    ItemLabelResult,  # Gemini가 돌려주는 "번호 + 라벨" 한 묶음의 모양
    StyleScoreResult,  # Gemini가 돌려주는 "스타일 이름 + 비율" 한 묶음의 모양
    apply_labels,  # 라벨을 아이템에 붙이는 함수
    interpret_style,  # Gemini를 불러 해석을 받아 오는 함수
    normalize_scores,  # 스타일 비율을 정리하는 함수
)

def make_scores(*pairs):
    """(이름, 비율) 묶음들을 Gemini가 돌려준 것과 같은 모양의 객체 리스트로 바꿔 주는 도우미"""
    return [StyleScoreResult(style_name=name, ratio=ratio) for name, ratio in pairs]  # 묶음 하나당 객체 하나


class NormalizeScoresTests(unittest.TestCase):  # normalize_scores 함수 테스트 모음
    def test_ratios_are_scaled_to_100(self):
        """비율 합이 100이 아니어도 100이 되게 맞춘다"""
        scores = make_scores(("캐주얼", 30), ("미니멀", 30))  # 합이 60인 입력

        result = normalize_scores(scores)  # 테스트할 함수 실행

        self.assertEqual(  # 결과가 기대한 것과 똑같은지 확인
            result,
            [
                {"style_name": "캐주얼", "ratio": 50.0},  # 30/60 = 50%
                {"style_name": "미니멀", "ratio": 50.0},  # 30/60 = 50%
            ],
        )

    def test_duplicate_names_are_merged(self):
        """같은 이름이 두 번 나오면 하나로 합친다 (앞뒤 공백은 무시)"""
        scores = make_scores(("캐주얼", 40), (" 캐주얼 ", 20), ("미니멀", 40))  # 캐주얼이 두 번, 한 번은 공백 포함

        result = normalize_scores(scores)

        self.assertEqual(
            result,
            [
                {"style_name": "캐주얼", "ratio": 60.0},  # 40 + 20
                {"style_name": "미니멀", "ratio": 40.0},
            ],
        )

    def test_empty_name_and_zero_ratio_are_dropped(self):
        """이름이 비었거나 비율이 0 이하인 항목은 버린다"""
        scores = make_scores(("", 50), ("캐주얼", 0), ("미니멀", 50))  # 쓸 수 있는 건 미니멀 하나뿐

        result = normalize_scores(scores)

        self.assertEqual(result, [{"style_name": "미니멀", "ratio": 100.0}])  # 남은 하나가 100%

    def test_returns_empty_list_when_nothing_usable(self):
        """쓸 수 있는 항목이 하나도 없으면 빈 리스트를 돌려준다"""
        scores = make_scores(("", 50), ("캐주얼", 0))  # 전부 버려질 입력

        result = normalize_scores(scores)

        self.assertEqual(result, [])  # 0으로 나누다 에러 나지 않고 빈 리스트
def make_items():
    """탐지 결과처럼 생긴 아이템 2개를 새로 만들어 주는 도우미 (테스트마다 깨끗한 새것을 쓰려고 함수로 만듦)"""
    return [
        {"category": "상의", "label": "티셔츠"},  # 1번 아이템 (FashionCLIP이 붙여 둔 라벨이라고 가정)
        {"category": "하의", "label": "바지"},  # 2번 아이템
    ]


class ApplyLabelsTests(unittest.TestCase):  # apply_labels 함수 테스트 모음
    def test_label_is_applied_to_matching_number(self):
        """번호에 해당하는 아이템의 라벨을 Gemini 결과로 바꾼다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=2, label="와이드 청바지")])  # 2번에만 새 라벨

        self.assertEqual(items[0]["label"], "티셔츠")  # 1번은 그대로
        self.assertEqual(items[1]["label"], "와이드 청바지")  # 2번은 바뀜 (번호 2 → 리스트의 [1])

    def test_unknown_number_is_ignored(self):
        """없는 번호가 오면 무시한다 (에러 없이 넘어감)"""
        items = make_items()

        apply_labels(
            items,
            [
                ItemLabelResult(number=0, label="없는 번호"),  # 번호는 1부터라 0은 없음
                ItemLabelResult(number=99, label="없는 번호"),  # 아이템이 2개뿐이라 99도 없음
            ],
        )

        self.assertEqual(items, make_items())  # 아무것도 안 바뀜 (새로 만든 것과 똑같음)

    def test_blank_label_keeps_existing_label(self):
        """빈 라벨이 오면 원래 라벨을 지킨다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=1, label="   ")])  # 공백만 있는 라벨

        self.assertEqual(items[0]["label"], "티셔츠")  # 빈칸으로 덮어쓰지 않음

    def test_long_label_is_cut(self):
        """너무 긴 라벨은 최대 글자 수에서 자른다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=1, label="가" * 30)])  # "가"가 30개인 긴 라벨

        self.assertEqual(items[0]["label"], "가" * MAX_LABEL_LENGTH)  # 15글자만 남음

def make_detected_items():
    """위치 정보까지 들어 있는 탐지 결과 2개를 만들어 주는 도우미 (프롬프트를 만들 때 위치가 필요함)"""
    return [
        {"category": "상의", "label": "티셔츠", "bbox_x": 0.2, "bbox_y": 0.1, "bbox_width": 0.6, "bbox_height": 0.4},  # 1번
        {"category": "하의", "label": "바지", "bbox_x": 0.2, "bbox_y": 0.5, "bbox_width": 0.6, "bbox_height": 0.5},  # 2번
    ]


@patch("app.interpretation.client")  # 이 클래스의 모든 테스트에서 진짜 Gemini 접속 준비물을 가짜로 바꿈
class InterpretStyleTests(unittest.TestCase):  # interpret_style 함수 테스트 모음
    def setUp(self):
        self.image = Image.new("RGB", (10, 10))  # 가로세로 10픽셀짜리 검은 사진 (내용은 중요하지 않음)

    def test_failure_returns_fallback_and_keeps_labels(self, mock_client):
        """Gemini가 실패하면 대체 문구와 빈 비율을 돌려주고, 원래 라벨은 그대로 둔다"""
        mock_client.interactions.create.side_effect = Exception("503 서버 혼잡")  # 가짜에게 "부르면 에러를 내라"고 시킴
        items = make_detected_items()

        style_scores, interpretation = interpret_style(self.image, items)

        self.assertEqual(style_scores, [])  # 스타일 비율은 비어 있음
        self.assertEqual(interpretation, FALLBACK_INTERPRETATION)  # 해석 자리엔 대체 문구
        self.assertEqual(items[0]["label"], "티셔츠")  # FashionCLIP 라벨이 살아 있음

    def test_success_returns_scores_and_applies_labels(self, mock_client):
        """Gemini가 성공하면 정리된 비율과 해석을 돌려주고, 라벨을 Gemini 것으로 바꾼다"""
        answer = {  # Gemini가 돌려줄 답을 미리 만들어 둠
            "style_scores": [{"style_name": "캐주얼", "ratio": 60}, {"style_name": "미니멀", "ratio": 40}],
            "interpretation": "편안해 보이는 조합입니다.",
            "item_labels": [{"number": 1, "label": "흰색 반팔티"}],
        }
        mock_client.interactions.create.return_value.output_text = json.dumps(answer)  # 가짜에게 "이 답을 JSON 글자로 돌려줘라"고 시킴
        items = make_detected_items()

        style_scores, interpretation = interpret_style(self.image, items)

        self.assertEqual(
            style_scores,
            [{"style_name": "캐주얼", "ratio": 60.0}, {"style_name": "미니멀", "ratio": 40.0}],
        )
        self.assertEqual(interpretation, "편안해 보이는 조합입니다.")
        self.assertEqual(items[0]["label"], "흰색 반팔티")  # 1번 라벨이 Gemini 것으로 바뀜
        self.assertEqual(items[1]["label"], "바지")  # 답에 없던 2번은 그대로

    def test_broken_answer_returns_fallback(self, mock_client):
        """Gemini가 약속한 모양이 아닌 답을 주면 실패로 처리한다"""
        mock_client.interactions.create.return_value.output_text = "JSON이 아닌 그냥 글"  # 엉뚱한 답

        style_scores, interpretation = interpret_style(self.image, make_detected_items())

        self.assertEqual(style_scores, [])
        self.assertEqual(interpretation, FALLBACK_INTERPRETATION)

    def test_call_uses_timeout(self, mock_client):
        """Gemini를 부를 때 제한 시간을 함께 넘긴다 (오늘 고친 부분이 실수로 지워지지 않게 지킴)"""
        mock_client.interactions.create.side_effect = Exception("실패")  # 결과는 중요하지 않으니 바로 실패시킴

        interpret_style(self.image, make_detected_items())

        called_with = mock_client.interactions.create.call_args.kwargs  # 가짜가 "어떤 옵션으로 불렸는지" 기록해 둔 것
        self.assertEqual(called_with["timeout"], LLM_TIMEOUT)  # timeout=30으로 불렸는지 확인
```

### `cv_service/tests/test_labeling.py` (전체)

```python
import unittest  # 파이썬 기본 테스트 도구

from app.labeling import merge_duplicates  # 테스트할 함수 불러오기


class MergeDuplicatesTests(unittest.TestCase):  # merge_duplicates 함수 테스트 모음
    def test_same_category_and_label_are_merged(self):
        """카테고리와 라벨이 모두 같으면 첫 번째 것만 남긴다 (왼발/오른발 신발)"""
        left_shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.2}  # 왼발
        right_shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.6}  # 오른발 (위치만 다름)

        result = merge_duplicates([left_shoe, right_shoe])

        self.assertEqual(result, [left_shoe])  # 먼저 나온 왼발만 남음

    def test_different_label_is_kept(self):
        """카테고리가 같아도 라벨이 다르면 둘 다 남긴다"""
        items = [
            {"category": "상의", "label": "흰색 반팔티"},  # 안에 입은 옷
            {"category": "상의", "label": "검정 가디건"},  # 겉에 걸친 옷
        ]

        result = merge_duplicates(items)

        self.assertEqual(result, items)  # 서로 다른 옷이라 그대로

    def test_same_label_in_different_category_is_kept(self):
        """라벨이 같아도 카테고리가 다르면 둘 다 남긴다"""
        items = [
            {"category": "상의", "label": "데님"},
            {"category": "하의", "label": "데님"},
        ]

        result = merge_duplicates(items)

        self.assertEqual(result, items)

    def test_order_is_preserved(self):
        """중복을 빼도 남은 아이템의 순서는 그대로다"""
        items = [
            {"category": "상의", "label": "티셔츠"},
            {"category": "신발", "label": "스니커즈"},
            {"category": "하의", "label": "청바지"},
            {"category": "신발", "label": "스니커즈"},  # 두 번째 신발 (빠질 것)
        ]

        result = merge_duplicates(items)

        self.assertEqual(
            [item["category"] for item in result],  # 결과에서 카테고리만 뽑아 순서 확인
            ["상의", "신발", "하의"],
        )

    def test_empty_list(self):
        """아이템이 하나도 없으면 빈 리스트를 돌려준다"""
        self.assertEqual(merge_duplicates([]), [])
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### `unittest`와 Django `TestCase`의 관계
Django의 `TestCase`는 `unittest.TestCase`를 물려받아 기능을 더한 것입니다. 그래서 `assertEqual`, `setUp`, `test_`로 시작하는 함수 이름 같은 규칙이 똑같습니다. DB나 가짜 브라우저가 필요 없으면 기본 도구만으로 충분합니다.

### `__init__.py` — 빈 파일의 역할
내용이 없어도, 이 파일이 있어야 `python -m unittest`가 `tests` 폴더를 파이썬 묶음으로 인식해 그 안의 테스트를 찾습니다.

### "Ran 0 tests"는 에러가 아니라 "찾은 게 없음"
테스트 파일이 비어 있거나 저장이 안 됐을 때 나옵니다. 설정 문제로 보이지만 대부분 파일 내용 문제입니다.

### 순수 함수는 테스트하기 쉽다
`normalize_scores`나 `merge_duplicates`처럼 **값을 받아 값을 돌려주기만 하는 함수**는 준비물도 가짜도 필요 없습니다. 넣을 값과 기대하는 값만 적으면 됩니다. 반대로 `interpret_style`처럼 바깥(Gemini)과 얘기하는 함수는 가짜가 필요합니다. 복잡한 계산을 바깥과 얘기하는 코드에서 떼어 작은 함수로 만들어 두면 테스트가 쉬워집니다.

### 받은 값을 고치는 함수와 새 값을 돌려주는 함수
`apply_labels(items, ...)`는 받은 `items`를 **직접 고치고** 아무것도 돌려주지 않습니다. `merge_duplicates(items)`는 **새 리스트를 돌려줍니다.** 앞의 것은 함수를 부른 뒤 원래 변수를 확인하고, 뒤의 것은 돌려받은 값을 확인합니다. 테스트 방식이 달라지는 이유입니다.

### 파이썬의 음수 인덱스
`리스트[-1]`은 에러가 아니라 마지막 값입니다. 번호에서 1을 빼 위치를 구하는 코드는 0이나 음수가 들어올 때를 반드시 막아야 합니다.

### `@patch`를 클래스 위에 붙이기
함수 위에 붙이면 그 테스트 하나에만, 클래스 위에 붙이면 그 안의 모든 테스트에 적용됩니다. 이때 각 테스트 함수는 가짜를 받을 자리(`mock_client`)를 하나씩 가져야 합니다.

### 가짜에게 시키는 세 가지
| 쓰는 법 | 뜻 |
|---|---|
| `가짜.side_effect = Exception(...)` | 부르면 에러를 내라 |
| `가짜.return_value.속성 = 값` | 부르면 돌려줄 것의 속성을 이 값으로 해라 |
| `가짜.call_args.kwargs` | 네가 어떤 옵션으로 불렸는지 알려 줘라 |

### `json.dumps` — 가짜 답 만들기
파이썬 딕셔너리를 JSON 글자로 바꿉니다. 진짜 Gemini가 JSON 글자를 돌려주므로, 가짜도 같은 형태로 돌려주게 하려고 씁니다.

### 테스트는 "지금 맞다"보다 "나중에 깨지면 알려 준다"가 목적
`test_call_uses_timeout`은 지금 당연히 통과합니다. 값어치는 나중에 있습니다. 코드를 정리하다 `timeout` 줄을 지우면, 구글이 혼잡해질 때까지 아무도 모른 채 5분 실패가 돌아옵니다. 테스트가 있으면 지운 즉시 알 수 있습니다.

---

## 5. 트러블슈팅

이번 작업에서는 따로 기록할 만한 문제가 없었습니다. (테스트 파일을 저장하지 않아 "Ran 0 tests"가 나온 것은 바로 확인해 고쳤습니다.)

### 결과 검증
```
Ran 17 tests in 0.014s

OK
```

| 단계 | 누적 개수 |
|---|---|
| `normalize_scores` | 4 |
| `apply_labels` | 8 |
| `interpret_style` | 12 |
| `merge_duplicates` | 17 |

### 남은 과제
- 비율 반올림으로 합이 정확히 100이 안 되는 경우 확인 (예: 세 스타일이 같은 비율)
- `/analyze` 엔드포인트 테스트 (전체 흐름을 가짜로 묶어 확인)
- `print`를 로깅으로 교체해 테스트 출력 정리
- 앞 작업에서 남긴 확인: Gemini 혼잡이 풀린 뒤 정상 응답 확인
