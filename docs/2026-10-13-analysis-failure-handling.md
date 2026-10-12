# AI 분석 실패 처리 (영원히 "분석 중"으로 남는 문제 해결) — 2026-10-13

## 1. 기술문서

### 한 줄 요약
분석이 어떤 이유로든 끝나지 못했을 때 화면이 **영원히 "분석 중"**으로 남던 문제를 고쳤다. 이제는 상태가 "실패"로 바뀌고 결과 페이지에 안내 문구가 자동으로 표시된다.

### 무엇이 문제였나
실패 상태(`failed`), 에러 문구를 담는 칸(`error_message`), 결과 페이지의 실패 화면, 3초마다 상태를 묻는 폴링의 실패 감지는 **이미 만들어져 있었다.** 그런데 실제로 상태를 "실패"로 바꾸는 코드가 어디에도 없었다. 그래서 분석이 실패해도 상태는 "대기중"에 머물렀고, 화면은 끝없이 상태만 묻고 있었다.

### 실패가 전달되지 않던 다섯 가지 길

| 상황 | 고치기 전 | 고친 후 화면에 보이는 문구 |
|---|---|---|
| cv_service가 꺼져 있음 | Celery 작업이 에러로 죽고 상태는 그대로 | 분석 서버에 연결할 수 없습니다 |
| cv_service가 응답 없이 멈춤 | 제한 시간이 없어 끝없이 기다림 | 분석 시간이 초과되었습니다 |
| cv_service가 에러(500)를 돌려줌 (깨진 이미지 등) | 응답 내용을 확인하지 않고 그냥 끝남 | 분석 중 오류가 발생했습니다 |
| Django 콜백 저장이 실패함 | cv_service가 콜백 응답을 확인하지 않아 성공으로 끝남 | 분석 중 오류가 발생했습니다 |
| Celery나 Redis가 꺼져 있음 | 작업이 시작조차 안 됨 | 분석이 시작되지 않았거나 너무 오래 걸리고 있습니다 |

### 설계: 실패를 기록하는 곳은 두 군데
```
[앞의 네 가지]
Django 콜백 실패 → cv_service가 알아채고 에러 응답 → Celery 작업이 알아채고 "실패" 기록
cv_service 꺼짐 / 멈춤 / 에러 응답 ─────────────────→ Celery 작업이 알아채고 "실패" 기록

[마지막 한 가지]
Celery가 꺼져 있음 → 기록할 주체가 없음 → Django의 상태 조회 API가 "너무 오래됐다"고 판단해 "실패" 기록
```

- **Celery 작업(`run_analysis`)**: cv_service와 관련된 모든 실패를 여기서 잡는다.
- **상태 조회 API(`analysis_status`)**: Celery 자체가 꺼진 경우를 대비한 마지막 안전망. 요청한 지 6분이 넘었는데 아직 끝나지 않은 분석을 실패로 바꾼다.

### 시간 설정

| 값 | 위치 | 의미 |
|---|---|---|
| 연결 대기 5초 | `tasks.py` `ANALYZE_TIMEOUT` | cv_service에 접속 자체가 5초 안에 안 되면 포기 |
| 응답 대기 300초 | `tasks.py` `ANALYZE_TIMEOUT` | 접속은 됐는데 300초(5분) 동안 답이 없으면 포기. 서버를 켠 직후의 첫 분석이 몇 분 걸릴 수 있어 넉넉하게 잡음 |
| 콜백 대기 10초 | `callback.py` | cv_service가 Django에 결과를 보낼 때 10초 안에 답이 없으면 포기 |
| 6분 | `views.py` `STALE_AFTER` | 요청 후 이 시간이 지나도 미완료면 실패로 봄. Celery의 최대 대기(약 5분)보다 길어야 정상 진행 중인 분석을 실패로 잘못 처리하지 않음 |

### 상태 흐름 (변경 후)
```
대기중(pending) ──작업 시작──→ 분석중(processing) ──콜백 성공──→ 완료(completed)
      │                              │
      └──────────── 실패 ────────────┴──→ 실패(failed) + error_message
```
"분석중" 상태는 정의만 돼 있고 한 번도 쓰이지 않았는데, 이번에 작업이 시작되는 시점에 켜지도록 했다.

### 신규/변경 파일

| 파일 | 내용 |
|---|---|
| `analysis/tasks.py` | task 이름을 `run_dummy_analysis`에서 `run_analysis`로 변경, 제한 시간·응답 확인·예외 처리 추가, `mark_failed` 함수 추가, 시작 시 "분석중"으로 전환 |
| `analysis/views.py` | task 이름 변경 반영, `analysis_status`에 오래된 미완료 분석의 실패 전환 추가 |
| `cv_service/app/callback.py` | 콜백 응답 확인과 제한 시간 추가 |
| `README.md` | 실패 처리 설명 추가, task 이름 갱신 |

모델과 템플릿, JS는 수정하지 않았다. 필요한 칸과 화면이 이미 있었기 때문이다.

---

## 2. 클래스·함수 단위 코드리뷰

### `mark_failed` — "완료된 것은 건드리지 않는다"
`Analysis.objects.filter(pk=...).exclude(status=완료).update(...)` 형태로 썼다. 레코드를 꺼내서 고치고 저장하는 대신, "이 조건에 맞는 것만 DB에서 바로 고쳐라"라고 한 번에 지시한다.

"완료된 것은 빼고"라는 조건이 핵심이다. 이런 경우가 있기 때문이다.
1. cv_service가 분석을 끝내고 Django 콜백으로 결과를 저장했다 (상태: 완료)
2. 그런데 cv_service가 Celery에게 돌려주는 응답이 늦어져서 Celery 쪽에서 시간 초과가 났다
3. 조건이 없으면 이미 결과가 저장된 분석을 "실패"로 덮어쓰게 된다

꺼내서 고치는 방식(`analysis.status = ...; analysis.save()`)은 꺼낸 시점과 저장하는 시점 사이에 다른 곳에서 상태가 바뀌면 그걸 모르고 덮어쓴다. `filter().update()`는 DB가 조건 확인과 수정을 한 번에 하므로 그럴 틈이 없다.

짚어 둘 점: `update()`는 `updated_at`(저장할 때마다 갱신되는 시각)을 자동으로 바꿔 주지 않는다. 지금은 이 값을 화면에서 쓰지 않아서 문제가 없다.

### `run_analysis` — 이름 변경
`run_dummy_analysis`는 가짜 결과를 돌려주던 시절의 이름이다. 이제 실제 모델이 동작하므로 `run_analysis`로 바꿨다. 이름이 바뀌면 Celery worker를 다시 켜야 새 이름을 인식한다.

### `run_analysis` — 시작할 때 "분석중"으로 전환
`filter(pk=..., status=대기중).update(status=분석중)`. 여기도 "대기중일 때만"이라는 조건을 달았다. 같은 작업이 어떤 이유로 두 번 실행되더라도 이미 완료되거나 실패한 분석을 "분석중"으로 되돌리지 않는다.

### `run_analysis` — `try / except` 세 갈래
- `ConnectionError`: 서버가 꺼져 있어 연결이 안 될 때
- `Timeout`: 제한 시간 안에 답이 안 올 때
- `Exception`: 그 밖의 전부. cv_service의 에러 응답(`raise_for_status()`가 일으킨 예외), 이미지 파일이 없는 경우 등

`except`는 위에서부터 차례로 맞춰 보므로 구체적인 것을 먼저, 뭐든 잡는 `Exception`을 마지막에 둬야 한다. 순서를 뒤집으면 전부 `Exception`에서 잡혀 문구 구분이 사라진다.

이미지 파일을 여는 줄도 `try` 안에 넣었다. 파일이 지워진 경우에도 실패로 기록되게 하기 위해서다.

### `raise_for_status()` — 이번 작업의 가장 작은 핵심
`requests`는 서버가 500 에러를 돌려줘도 예외를 일으키지 않고 조용히 응답 객체를 돌려준다. "에러 응답이면 예외를 일으켜라"가 이 한 줄이다. `tasks.py`와 `callback.py` 양쪽에 넣었고, 이 두 줄이 실패를 Django 콜백 → cv_service → Celery로 이어서 전달하는 고리가 된다.

### 사용자에게 보이는 문구와 로그를 나눈 이유
`error_message`는 결과 페이지에 그대로 표시된다. 여기에 `500 Server Error: Internal Server Error for url: http://localhost:8001/analyze` 같은 원문을 넣으면 사용자가 이해할 수 없고 내부 주소도 드러난다. 그래서 화면용으로는 쉬운 안내 문구를 저장하고, 원인 원문은 `print`로 Celery 터미널에 남긴다.

아쉬운 점: `print`로 남긴 로그는 터미널을 닫으면 사라진다. 배포 단계에서는 정식 로깅으로 바꿔야 한다.

### Celery 터미널에 `succeeded`가 뜨는 것
분석이 실패해도 Celery는 `succeeded`를 찍는다. Celery의 `succeeded`는 "분석이 성공했다"가 아니라 "이 함수가 에러로 죽지 않고 끝까지 실행됐다"는 뜻이다. 우리가 에러를 직접 잡아서 처리했기 때문에 Celery 입장에서는 정상 종료다. 실패 여부는 그 위에 찍히는 `[run_analysis] #번호 ...` 줄과 DB의 상태로 확인한다.

### `analysis_status` — 조회 API에서 상태를 바꾸는 것
원래 이 API는 상태를 읽기만 했는데, 이제 오래된 미완료 분석을 실패로 바꾸기도 한다. "조회"라는 이름의 API가 데이터를 바꾸는 것은 깔끔한 설계는 아니다. 그래도 이 자리를 고른 이유가 있다.
- Celery가 꺼져 있을 때도 살아 있는 것은 Django뿐이다.
- 결과 페이지가 3초마다 이 API를 부르고 있으므로, 사용자가 기다리는 동안 자연스럽게 검사가 이뤄진다.
- 주기적으로 오래된 분석을 청소하는 별도 작업을 만들면 그 작업도 Celery에 의존하게 되어 같은 문제가 반복된다.

대가: 아무도 그 결과 페이지를 열지 않으면 그 분석은 DB에 "대기중"으로 계속 남는다. 화면에 잘못 보이는 일은 없으므로 받아들였다.

### 실패로 표시된 뒤 Celery를 켜면
Celery가 꺼진 동안 들어온 요청은 Redis 대기열에 남아 있다. 6분이 지나 "실패"로 표시된 뒤에 Celery를 켜면 그 요청이 뒤늦게 처리되고, 콜백이 상태를 "완료"로 바꾼다. 늦게라도 결과가 나오면 보여 주는 쪽이 낫다고 보고 그대로 뒀다.

### `callback.py` — 남아 있는 약점
Django 콜백이 아이템을 몇 개 저장하다가 중간에 에러가 나면, 그때까지 저장된 아이템은 DB에 남고 분석은 "실패"가 된다. 재분석은 새 분석 레코드를 만들기 때문에 화면에 섞여 보이지는 않는다. 깔끔하게 하려면 콜백의 저장 전체를 "전부 성공하거나 전부 취소"로 묶어야 한다(트랜잭션). 이번 범위에는 넣지 않았다.

---

## 3. 코드 한 줄 한 줄 주석

### `analysis/tasks.py` (전체)
```python
import requests                                              # FastAPI 서버로 HTTP 요청 보낼 때 씀
from celery import shared_task                                # Celery task로 등록해주는 데코레이터
from django.conf import settings                               # settings.py에 적어둔 주소들 가져오기

from .models import Analysis                                    # analysis_id로 레코드 조회할 때 씀

ANALYZE_TIMEOUT = (5, 300)  # (연결 대기 5초, 응답 대기 300초) — 서버 켠 직후 첫 분석은 몇 분 걸릴 수 있어 넉넉하게


def mark_failed(analysis_id, message):
    """분석을 실패 상태로 바꾸고 안내 문구를 저장 (이미 완료된 분석은 건드리지 않음)"""
    Analysis.objects.filter(pk=analysis_id).exclude(      # 이 id의 분석 중에서, 완료된 것은 빼고
        status=Analysis.STATUS_COMPLETED                  # (빼는 조건: 상태가 "완료")
    ).update(                                              # 조건에 맞는 레코드만 DB에서 바로 수정
        status=Analysis.STATUS_FAILED,                     # 상태를 "실패"로
        error_message=message,                             # 화면에 보여줄 안내 문구 저장
    )


@shared_task                                                      # 이 함수를 Celery가 "일감"으로 등록, .delay()로 호출 가능해짐
def run_analysis(analysis_id):
    analysis = Analysis.objects.get(pk=analysis_id)                 # DB에서 해당 분석 레코드 조회 (callback_token도 이미 들어있음)

    Analysis.objects.filter(pk=analysis_id, status=Analysis.STATUS_PENDING).update(  # 이 분석이 "대기중"일 때만
        status=Analysis.STATUS_PROCESSING                             # "분석중"으로 변경
    )

    image_field = analysis.image if analysis.image else analysis.post.image
    # A 플로우(게시물 기반)면 analysis.image가 비어있어서 analysis.post.image를 씀,
    # B 플로우(독립 업로드)면 analysis.image가 있으니 그걸 그대로 씀

    callback_url = f"{settings.INTERNAL_BASE_URL}/analysis/api/{analysis.id}/callback/"  # 결과를 돌려받을 Django 콜백 주소
    analyze_url = f"{settings.CV_SERVICE_BASE_URL}/analyze"                                # FastAPI의 분석 요청 주소

    try:                                                                  # 여기서부터는 실패할 수 있는 구간
        with image_field.open("rb") as image_file:                        # 이미지 파일을 바이너리로 열기
            response = requests.post(                                        # FastAPI에 "이 사진 분석해줘" 요청
                analyze_url,                                                   # 요청을 보낼 주소
                data={                                                         # 파일이 아닌 일반 텍스트 값들
                    "callback_url": callback_url,                              # 결과를 돌려보낼 주소
                    "callback_token": analysis.callback_token,                 # Django가 검증할 토큰
                },
                files={"image": image_file},                                  # 실제 이미지 파일
                timeout=ANALYZE_TIMEOUT,                                       # 이 시간 넘게 답이 없으면 포기
            )
        response.raise_for_status()                                         # 응답이 에러(4xx/5xx)면 예외를 일으킴
    except requests.exceptions.ConnectionError as error:                  # 서버가 꺼져 있어 연결 자체가 안 될 때
        print(f"[run_analysis] #{analysis_id} 연결 실패: {error}")          # 원인 원문은 Celery 터미널에 남기고
        mark_failed(analysis_id, "분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")  # 화면용 문구를 저장
    except requests.exceptions.Timeout as error:                           # 제한 시간 안에 답이 안 올 때
        print(f"[run_analysis] #{analysis_id} 시간 초과: {error}")          # 원인 원문 로그
        mark_failed(analysis_id, "분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")      # 화면용 문구
    except Exception as error:                                              # 그 밖의 모든 문제 (서버 에러 응답, 이미지 파일 없음 등)
        print(f"[run_analysis] #{analysis_id} 오류: {error}")               # 원인 원문 로그
        mark_failed(analysis_id, "분석 중 오류가 발생했습니다. 다른 사진으로 다시 시도해 주세요.")  # 화면용 문구
```

### `analysis/views.py` (변경된 부분)
```python
from datetime import timedelta                              # "6분" 같은 시간 간격을 표현할 때 씀
from django.utils import timezone                            # 현재 시각을 가져올 때 씀
from .tasks import run_analysis, mark_failed                 # 분석 요청 task + 실패 기록 함수

STALE_AFTER = timedelta(minutes=6)  # 요청 후 이 시간이 지나도 안 끝나면 실패로 봄 (Celery의 최대 대기 5분보다 길게)
```
```python
    run_analysis.delay(analysis.id)                          # request_analysis, upload_and_analyze 두 곳에서 이름만 변경
```
```python
@require_GET                                                     # 상태 조회는 GET 요청만 허용 (JS가 fetch로 호출)
def analysis_status(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)          # 없는 id면 404

    is_waiting = analysis.status in (Analysis.STATUS_PENDING, Analysis.STATUS_PROCESSING)  # 아직 안 끝난 상태인지 (대기중 또는 분석중)
    if is_waiting and timezone.now() - analysis.created_at > STALE_AFTER:                  # 안 끝났는데 요청한 지 6분이 넘었으면
        mark_failed(analysis.id, "분석이 시작되지 않았거나 너무 오래 걸리고 있습니다. 잠시 후 다시 시도해 주세요.")  # 실패로 기록
        analysis.refresh_from_db()                                    # 방금 DB에서 바뀐 상태를 다시 읽어옴

    return JsonResponse({"status": analysis.status})                  # 지금 상태값만 JSON으로 돌려줌
```

### `cv_service/app/callback.py` (전체)
```python
import requests  # Django 콜백 주소로 HTTP 요청을 보낼 때 씀
from .schemas import CallbackPayload  # 보낼 데이터의 모양을 정의해둔 스키마


def send_callback(callback_url: str, payload: CallbackPayload):
    response = requests.post(callback_url, json=payload.model_dump(), timeout=10)  # Pydantic 객체를 dict로 바꿔서 JSON으로 전송, 10초 넘으면 포기
    response.raise_for_status()  # Django가 저장에 실패하면 예외 발생 → /analyze가 500으로 응답 → Celery가 실패로 기록
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### "실패 상태를 만들어 두는 것"과 "실패 상태로 바꾸는 것"은 다르다
모델에 실패 상태가 있고 화면에 실패 문구가 준비돼 있어도, 실제로 그 상태로 바꾸는 코드가 없으면 아무 일도 일어나지 않는다. 기능을 만들 때는 잘되는 경우뿐 아니라 "안 되면 어떻게 되는가"를 끝까지 따라가 봐야 한다.

### 제한 시간 (timeout)
네트워크 요청은 상대가 답을 안 하면 기본적으로 끝없이 기다린다. `timeout=(5, 300)`은 "연결에 5초, 응답에 300초까지만 기다린다"는 뜻이다. 외부로 나가는 요청에는 항상 제한 시간을 거는 것이 기본이다.

### `raise_for_status()`
`requests`는 서버가 에러 응답을 줘도 예외를 일으키지 않는다. 응답을 받는 데는 성공했기 때문이다. 에러 응답을 실패로 다루려면 이 메서드를 직접 불러야 한다.

### `try / except`의 순서
위에서부터 차례로 맞춰 보고 처음 맞는 곳에서 처리한다. 구체적인 예외를 위에, 범위가 넓은 예외를 아래에 둔다.

### `filter().update()`와 `save()`의 차이
- `save()`: 레코드를 꺼내서 값을 바꾸고 통째로 저장한다. 꺼낸 뒤에 다른 곳에서 바뀐 내용을 덮어쓸 수 있다.
- `filter().update()`: 조건에 맞는 레코드만 DB에서 바로 고친다. 조건 확인과 수정이 한 번에 이뤄진다.

"완료된 것은 건드리지 마라" 같은 조건부 수정에는 후자가 안전하다.

### `refresh_from_db()`
`filter().update()`는 DB만 고치고, 이미 꺼내서 손에 들고 있는 객체는 바꾸지 않는다. 손에 든 객체를 최신으로 맞추려면 `refresh_from_db()`로 다시 읽어 와야 한다.

### `timedelta`와 시간 계산
`timedelta(minutes=6)`은 "6분"이라는 시간 간격이다. `timezone.now() - analysis.created_at`처럼 시각에서 시각을 빼면 그 사이의 간격이 나오고, 간격끼리 크기를 비교할 수 있다.

### Celery의 `succeeded`가 뜻하는 것
작업 함수가 예외 없이 끝났다는 뜻일 뿐, 우리가 하려던 일이 성공했다는 뜻이 아니다.

### Celery는 코드를 바꿔도 자동으로 다시 뜨지 않는다
Django(`runserver`)와 cv_service(`--reload`)는 파일을 저장하면 자동으로 다시 뜨지만, Celery worker는 직접 껐다 켜야 한다. 특히 task 이름을 바꿨을 때는 반드시 다시 켜야 한다.

### 대기열에 쌓인 작업은 사라지지 않는다
Celery가 꺼져 있어도 요청은 Redis 대기열에 남는다. Celery를 다시 켜면 쌓여 있던 요청이 처리된다.

### 서비스마다 꺼졌을 때의 증상이 다르다
cv_service가 꺼지면 Celery가 연결 실패를 알아챈다. Celery가 꺼지면 알아챌 주체가 없다. 어떤 부품이 꺼졌을 때 "누가 그걸 알아채는가"를 부품별로 따져 봐야 한다.

---

## 5. 트러블슈팅

### 1) Celery를 끄고 테스트했더니 계속 "분석 중"
- **상황**: "서버가 꺼졌을 때 실패 문구가 뜨는지" 테스트하면서 cv_service가 아니라 Celery를 껐다. 화면은 실패 문구 없이 계속 "분석 중입니다..."로 남았다.
- **원인**: 그 시점의 코드는 실패를 기록하는 주체가 Celery 작업 하나뿐이었다. Celery가 꺼져 있으면 작업이 시작조차 되지 않아 실패를 기록할 주체가 없다. 요청은 Redis 대기열에 쌓인 채 남는다.
- **해결**: 상태 조회 API(`analysis_status`)에 "요청한 지 6분이 넘었는데 아직 끝나지 않았으면 실패로 전환"을 추가했다. Celery가 꺼져 있어도 Django는 살아 있고, 결과 페이지가 3초마다 이 API를 부르기 때문이다.
- **배운 점**: 처음 설계에서는 "별도 장치가 필요하니 나중에 정하자"로 미뤄 둔 경우였는데, 직접 겪어 보니 가장 쉽게 마주치는 상황이었다.

### 결과 검증
- **cv_service 꺼짐**: Celery는 켜 둔 채 cv_service만 끄고 요청 → 화면에 "분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."가 표시됨.
- **정상 동작**: 서버를 전부 켜고 실제 사진으로 요청 → 이전과 같이 분석 결과가 표시됨. `callback.py`에 응답 확인을 추가한 뒤에도 정상 흐름이 유지됨을 확인.
- **깨진 파일**: 텍스트 파일의 확장자를 `.jpg`로 바꿔 올림 → Celery 터미널에 `[run_analysis] #29 오류: 500 Server Error: Internal Server Error for url: http://localhost:8001/analyze`가 찍힘. 작업을 받고 0.13초 만에 실패가 기록됨.
- **Celery 꺼짐**: `STALE_AFTER`를 임시로 20초로 줄이고 Celery를 끈 채 요청 → 시간이 지나자 화면이 실패 문구로 자동 전환됨. 확인 후 6분으로 되돌림.
