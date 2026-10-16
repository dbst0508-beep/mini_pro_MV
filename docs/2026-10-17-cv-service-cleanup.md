# cv_service 정리 (비율 합 100 보정, 로깅, /analyze 테스트) — 2026-10-17

## 1. 기술문서

### 한 줄 요약
`cv_service`의 작은 빈틈 세 가지를 정리했습니다. ① 스타일 비율 합이 99.9가 되던 문제 수정, ② `print`를 `logging`으로 교체하고 서버 로그 설정 추가, ③ `/analyze`가 부품들을 올바르게 연결하는지 확인하는 테스트 추가.

### 왜 필요했나
| 항목 | 문제 |
|---|---|
| 비율 합 | 스타일마다 따로 반올림해서, 같은 비율 3개면 33.3 × 3 = **99.9**가 됨 |
| `print` | 시각, 중요도 구분이 없어 배포 후 "언제, 얼마나 심각한 실패였는지" 추적이 어려움. 이 한 줄이 Gemini 실패 원인을 알려 주는 유일한 단서 |
| `/analyze` 테스트 | 부품(비율 정리, 라벨 적용 등)은 각각 테스트했지만, 부품을 **순서대로 연결**하는 `/analyze`는 확인한 적이 없었음 |

### 무엇을 바꿨나
| 파일 | 변경 |
|---|---|
| `cv_service/app/interpretation.py` | `normalize_scores`가 마지막 스타일에 "100 − 나머지 합"을 채움, `print` → `logger.warning` |
| `cv_service/app/main.py` | `logging.basicConfig`로 서버 로그 형식 설정 |
| `cv_service/tests/test_interpretation.py` | 합 100 테스트 1개 추가, 실패 로그 확인(`assertLogs`) |
| `cv_service/tests/test_main.py` (새 파일) | `/analyze` 전체 흐름 테스트 5개 |

### `/analyze` 테스트가 확인하는 것
| 테스트 | 확인하는 것 |
|---|---|
| 정상 흐름 | 탐지·라벨·비율·해석이 콜백 데이터에 담기고, 받은 주소와 토큰으로 보내는지 |
| 검색 링크 | 라벨이 쇼핑 검색 링크로 바뀌어 담기는지 (한글은 URL용으로 변환) |
| 빈 라벨 | 라벨이 비면 `search_url`도 빈 문자열인지 |
| 중복 합치기 | 왼발/오른발 신발 같은 중복이 하나로 합쳐진 채 전송되는지 |
| 콜백 실패 | 전송이 실패하면 500을 돌려주는지 (Django의 Celery가 실패로 기록하는 근거) |

탐지가 옷을 잘 찾는지, Gemini 해석이 좋은지는 **확인하지 않습니다.** 무거운 부품 4개(`detect_items`, `label_items`, `interpret_style`, `send_callback`)를 가짜로 바꿔 놓고 "연결"만 봅니다.

### 실행 방법
```bash
cd cv_service
uv run --env-file .env python -m unittest -v
```
- 기대 결과: `Ran 23 tests` / `OK` (`test_interpretation` 13 + `test_labeling` 5 + `test_main` 5)
- `app.main`을 불러오면 CV 모델 2개가 같이 로드되므로 첫 실행은 몇 초 걸립니다.

### 직접 확인한 결과 (진짜 모델 + 진짜 Gemini)
| 항목 | 결과 |
|---|---|
| 스타일 비율 | 시크 50 + 스트릿 30 + 캐주얼 20 = 100% |
| 탐지 박스 | 모자, 상의, 아우터, 하의, 가방에 그려짐 |
| 해석 글 | 대체 문구가 아닌 실제 Gemini 해석이 나옴 |
| 신발 | **탐지 못 함.** Gemini 해석 글에는 "워커 부츠"가 언급되는데 탐지 목록에는 신발이 없음 → 탐지 기준값(`CONFIDENCE_THRESHOLD = 0.5`) 조정이 필요한 근거 |

---

## 2. 클래스·함수 단위 코드리뷰

### `normalize_scores` — 마지막 하나가 남은 값을 가져간다
각 비율을 따로 반올림하면 오차가 쌓입니다.

| 스타일 | 반올림 전 | 따로 반올림 | 수정 후 |
|---|---|---|---|
| 캐주얼 | 33.333… | 33.3 | 33.3 |
| 미니멀 | 33.333… | 33.3 | 33.3 |
| 스트릿 | 33.333… | 33.3 | **33.4** (100 − 66.6) |
| 합 | 100 | 99.9 | **100.0** |

마지막 스타일만 `100.0 - sum(ratios)`로 구합니다. 스타일이 1개면 `names[:-1]`이 빈 리스트라 `100.0 - 0 = 100.0`이 되어 기존 동작과 같습니다. `100`이 아니라 `100.0`으로 쓴 이유는 `sum([])`이 정수 `0`이라, 정수로 쓰면 결과 타입이 정수가 될 수 있기 때문입니다.

### `logger = logging.getLogger(__name__)`
`__name__`은 파이썬이 파일 이름으로 채워 주는 값입니다. 이 파일에서는 `"app.interpretation"`이 되어 로그에 어디서 난 로그인지 남습니다. 테스트의 `assertLogs("app.interpretation", ...)`도 이 이름으로 로그를 찾습니다.

### `logger.warning("LLM 호출 실패: %s", error)`
- **경고(warning)인 이유:** Gemini가 실패해도 탐지 결과는 살려서 돌려주므로 서비스가 멈춘 것이 아니라 "일부 기능이 빠진 것"입니다.
- **`%s`로 값을 따로 넘기는 이유:** f-string은 로그를 안 찍어도 글자를 만들지만, 이 방식은 로그가 실제로 출력될 때만 만듭니다. 로깅의 관례입니다.

### `logging.basicConfig(...)` (`main.py`)
로깅은 `logger`를 만드는 것만으로는 부족하고, **어떤 모양으로 출력할지 서버 시작 시 한 번 설정**해야 합니다.

| 설정 | 의미 |
|---|---|
| `level=logging.INFO` | 정보 단계 이상(정보/경고/에러)을 기록 |
| `format="%(asctime)s %(levelname)s %(name)s: %(message)s"` | `시각 단계 파일이름: 내용` 한 줄 모양 |

결과: `2026-10-17 09:12:03,412 WARNING app.interpretation: LLM 호출 실패: 503 서버 혼잡`

### `AnalyzeEndpointTests.setUp` — 가짜 부품 4개를 한곳에서 준비
- `patch("app.main.detect_items")`처럼 **"쓰는 곳"의 이름**(`app.main`)을 바꿉니다. `main.py`가 `from .detection import detect_items`로 자기 파일 안에 가져와 쓰기 때문에, 원본(`app.detection`)을 바꿔도 `main.py`에는 적용되지 않습니다.
- `self.addCleanup(patcher.stop)`: 테스트가 끝나면 가짜를 원래대로 되돌립니다.
- `TestClient(app, raise_server_exceptions=False)`: 서버 안에서 에러가 나면 테스트가 그 에러로 터지지 않고 **500 응답으로** 돌려줍니다. 실제 서버와 같은 모습입니다.
- `call_args.args`: 가짜가 "어떤 값으로 불렸는지" 기록한 것. `send_callback(url, payload)`로 불렸으니 `(url, payload)`로 꺼냅니다.

### `assertLogs` — 로그 붙잡기
`with self.assertLogs("app.interpretation", level="WARNING") as logs:` 블록 안에서 나온 경고 로그를 화면에 찍지 않고 `logs.output`에 모아 둡니다.
- `test_failure_returns_fallback...`: `assertIn("503 서버 혼잡", logs.output[0])`로 **실패 원인이 로그에 실제로 남는지** 확인합니다. 누군가 로그 줄을 실수로 지우면 이 테스트가 실패합니다.
- `test_broken_answer...`, `test_call_uses_timeout`: 붙잡기만 합니다. 테스트 출력을 깨끗하게 하는 용도이며 필수는 아닙니다.

---

## 3. 코드 한 줄 한 줄 주석

### `cv_service/app/interpretation.py` — 로거 만들기
```python
import logging  # print 대신 쓰는 파이썬 기본 기록 도구 (중요도 단계와 시각이 자동으로 붙음)

logger = logging.getLogger(__name__)  # 이 파일 전용 기록 담당자 (이름이 "app.interpretation"으로 붙어서 어느 파일의 로그인지 알 수 있음)
```

### `cv_service/app/interpretation.py` — `normalize_scores`의 끝부분
```python
    names = list(merged)  # 스타일 이름만 순서대로 꺼낸 리스트 (dict를 list로 바꾸면 키만 남음)
    ratios = [round(merged[name] / total * 100, 1) for name in names[:-1]]  # 마지막 하나를 뺀 나머지만 전체 대비 비율로 계산 + 반올림
    ratios.append(round(100.0 - sum(ratios), 1))  # 마지막 스타일은 "100 - 나머지 합"으로 채워서 합이 정확히 100이 되게 함
    return [
        {"style_name": name, "ratio": ratio}  # 이름과 비율을 한 묶음(dict)으로
        for name, ratio in zip(names, ratios)  # zip: 두 리스트를 같은 순서끼리 짝지어 하나씩 꺼냄
    ]
```

### `cv_service/app/interpretation.py` — `interpret_style`의 except 부분
```python
    except Exception as error:  # 한도 초과, 네트워크 오류, 이상한 응답 등 뭐가 터져도
        logger.warning("LLM 호출 실패: %s", error)  # 경고 단계로 기록 (분석은 계속되므로 에러가 아니라 경고)
        return [], FALLBACK_INTERPRETATION  # 탐지 결과는 살릴 수 있게 빈 값으로 돌려줌
```

### `cv_service/app/main.py` — 로깅 설정
```python
import logging  # 파이썬 기본 기록 도구


logging.basicConfig(  # 서버가 시작될 때 한 번만 하는 기록 설정 (이게 없으면 시각/단계/이름이 안 붙음)
    level=logging.INFO,  # 정보 단계 이상(정보/경고/에러)을 모두 기록
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",  # 한 줄 모양: 시각 / 단계 / 어느 파일인지 / 내용
)
```

### `cv_service/tests/test_main.py` (전체)
```python
import io  # 파일로 저장하지 않고 메모리 안에서 사진을 만들 때 씀
import unittest  # 파이썬 기본 테스트 도구
from unittest.mock import patch  # 진짜를 잠깐 가짜로 바꿔치기하는 도구
from urllib.parse import quote  # 기대하는 검색 링크를 만들 때 씀 (main.py가 쓰는 것과 같은 도구)

from fastapi.testclient import TestClient  # 서버를 띄우지 않고 가짜 요청을 보내 주는 도구
from PIL import Image  # 테스트용 작은 사진을 만들 때 씀

from app.main import app  # 테스트할 FastAPI 앱


def make_image_file():
    """업로드용 작은 사진 파일을 메모리에 만들어 주는 도우미"""
    buffer = io.BytesIO()  # 메모리 안의 빈 파일
    Image.new("RGB", (10, 10)).save(buffer, format="PNG")  # 10x10 검은 사진을 PNG로 저장
    buffer.seek(0)  # 파일 읽는 위치를 맨 앞으로 되돌림 (안 하면 빈 파일처럼 읽힘)
    return buffer


class AnalyzeEndpointTests(unittest.TestCase):  # /analyze 전체 흐름 테스트 모음
    def setUp(self):
        """테스트마다 먼저 실행됨: 무거운 부품 4개를 가짜로 바꿔 둔다"""
        self.client = TestClient(app, raise_server_exceptions=False)  # 서버 에러가 나면 테스트가 터지지 않고 500 응답으로 받음

        for name in ("detect_items", "label_items", "interpret_style", "send_callback"):  # 가짜로 바꿀 부품 이름 4개
            patcher = patch(f"app.main.{name}")  # main.py 안에서 쓰는 이름을 가짜로 바꿀 준비
            setattr(self, f"mock_{name}", patcher.start())  # 바꾸고, self.mock_detect_items 같은 이름으로 꺼내 쓸 수 있게 보관
            self.addCleanup(patcher.stop)  # 테스트가 끝나면 원래대로 되돌림

        self.mock_detect_items.return_value = [  # 가짜 탐지 결과: 상의 하나
            {"category": "상의", "bbox_x": 0.1, "bbox_y": 0.2, "bbox_width": 0.3, "bbox_height": 0.4},
        ]
        self.mock_label_items.return_value = [  # 가짜 라벨링 결과: 위 아이템에 라벨이 붙은 모양
            {"category": "상의", "label": "흰색 티셔츠", "bbox_x": 0.1, "bbox_y": 0.2, "bbox_width": 0.3, "bbox_height": 0.4},
        ]
        self.mock_interpret_style.return_value = (  # 가짜 Gemini 결과: (스타일 비율 리스트, 해석 글)
            [{"style_name": "캐주얼", "ratio": 60.0}, {"style_name": "미니멀", "ratio": 40.0}],
            "편안한 캐주얼 룩입니다.",
        )

    def post_analyze(self):
        """/analyze에 사진과 콜백 정보를 실어 보내는 도우미"""
        return self.client.post(
            "/analyze",
            files={"image": ("look.png", make_image_file(), "image/png")},  # 사진 파일
            data={"callback_url": "http://django/callback/", "callback_token": "secret-token"},  # 사진 말고 글자 값 2개
        )

    def test_success_sends_callback_with_everything(self):
        """정상 흐름: 탐지, 라벨, 비율, 해석이 모두 담긴 데이터를 콜백으로 보낸다"""
        response = self.post_analyze()  # 가짜 요청 보내기

        self.assertEqual(response.status_code, 200)  # 성공 응답
        self.assertEqual(response.json(), {"ok": True})  # 응답 내용도 약속대로

        self.mock_send_callback.assert_called_once()  # 콜백 전송 함수가 딱 한 번 불렸는지
        callback_url, payload = self.mock_send_callback.call_args.args  # 불릴 때 넘겨받은 값 2개를 꺼냄
        self.assertEqual(callback_url, "http://django/callback/")  # 받은 주소로 보냈는지
        self.assertEqual(payload.callback_token, "secret-token")  # 받은 토큰 그대로 실었는지
        self.assertEqual(payload.detected_items[0].label, "흰색 티셔츠")  # 라벨링 결과가 담겼는지
        self.assertEqual(payload.detected_items[0].bbox_x, 0.1)  # 박스 좌표도 그대로인지
        self.assertEqual([s.style_name for s in payload.style_scores], ["캐주얼", "미니멀"])  # 스타일 비율이 담겼는지
        self.assertEqual(payload.interpretation, "편안한 캐주얼 룩입니다.")  # 해석 글이 담겼는지

    def test_search_url_is_built_from_label(self):
        """라벨로 쇼핑 검색 링크를 만든다 (한글은 URL용으로 변환됨)"""
        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]  # 콜백으로 보낸 데이터
        expected = f"https://search.shopping.naver.com/search/all?query={quote('흰색 티셔츠')}"  # 기대하는 링크
        self.assertEqual(payload.detected_items[0].search_url, expected)

    def test_empty_label_gives_empty_search_url(self):
        """라벨이 비어 있으면 검색 링크도 빈 문자열이다"""
        self.mock_label_items.return_value[0]["label"] = ""  # 가짜 라벨링 결과의 라벨을 비움

        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]
        self.assertEqual(payload.detected_items[0].search_url, "")

    def test_duplicate_items_are_merged_before_sending(self):
        """같은 아이템(왼발/오른발 신발)은 하나로 합쳐서 보낸다"""
        shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.2, "bbox_y": 0.8, "bbox_width": 0.1, "bbox_height": 0.1}
        self.mock_label_items.return_value = [shoe, dict(shoe, bbox_x=0.6)]  # 위치만 다른 같은 신발 2개 (dict(shoe, ...)는 복사 후 일부만 바꿈)

        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]
        self.assertEqual(len(payload.detected_items), 1)  # 하나만 남았는지

    def test_callback_failure_returns_500(self):
        """콜백 전송이 실패하면 500을 돌려준다 (그래야 Django의 Celery가 실패로 기록함)"""
        self.mock_send_callback.side_effect = Exception("Django 저장 실패")  # 가짜에게 "부르면 에러를 내라"고 시킴

        response = self.post_analyze()

        self.assertEqual(response.status_code, 500)  # 에러 응답이 나는지
```

### `cv_service/tests/test_interpretation.py` — 추가·수정한 부분
```python
    def test_ratios_always_sum_to_100(self):
        """같은 비율 3개처럼 반올림 오차가 생겨도 합은 정확히 100이 된다"""
        scores = make_scores(("캐주얼", 1), ("미니멀", 1), ("스트릿", 1))  # 각각 33.333...%가 되는 입력

        result = normalize_scores(scores)  # 테스트할 함수 실행

        ratios = [score["ratio"] for score in result]  # 결과에서 비율 숫자만 꺼냄
        self.assertEqual(ratios, [33.3, 33.3, 33.4])  # 마지막 스타일이 남은 0.1을 가져감
        self.assertEqual(round(sum(ratios), 1), 100.0)  # 합이 100 (소수 계산의 아주 작은 오차는 반올림으로 무시)
```
```python
        with self.assertLogs("app.interpretation", level="WARNING") as logs:  # 이 블록 안에서 남은 경고 로그를 화면에 안 찍고 붙잡아 둠 (하나도 안 남으면 테스트 실패)
            style_scores, interpretation = interpret_style(self.image, items)  # 테스트할 함수 실행
        ...
        self.assertIn("503 서버 혼잡", logs.output[0])  # 붙잡은 첫 로그에 실패 원인이 담겨 있는지 확인
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 로깅은 "만들기"와 "설정"이 따로다
`logging.getLogger(__name__)`로 기록 담당자를 만드는 것과, `logging.basicConfig(...)`로 **출력 모양을 정하는 것**은 별개입니다. 설정이 없으면 파이썬은 "메시지만 찍는 기본 방식"으로 출력해서 시각, 단계, 이름이 붙지 않습니다.

### `print` vs `logging`
| | `print` | `logging` (설정 후) |
|---|---|---|
| 언제 났는지 | 모름 | 시각이 붙음 |
| 어느 파일에서 | 직접 글자로 써야 함 | 자동으로 붙음 |
| 얼마나 심각한지 | 구분 없음 | 정보 / 경고 / 에러 |
| 골라 보기 | 불가능 | "경고 이상만" 같은 필터 가능 |

배포하면 `print`는 서버의 출력창에 찍힙니다. 안 보이는 것이 문제가 아니라 **쓸 만한 정보가 없다**는 것이 문제입니다.

### `warning`과 `error`의 차이
Gemini가 실패해도 탐지 결과는 살려서 돌려주므로 "서비스가 멈춘 것"이 아니라 "일부가 빠진 것"입니다. 이럴 때는 `warning`이 맞습니다.

### 반올림 오차는 "마지막이 가져가기"로 해결
각각 반올림하면 합이 어긋납니다. 마지막 하나는 계산하지 않고 `100 − 나머지 합`으로 채우면 합이 항상 100입니다. 피자를 나눌 때 마지막 사람이 남은 조각을 다 가져가는 것과 같습니다.

### 컴퓨터의 소수 계산에는 아주 작은 오차가 있다
`0.1 + 0.2 = 0.30000000000000004`. 그래서 테스트에서 합을 비교할 때는 `round(sum(ratios), 1)`로 반올림한 뒤 비교했습니다.

### 연결 테스트 vs 부품 테스트
- **부품 테스트:** 함수 하나가 맞는지 (`normalize_scores` 등)
- **연결 테스트:** 부품들이 순서대로, 값을 제대로 넘기며 이어지는지 (`/analyze`)
- **실제 실행:** 진짜 모델과 진짜 Gemini로 돌려 보기 (이번에는 사진 한 장으로 직접 확인)

세 가지는 서로 다른 것을 확인해 주므로 하나가 있다고 다른 것이 필요 없어지지 않습니다.

### 가짜는 "쓰는 곳"의 이름을 바꾼다
`from .detection import detect_items`로 가져와 쓰는 코드는 `app.main.detect_items`라는 이름을 갖습니다. 원본(`app.detection.detect_items`)을 가짜로 바꿔도 `main.py`가 이미 들고 있는 이름은 그대로라서 적용되지 않습니다.

### `setUp`과 `addCleanup`
- `setUp`: 테스트 함수가 실행되기 **전마다** 자동 실행됩니다. 반복되는 준비를 한곳에 모읍니다.
- `addCleanup`: 테스트가 끝나면 실행할 뒷정리를 등록합니다. 가짜가 다른 테스트에 남지 않게 합니다.

### `raise_server_exceptions=False`
`TestClient`의 기본값은 서버 안 에러를 테스트로 그대로 던집니다. `False`로 하면 실제 서버처럼 500 응답으로 돌려주어 `status_code`를 확인할 수 있습니다.

### `python -m unittest`의 이름 규칙
현재 폴더 아래에서 **`test`로 시작하는 `.py` 파일**을 전부 찾아 실행합니다. 파일 이름을 `main_test.py`로 지으면 찾지 못합니다.

### "Address already in use"는 에러가 아니라 알림
Redis를 켰을 때 `bind: Address already in use`가 나오면 **이미 켜져 있다는 뜻**입니다. 새로 켤 필요가 없습니다. `redis-cli ping`에 `PONG`이 오면 정상입니다.

---

## 5. 트러블슈팅

### 1. 테스트가 `No API key was provided`로 시작도 못 함
- **증상:** `uv run python -m unittest ...` 실행 시 `ValueError: No API key was provided`
- **원인:** `interpretation.py`를 **불러오는 순간** `genai.Client()`가 API 키를 찾는데, 키가 든 `.env`를 읽지 않았음. 테스트에서는 Gemini를 가짜로 바꿔도 불러오는 단계에서 키 존재만 확인함
- **해결:** `uv run --env-file .env python -m unittest ...`

### 2. `No environment file found at: .env`
- **증상:** `--env-file .env`를 붙였는데 파일이 없다고 함
- **원인:** 실행 위치가 프로젝트 최상위(`mini_project1`)였음. `.env`는 `cv_service/` 안에 있음
- **해결:** `cd cv_service` 후 실행

### 3. 로깅을 바꿨는데 시각·단계가 안 붙음 (설명 오류 정정)
- **증상:** `print`를 `logger.warning`으로 바꿨는데 테스트 출력에 `LLM 호출 실패: ...`만 찍히고 `WARNING`, 시각, 이름이 없었음
- **원인:** 로깅 설정이 하나도 없으면 파이썬이 "메시지만 찍는 기본 방식"으로 대신 출력함. `logger`를 만드는 것만으로는 형식이 정해지지 않음
- **해결:** `main.py`에 `logging.basicConfig(...)` 추가. 서버에서 실제로 쓰이는 지점이 `main.py`이기 때문
- **교훈:** 로깅은 만들기와 설정이 따로다. 처음에 "바꾸면 자동으로 시각이 붙는다"고 설명한 것은 설정을 했을 때만 맞는 말이었음

### 4. 같은 로그가 일부 테스트에서 계속 화면에 찍힘
- **증상:** `assertLogs`를 한 테스트만 적용했더니 같은 경고를 내는 다른 두 테스트가 로그를 화면에 찍음
- **원인:** `assertLogs`는 `with` 블록 **안**에서 나온 로그만 붙잡음
- **해결:** 경고를 일으키는 테스트 3개 모두 `with self.assertLogs(...)`로 감쌈

### 5. 테스트 개수가 기대와 다름 (13개)
- **증상:** `test_interpretation`을 돌렸더니 14개가 아니라 13개
- **원인:** 이 파일에는 원래 12개가 있었음(나머지 5개는 `test_labeling.py`). 기대 개수를 잘못 안내한 것이었고 테스트는 정상
- **확인:** `grep -c "    def test"`로 파일 안의 테스트 수를 직접 세어 봄

### 6. `redis-server`가 `Address already in use`로 종료됨
- **원인:** Redis가 이미 켜져 있었음 (에러가 아니라 알림)
- **해결:** 새로 켜지 않고 `redis-cli ping` → `PONG` 확인 후 다음 서버 실행

### 결과 검증
```
Ran 23 tests in ...

OK
```

| 단계 | 누적 개수 |
|---|---|
| `test_interpretation.py` | 13 |
| `test_labeling.py` | 18 |
| `test_main.py` | 23 |

### 남은 과제
- 탐지 기준값(`CONFIDENCE_THRESHOLD = 0.5`) 조정: 직접 확인에서 신발(워커 부츠)을 탐지하지 못함
- 콜백 저장을 `transaction.atomic`으로 묶기 (아이템 일부만 저장되는 경우 방지)
- Django 쪽 `analysis/tasks.py`의 `print` 3개를 `logging`으로 교체 (Django 로깅 설정 포함)
- README의 `## 실행 방법` 제목 위치 정리
- 배포 방식 결정 및 배포용 설정
- (고도화) `Analysis`에 `user` FK 추가: 요청자 기록과 "내 분석 기록" 기능
- (고도화) 콜백을 완전한 비동기로: FastAPI `BackgroundTasks`, 실패 콜백
