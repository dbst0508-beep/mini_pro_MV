# 콜백 결과 저장 트랜잭션 처리 + 저장 실패 시 분석 실패 처리 — 2026-10-19

## 1. 기술문서

### 한 줄 요약
cv_service가 보낸 분석 결과를 Django가 저장할 때, 저장을 `transaction.atomic()`으로 묶어 "전부 저장되거나 전부 취소"되게 했습니다. 저장이 실패하면 분석을 바로 `실패`로 표시하고, 보낸 쪽(cv_service)에도 500을 돌려줍니다.

### 왜 필요했나
콜백 view는 저장을 여러 번 나눠서 했습니다.

1. `DetectedItem` 여러 개 저장
2. `StyleScore` 여러 개 저장
3. `Analysis`에 해석 글과 `완료` 상태 저장

이 중간에 에러가 나면 **일부만 저장된 채** 남습니다.

| 상황 | 이전 동작 | 문제 |
|---|---|---|
| 아이템 3개 저장 후 스타일 저장에서 에러 | 아이템 3개는 DB에 남고, 상태는 `분석중` 그대로 | 반쪽짜리 데이터가 남고, 재분석하면 아이템이 중복될 수 있음 |
| 에러 후 상태 | 상태 조회 API가 6분이 지나야 `실패`로 바꿈 | 사용자가 6분 동안 "분석 중" 화면을 봄 |

### 무엇을 바꿨나
| 파일 | 변경 |
|---|---|
| `analysis/views.py` | `analysis_callback`의 저장 부분을 `try` + `transaction.atomic()`으로 감싸고, 실패하면 로그 → `mark_failed` → 500 응답. `logging`, `transaction` import와 `logger` 추가 |
| `analysis/tests.py` | 저장 실패 시 전부 취소되고 `실패` 처리되는지 확인하는 테스트 1개 추가 |

### 저장 실패 시 흐름
```
cv_service ──결과 전송──▶ Django 콜백 view
                          ├─ atomic 블록 안에서 저장 시작
                          ├─ 에러 발생 → 블록 안에서 저장한 것 전부 취소(롤백)
                          ├─ logger.exception으로 원인 기록
                          ├─ mark_failed로 상태를 "실패" + 안내 문구 저장
                          └─ 500 응답 ──▶ cv_service가 실패로 인식 (Celery task도 실패 기록)
```

### 실행 방법
```bash
uv run python manage.py test analysis
```
- 기대 결과: `Ran 19 tests` / `OK` (이번에 1개 추가, 이전 18개)

### 의도적으로 바꾸지 않은 것
- 토큰 검사와 `json.loads`는 `try` **밖**에 둠. 토큰이 틀린 요청(403)은 저장 실패(500)와 다른 문제이고, 남의 분석을 실패로 바꾸는 데 악용되면 안 되기 때문입니다.
- `mark_failed`는 `atomic` 블록 **밖**에서 호출. 블록 안에서 호출하면 그 실패 표시까지 같이 취소되기 때문입니다.

---

## 2. 클래스·함수 단위 코드리뷰

### `analysis_callback` — 저장 구간만 감싼 구조
| 구간 | 위치 | 이유 |
|---|---|---|
| 분석 조회, 토큰 검사 | `try` 밖 | 없는 id는 404, 틀린 토큰은 403으로 각각 따로 처리 |
| 아이템·스타일·해석·상태 저장 | `try` + `atomic` 안 | 한 묶음으로 성공/실패 |
| 실패 처리 | `except` 안 | 이미 롤백이 끝난 시점에 실행됨 |

### `transaction.atomic()` — 전부 아니면 전무
`with` 블록 안의 DB 저장을 하나의 묶음으로 만듭니다. 블록이 에러 없이 끝나면 **한꺼번에 확정**하고, 에러가 나서 빠져나오면 **블록 안에서 한 저장을 전부 취소**합니다.

> 비유: 장바구니에 담기만 하다가 계산대에서 결제가 한 번에 이뤄지는 것과 같습니다. 결제가 실패하면 담아 둔 것도 없던 일이 됩니다.

### `except Exception`을 넓게 잡은 이유
어떤 에러가 날지(필수 키 누락, 숫자가 아닌 값, 중복 규칙 위반 등) 미리 다 알 수 없고, **어떤 에러든 결과는 같기** 때문입니다("이 분석은 저장 실패"). 대신 원인은 `logger.exception`으로 남겨서 추적할 수 있게 했습니다.

### `logger.exception(...)` vs `logger.error(...)`
`exception`은 `except` 안에서 쓰면 **에러 내용과 발생 위치(traceback)까지** 자동으로 기록합니다. 저장 실패는 "왜 났는지"가 핵심 정보라서 이쪽을 골랐습니다. (cv_service의 Gemini 실패는 서비스가 계속되므로 `warning`, 이쪽은 분석이 실제로 실패하므로 에러 단계입니다.)

### `mark_failed(analysis.id, ...)` — 롤백 이후에도 정상 동작하는 이유
롤백되면 상태는 콜백 전 값(`분석중`)으로 돌아갑니다. `mark_failed`는 "완료가 아닌 것"만 `실패`로 바꾸므로 이 상태에서 정상 동작합니다. 이미 `완료`된 분석을 실패로 덮어쓰지 않는 기존 안전장치도 그대로 유지됩니다.

### 500 응답의 의미
cv_service는 콜백 응답을 확인해서 실패면 에러로 응답합니다(이전 작업에서 구현). 그래서 Django가 500을 주면 cv_service → Celery task까지 실패가 전달되어, 세 곳이 모두 "이 분석은 실패"로 일치합니다.

### 추가한 테스트 `test_save_failure_rolls_back_everything_and_marks_failed`
**실패를 만드는 방법:** 같은 스타일 이름을 두 번 보냅니다. `StyleScore`는 (분석, 스타일 이름) 조합이 중복될 수 없는 규칙이 있어서 **두 번째 저장에서 DB가 에러**를 냅니다. 이때 아이템과 첫 번째 스타일은 이미 저장된 상태라 롤백 여부를 확인하기 좋은 상황입니다.

| 확인 | 의미 |
|---|---|
| `status_code == 500` | 보낸 쪽에 실패를 알림 |
| `detected_items.count() == 0` | 먼저 저장된 아이템도 취소됨 (**이 테스트의 핵심**) |
| `style_scores.count() == 0` | 먼저 저장된 첫 스타일도 취소됨 |
| `status == FAILED` | 6분 안 기다리고 바로 실패 표시 |
| `"저장하지 못했습니다" in error_message` | 사용자에게 보일 안내 문구가 저장됨 |

---

## 3. 코드 한 줄 한 줄 주석

### `analysis/views.py` — 추가한 import와 로거
```python
import logging                                              # print 대신 쓰는 기록 도구 (실패 원인을 남길 때 씀)
from django.db import transaction                           # 여러 DB 저장을 "전부 성공 아니면 전부 취소"로 묶는 도구

logger = logging.getLogger(__name__)  # 이 파일 전용 기록 담당자 (이름은 "analysis.views"가 됨)
```

### `analysis/views.py` — `analysis_callback`의 저장 부분
```python
    try:                                                           # 저장 중 어떤 에러가 나도 아래 except가 받도록 감싸기 시작
        with transaction.atomic():                                   # 이 블록 안의 저장을 한 묶음으로: 중간에 에러가 나면 안에서 저장한 것이 전부 취소됨
            for item in data.get("detected_items", []):                # 검출된 아이템 목록을 하나씩 순회 (없으면 빈 리스트)
                DetectedItem.objects.create(                             # 각 아이템마다 DetectedItem 레코드 새로 생성
                    analysis=analysis,                                     # 어느 분석에 속하는지 연결
                    category=item["category"],                             # 필수값이라 없으면 에러가 나도록 [] 로 접근
                    label=item.get("label", ""),                            # 선택값이라 없으면 빈 문자열 기본값
                    ...
                )

            for score in data.get("style_scores", []):                  # 스타일 비율 목록도 동일하게 순회
                StyleScore.objects.create(analysis=analysis, style_name=score["style_name"], ratio=score["ratio"])

            analysis.interpretation = data.get("interpretation", "")     # LLM 해석 텍스트 채우기
            analysis.status = Analysis.STATUS_COMPLETED                    # 상태를 "완료"로 변경
            analysis.save()                                                 # 변경사항 저장 (여기까지 와야 묶음 전체가 확정됨)
    except Exception:                                                  # 묶음 안에서 무슨 에러가 나도 (이 시점엔 이미 전부 되돌려진 상태)
        logger.exception("분석 #%s 결과 저장 실패", analysis.id)         # 실패 원인(에러 내용과 위치)을 로그에 남김
        mark_failed(analysis.id, "분석 결과를 저장하지 못했습니다. 다른 사진으로 다시 시도해 주세요.")  # 분석을 바로 "실패"로 표시 (6분 기다리지 않게)
        return JsonResponse({"error": "failed to save result"}, status=500)  # 보낸 쪽(cv_service)에도 실패를 알림

    return JsonResponse({"ok": True})                                   # 처리 성공 응답
```

### `analysis/tests.py` — 추가한 테스트 (전체)
```python
    def test_save_failure_rolls_back_everything_and_marks_failed(self):
        self.payload["style_scores"] = [  # 같은 스타일 이름을 두 번 보냄: DB의 중복 금지 규칙(unique_together)에 걸려 두 번째 저장에서 에러가 남
            {"style_name": "캐주얼", "ratio": 60.0},
            {"style_name": "캐주얼", "ratio": 40.0},
        ]

        with self.assertLogs("analysis.views", level="ERROR"):  # 실패 로그를 화면에 안 찍고 붙잡아 둠
            response = self.post_callback(self.payload)  # 콜백 요청 보내기

        self.assertEqual(response.status_code, 500)  # 보낸 쪽에 실패를 알려야 함
        self.analysis.refresh_from_db()  # 뷰가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.detected_items.count(), 0)  # 아이템은 먼저 저장됐었지만 되돌려져서 0개여야 함
        self.assertEqual(self.analysis.style_scores.count(), 0)  # 첫 번째 스타일도 되돌려져서 0개여야 함
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # 분석은 "실패"로 표시돼야 함
        self.assertIn("저장하지 못했습니다", self.analysis.error_message)  # 안내 문구가 저장돼야 함
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 트랜잭션: 전부 아니면 전무
여러 번에 나눠 하는 저장이 "중간에 멈추면 반쯤만 된 상태"가 되는 것을 막는 장치입니다. 은행 이체(출금 + 입금)가 대표 예시입니다. 출금만 되고 입금이 안 되면 안 되니까 둘을 한 묶음으로 처리합니다.

### 롤백은 DB에만 적용된다
`atomic` 블록이 취소하는 것은 **DB 저장**입니다. 파일 저장, 외부 서버 호출, 메모리의 변수 값(`analysis.status = ...`)은 되돌려지지 않습니다. 그래서 실패 처리(`mark_failed`)는 DB를 다시 읽는 방식(`filter().update()`)으로 되어 있어 영향을 받지 않습니다.

### 실패 표시는 `atomic` 밖에서
실패 표시를 블록 안에서 했다면, 에러로 블록이 취소될 때 **실패 표시까지 같이 사라집니다.** "취소될 일"과 "취소 후에 남겨야 하는 일"은 블록 안팎으로 나눠야 합니다.

### 실패를 "빨리, 명확하게" 알리기
- **빠르게:** 6분 뒤 안전장치에 맡기지 않고 실패한 즉시 상태를 바꿈
- **명확하게:** 사용자에겐 안내 문구, 보낸 쪽엔 500, 개발자에겐 로그(traceback)
- 세 대상이 필요로 하는 정보가 다르므로 셋 다 따로 챙깁니다.

### 테스트로 롤백 확인하기
"에러가 나는 상황"을 일부러 만들되, **에러가 나기 전에 이미 저장된 것**이 있어야 롤백을 검증할 수 있습니다. 첫 저장부터 실패하면 취소할 것이 없어 롤백이 되는지 안 되는지 구별할 수 없습니다. 이번 테스트가 "아이템 저장 → 스타일 1번 저장 → 스타일 2번에서 실패" 순서가 되도록 한 이유입니다.

### 안전장치는 겹겹이
| 단계 | 안전장치 |
|---|---|
| 저장 실패 | 이번 작업 (즉시 `실패`) |
| cv_service/Celery 실패 | 이전 작업 (task가 `실패` 기록) |
| 작업이 아예 시작 안 됨 | 상태 조회 API (6분 후 `실패`) |

앞 단계가 막지 못한 경우를 뒤 단계가 받는 구조입니다. 이번 작업으로 "저장 실패"가 6분짜리 안전장치에 기대던 구멍이 메워졌습니다.

---

## 5. 트러블슈팅

### 1. "`print`로 확인" 대신 로그 테스트에서 에러 로그가 화면에 찍힘
- **증상:** 테스트에서 일부러 실패를 일으켰더니 테스트는 통과하는데 `ERROR analysis.views: 분석 #... 결과 저장 실패`와 traceback이 터미널에 가득 출력됨
- **원인:** 의도한 실패여도 `logger.exception`은 실제로 로그를 출력함
- **해결:** `with self.assertLogs("analysis.views", level="ERROR"):`로 감싸서 로그를 붙잡아 둠 (cv_service 테스트에서 쓴 방식과 동일)

### 2. 롤백 검증이 의미 있는지 점검
- **고려한 점:** 첫 저장에서 바로 실패하는 입력이면 롤백이 없어도 테스트가 통과함
- **해결:** 아이템·첫 스타일이 먼저 저장되고 **두 번째 스타일에서** 실패하도록 입력을 설계. 롤백이 빠지면 `count() == 0` 확인이 실패함

### 결과 검증
```
Ran 19 tests in 12.804s

OK
```

### 남은 과제
- (정정) 작은 신발/부츠 미탐지는 기준값(`CONFIDENCE_THRESHOLD`) 조정으로 해결되지 않는 알려진 한계입니다. 자세한 내용은 `docs/2026-10-19-logging-cleanup.md`의 "알려진 한계" 참고
- Django 쪽 `analysis/tasks.py`의 `print` 3개를 `logging`으로 교체 (Django 로깅 설정 포함)
- README의 `## 실행 방법` 제목 위치 정리
- 배포 방식 결정 및 배포용 설정
- (고도화) `Analysis`에 `user` FK 추가: 요청자 기록과 "내 분석 기록" 기능
- (고도화) 콜백을 완전한 비동기로: FastAPI `BackgroundTasks`, 실패 콜백
