# Django 쪽 로깅 정리 (print → logging, LOGGING 설정, 죽은 테스트 삭제) — 2026-10-19

## 1. 기술문서

### 한 줄 요약
Django 쪽 `analysis/tasks.py`에 남아 있던 `print` 3개를 `logging`으로 바꾸고, `settings.py`에 `LOGGING` 설정을 추가해 로그가 `시각 단계 파일이름: 내용` 모양으로 출력되게 했습니다. 또 이름이 겹쳐서 한 번도 실행되지 않던 테스트 1개를 삭제했습니다.

### 왜 필요했나
| 항목 | 문제 |
|---|---|
| `print` 3개 | 언제 났는지, 얼마나 심각한지 알 수 없고, 마지막 `print`는 에러 내용만 찍고 **어디서 났는지**는 남기지 않음 |
| 로그 설정 없음 | `logger`를 만들어도 모양을 정해 주지 않으면 파이썬이 "메시지만 찍는 기본 방식"으로 출력해서 시각, 단계, 이름이 안 붙음 |
| 같은 이름의 테스트 2개 | 파이썬은 같은 이름의 함수가 두 번 나오면 뒤쪽만 남김. 앞쪽 테스트는 **한 번도 실행되지 않는 죽은 코드**였음 |
| 실패 테스트의 화면 출력 | 일부러 실패를 일으키는 테스트가 에러 로그를 화면에 그대로 찍어서 진짜 에러처럼 보임 |

### 무엇을 바꿨나
| 파일 | 변경 |
|---|---|
| `analysis/tests.py` | 중복된 `test_error_response_marks_failed` 중 죽은 쪽 삭제 |
| `analysis/tasks.py` | `import logging`, `logger` 추가. `print` 3개 → `logger.error` 2개 + `logger.exception` 1개 |
| `analysis/tests.py` | 실패 테스트 3개를 `assertLogs`로 감싸고, 로그가 실제로 남는지 확인 |
| `config/settings.py` | `LOGGING` 추가: `analysis` 로거를 콘솔로 출력 |

### 로그가 나오는 모습 (실제 확인)
cv_service를 일부러 끄고 분석을 요청했을 때 Celery worker 터미널에 찍힌 로그입니다.
```
2026-10-19 23:29:28,276 ERROR analysis.tasks: 분석 #44 연결 실패: HTTPConnectionPool(host='localhost', port=8001): Max retries exceeded with url: /analyze (... Connection refused ...)
```
| 부분 | 의미 |
|---|---|
| `2026-10-19 23:29:28,276` | 언제 |
| `ERROR` | 얼마나 심각한지 |
| `analysis.tasks` | 어느 파일에서 (`analysis/tasks.py`) |
| `분석 #44 연결 실패: ...` | 무슨 일이 (44번 분석이 cv_service에 연결하지 못함) |
| `Connection refused` | 8001번 포트에서 받아 주는 서버가 없어 거부됨 (cv_service가 꺼져 있었음) |

### 실행 방법
```bash
uv run python manage.py test analysis
```
- 기대 결과: `Ran 19 tests` / `OK`, 그리고 화면에 로그나 Traceback이 **하나도 나오지 않음**
- 숫자가 19개 그대로인 이유: 삭제한 테스트는 원래 실행되지 않던 것이라 세어지지 않았기 때문입니다.

### 알려진 한계 (직전 문서 정정)
`docs/2026-10-19-callback-hardening.md`의 남은 과제에 "탐지 기준값 조정"이라고 적었으나 틀린 내용이라 정정했습니다.
- **작은 신발/부츠가 탐지되지 않습니다.** 기준값(`CONFIDENCE_THRESHOLD`)을 조정해도 해결되지 않습니다. 사진 한 장(워커 부츠를 놓친 사진)으로 진단한 결과가 근거입니다.
  - 신발 후보의 점수가 최대 0.24로 낮고 노이즈와 섞여 있음
  - 점수가 낮은 후보들(가방 0.35, 신발 0.24, 모자 0.22, 아우터 0.21)이 **같은 크기의 박스(6.4%)**였음 → 탐지 모델이 "그 박스가 무엇인지" 자신 없어 한다는 뜻
  - 기준값을 0.2 정도로 낮추면 박스 4개가 겹쳐서 나오고, `merge_duplicates`는 **카테고리와 라벨이 같은 것만** 합치므로 해결되지 않음
  - Gemini의 해석 글에는 부츠가 언급됨 → **박스만 없는** 상태
- 근본 해결(모두 무거워서 고도화 단계로 보류): 사진 하단을 확대해 다시 탐지, 더 큰 탐지 모델 사용(메모리·배포 비용), Gemini가 박스를 직접 출력

---

## 2. 클래스·함수 단위 코드리뷰

### `run_analysis` — 예외 3개를 심각도에 맞게 나눠 기록
| 예외 | 로그 | 이유 |
|---|---|---|
| `ConnectionError` (서버 꺼짐) | `logger.error` | 원인이 뻔해서 한 줄이면 충분 |
| `Timeout` (응답 없음) | `logger.error` | 마찬가지로 원인이 뻔함 |
| 그 밖의 `Exception` | `logger.exception` | 원인을 알 수 없는 문제는 **어디서 났는지(traceback)**가 핵심이라 위치까지 기록 |

마지막 `except`에서 `as error`를 뺐습니다. `logger.exception`이 지금 처리 중인 에러를 알아서 기록하므로 변수가 필요 없어졌습니다.

세 경우 모두 `mark_failed`는 그대로 호출합니다. **로그는 개발자용, `mark_failed`는 사용자 화면용**으로 역할이 다릅니다.

### 로그 형식: `logger.error("... %s", 값)`
값을 문자열에 바로 끼워 넣지 않고(`f"..."`) 뒤에 따로 넘깁니다. f-string은 로그를 찍든 말든 글자를 만들지만, 이 방식은 **로그가 실제로 출력될 때만** 만듭니다. 로깅의 관례이고 cv_service에서도 같은 방식을 썼습니다.

### `LOGGING` 설정 — 네 가지 부품
| 부품 | 역할 | 비유 |
|---|---|---|
| `formatters` | 출력 모양 | 영수증 서식 |
| `handlers` | 어디로 내보낼지 (여기서는 터미널) | 프린터 |
| `loggers` | 누가 기록하고 어떤 출구를 쓸지 | 담당자 + 프린터 지정 |
| `propagate: False` | 위로 다시 넘기지 않음 | 복사본을 본사에 또 보내지 않음 |

- `"analysis"` 로거 **하나로** `analysis.views`와 `analysis.tasks`가 모두 적용됩니다. 로거 이름은 점(`.`)으로 계층이 되어서 부모에 설정하면 자식이 따라옵니다.
- `disable_existing_loggers: False`: 이미 만들어진 다른 로거(Django 자체 로그 등)를 끄지 않습니다. `True`로 두면 기존 로그가 사라질 수 있습니다.
- 루트 로거가 아닌 `analysis`에만 연결한 이유: 루트에 붙이면 Django 자체 로그까지 같은 출구로 두 번 찍힐 수 있습니다. 우리가 정한 모양은 우리 앱의 로그에만 적용합니다.

### 추가한 테스트 3개의 공통 구조
```
with self.assertLogs("analysis.tasks", level="ERROR") as logs:
    run_analysis(...)                    # 실패를 일으키는 호출은 반드시 블록 안에
... (상태·안내 문구 확인) ...
self.assertIn("연결 실패", logs.output[0])  # 로그가 실제로 남았는지
```
- 로그를 붙잡는 이름 `"analysis.tasks"`는 `tasks.py`의 `logger` 이름(`__name__`)과 **같아야** 합니다. 다르면 로그를 못 찾아 테스트가 실패합니다.
- `logs.output[0]`에는 메시지만 있고 traceback은 없습니다. 그래서 `"오류"`처럼 메시지의 일부로 확인합니다.
- 누군가 로그 줄을 실수로 지우면 이 테스트가 실패합니다. "실패 원인이 로그에 남는다"는 약속을 지켜 주는 장치입니다.

### 삭제한 테스트
| | 앞쪽 (삭제) | 뒤쪽 (유지) |
|---|---|---|
| 가짜 예외 | `ConnectionError("서버 꺼짐")` | `HTTPError("500")` |
| 확인 | "연결할 수 없습니다" 문구 | "오류가 발생" 문구 |
| 상태 | 실행된 적 없음 | 실행됨 |

앞쪽이 확인하려던 내용은 바로 위의 `test_connection_error_marks_failed`가 이미 검증합니다. 그래서 삭제로 사라지는 검증은 없습니다.

---

## 3. 코드 한 줄 한 줄 주석

### `analysis/tasks.py` — 로거 만들기
```python
import logging                                              # print 대신 쓰는 기록 도구 (시각과 심각도가 붙음)

logger = logging.getLogger(__name__)  # 이 파일 전용 기록 담당자 (이름은 "analysis.tasks"가 됨)
```

### `analysis/tasks.py` — `run_analysis`의 `except` 3개
```python
    except requests.exceptions.ConnectionError as error:                  # 서버가 꺼져 있어 연결 자체가 안 될 때
        logger.error("분석 #%s 연결 실패: %s", analysis_id, error)          # 에러 단계로 기록: %s 자리에 뒤의 값들이 순서대로 들어감
        mark_failed(analysis_id, "분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    except requests.exceptions.Timeout as error:                           # 제한 시간 안에 답이 안 올 때
        logger.error("분석 #%s 시간 초과: %s", analysis_id, error)          # 이것도 원인이 뻔하므로 에러 단계 + 한 줄이면 충분함
        mark_failed(analysis_id, "분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
    except Exception:                                                       # 그 밖의 모든 문제 (서버 에러 응답, 이미지 파일 없음 등)
        logger.exception("분석 #%s 오류", analysis_id)                       # 에러 내용과 발생 위치(traceback)까지 자동으로 같이 기록함
        mark_failed(analysis_id, "분석 중 오류가 발생했습니다. 다른 사진으로 다시 시도해 주세요.")
```

### `config/settings.py` — `LOGGING`
```python
# 로그 설정: analysis 앱의 로그(logger.error 등)를 "시각 단계 파일이름: 내용" 모양으로 터미널에 출력
LOGGING = {
    "version": 1,                                         # 설정 형식의 버전 (지금은 항상 1로 적는 것이 약속)
    "disable_existing_loggers": False,                    # 이미 만들어진 다른 로거(Django 자체 로그 등)를 끄지 않음 (True면 기존 로그가 사라질 수 있음)
    "formatters": {                                       # 출력 모양 정의
        "basic": {                                          # 이 모양의 이름: "basic"
            "format": "%(asctime)s %(levelname)s %(name)s: %(message)s",  # 한 줄 모양: 시각 / 단계 / 어느 파일인지 / 내용 (cv_service와 같은 형식)
        },
    },
    "handlers": {                                         # 로그를 어디로 내보낼지 정의
        "console": {                                        # 이 출구의 이름: "console"
            "class": "logging.StreamHandler",                 # 터미널 화면으로 출력하는 파이썬 기본 도구
            "formatter": "basic",                             # 위에서 정의한 "basic" 모양으로 출력
        },
    },
    "loggers": {                                          # 어느 로거에 어떤 출구를 연결할지 정의
        "analysis": {                                       # "analysis"로 시작하는 로거 전부 (analysis.views, analysis.tasks)
            "handlers": ["console"],                          # 위의 "console" 출구에 연결
            "level": "INFO",                                  # 정보 단계 이상(정보/경고/에러)을 출력
            "propagate": False,                               # 상위(루트) 로거로 다시 넘기지 않음: 같은 로그가 두 번 찍히는 것을 막음
        },
    },
}
```

### `analysis/tests.py` — 수정한 `RunAnalysisTests`의 실패 테스트 3개
```python
    def test_connection_error_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("서버 꺼짐")  # 가짜가 불리면 "연결 실패" 예외를 일으키게 설정
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 이 블록 안에서 남은 에러 로그를 화면에 안 찍고 붙잡아 둠 (하나도 안 남으면 테스트 실패)
            run_analysis(self.analysis.id)  # 테스트할 task 실행

        self.analysis.refresh_from_db()  # task가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # 분석이 "실패"로 바뀌었는지
        self.assertIn("연결할 수 없습니다", self.analysis.error_message)  # 연결 실패용 문구여야 함
        self.assertIn("연결 실패", logs.output[0])  # 붙잡은 첫 로그에 "연결 실패"가 있는지 (로그가 실제로 남았는지 확인)

    def test_timeout_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("응답 없음")  # "시간 초과" 예외를 일으키게 설정
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 에러 로그를 붙잡아 둠
            run_analysis(self.analysis.id)

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)
        self.assertIn("시간이 초과", self.analysis.error_message)  # 시간 초과용 문구여야 함
        self.assertIn("시간 초과", logs.output[0])  # 로그에도 "시간 초과"가 남았는지

    def test_error_response_marks_failed(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500")  # 응답은 왔지만 에러 응답인 상황
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 에러 로그를 붙잡아 둠 (traceback이 화면에 쏟아지는 것도 막아 줌)
            run_analysis(self.analysis.id)

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)
        self.assertIn("오류가 발생", self.analysis.error_message)  # 그 밖의 오류용 문구여야 함
        self.assertIn("오류", logs.output[0])  # 로그에도 "오류"가 남았는지
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 로깅 설정의 네 부품: 모양, 출구, 담당자, 연결
로거(`logger`)를 만드는 것은 "기록할 사람"을 정하는 것뿐입니다. 어떤 **모양**(formatter)으로 어느 **출구**(handler)에 내보낼지는 별도로 설정해야 합니다. cv_service에서는 `basicConfig` 한 줄로 했고, Django에서는 `LOGGING`이라는 딕셔너리에 적는 것이 관례입니다.

### 로거 이름은 계층이다
`analysis.views`와 `analysis.tasks`는 점(`.`) 때문에 `analysis`의 자식입니다. 부모에게 설정하면 자식에게 적용됩니다. 파일마다 `getLogger(__name__)`을 쓰는 이유가 이것입니다. 이름이 자동으로 위치 정보가 되고, 계층으로 한꺼번에 설정할 수 있습니다.

### `error`와 `exception`의 차이
- `logger.error`: 메시지만 기록. 원인이 뻔할 때
- `logger.exception`: 메시지 + 에러 내용 + **발생 위치(traceback)**. `except` 안에서만 쓸 수 있고, 원인을 모를 때

### 같은 이름의 함수는 뒤가 앞을 덮는다
클래스 안에서 같은 이름의 함수를 두 번 정의하면 앞의 것은 사라집니다. 에러도 경고도 없이 조용히 사라지는 점이 위험합니다. 테스트가 "통과"하는 것과 "테스트가 실행되는 것"은 다릅니다. 테스트 개수(`Ran N tests`)가 기대와 맞는지 가끔 확인하세요.

### "실패한 task"와 "task가 처리한 실패"는 다르다
worker 로그 끝에 `Task ... succeeded ... None`이 나왔습니다. 이상한 게 아닙니다. `run_analysis`가 에러를 `except`로 잡아 `mark_failed`로 분석을 `실패`로 바꾸고 정상 종료했기 때문입니다. Celery 입장에서는 task가 에러 없이 끝났지만, **분석의 성공/실패는 `Analysis.status`에 기록**됩니다. 두 가지를 구분해서 봐야 합니다.

### "Connection refused"는 "끊김"이 아니라 "처음부터 안 됨"
서버가 켜져 있다가 도중에 끊긴 것이 아니라, 그 포트에서 **받아 주는 프로그램이 없어서** 연결 자체가 거부된 것입니다. 이 메시지가 보이면 먼저 "상대 서버가 켜져 있는지"를 확인합니다.

### 로그와 DB 기록은 용도가 다르다
- 로그: 일어난 일 전체를 개발자가 보는 기록 (시각, 원인, traceback)
- DB(`Analysis.status`, `error_message`): 서비스가 사용자에게 보여 주기 위한 상태

오류 전용 DB 테이블은 지금 만들지 않기로 했습니다. 필요해지면 새 테이블보다 `Analysis`에 `error_detail` 필드 하나를 추가하는 것이 가볍습니다(관리자 페이지에서 한 행으로 볼 수 있음). 오류를 모아 알림받는 용도라면 Sentry 같은 서비스를 씁니다. 배포 방식을 정할 때 함께 결정합니다.

---

## 5. 트러블슈팅

### 1. 같은 이름의 테스트 2개 중 하나가 한 번도 실행되지 않고 있었음
- **발견:** 로깅 작업을 하려고 `RunAnalysisTests`를 읽다가 `test_error_response_marks_failed`가 두 번 정의된 것을 발견
- **원인:** 파이썬은 같은 이름이면 뒤쪽 정의로 덮어씀. 앞쪽(`ConnectionError("서버 꺼짐")`을 쓰는 것)은 코드만 있고 실행된 적이 없음. 에러도 경고도 없고 `Ran 19 tests`에도 세어지지 않아 눈에 띄지 않았음
- **해결:** 앞쪽 삭제. 같은 내용은 `test_connection_error_marks_failed`가 이미 검증하고 있어 검증 범위는 줄지 않음
- **확인:** 삭제 전후 모두 `Ran 19 tests` / `OK`

### 2. `print`를 `logging`으로 바꿨는데 `ERROR`와 시각이 안 붙어 나옴
- **증상:** 테스트 출력에 `분석 #1 연결 실패: 서버 꺼짐`만 찍히고 `ERROR`, 시각, 이름이 없었음. 사용자가 "이 오류가 로깅 설정이 없어서 그런 거냐"고 질문
- **원인:** 오류가 아니라 의도한 실패를 흉내 내는 테스트가 남긴 로그였음. 모양이 없었던 이유는 로깅 설정이 하나도 없으면 파이썬이 "메시지만 찍는 기본 방식"으로 대신 출력하기 때문(cv_service에서 겪은 것과 같은 현상)
- **해결:** ① `settings.py`에 `LOGGING` 추가(모양 해결), ② 실패 테스트를 `assertLogs`로 감싸서 화면 출력 제거(소음 해결)

### 3. `LOGGING` 설정을 테스트만으로는 확인할 수 없었음
- **고려한 점:** `assertLogs`가 로그를 붙잡기 때문에 테스트는 설정이 맞든 틀리든 통과함 → 설정 자체가 작동하는지는 테스트로 알 수 없음
- **해결:** cv_service를 일부러 끄고 Celery worker + Django 서버를 켠 뒤 실제로 분석을 요청해서 worker 터미널에서 확인
- **결과:** `2026-10-19 23:29:28,276 ERROR analysis.tasks: 분석 #44 연결 실패: ...` 한 줄이 중복 없이 출력됨

### 결과 검증
```
Ran 19 tests in ...

OK
```
| 단계 | 개수 |
|---|---|
| 죽은 테스트 삭제 전 | 19 |
| 삭제 후 | 19 (원래 세어지지 않던 코드) |
| 로깅 변경 후 | 19 |

### 남은 과제
- 배포 방식 결정 및 배포용 설정 (로그를 어디서 볼지, `SECRET_KEY` 환경 변수화 포함)
- (고도화) 작은 신발/부츠 미탐지 근본 해결: 하단 확대 재탐지, 더 큰 탐지 모델, Gemini 박스 출력 중 선택
- (고도화) `Analysis`에 `user` FK 추가: 요청자 기록과 "내 분석 기록" 기능, 필요하면 `error_detail` 필드도 이때 같이 추가
- (고도화) 콜백을 완전한 비동기로: FastAPI `BackgroundTasks`, 실패 콜백
- (고도화) JWT 도입 시 `posts` 테스트의 403 기대값 점검
