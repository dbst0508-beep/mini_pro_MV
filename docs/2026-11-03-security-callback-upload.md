# 내부 통신 잠그기 + 업로드 검사 (2026-11-01 ~ 2026-11-03)

브랜치: `feature/security-callback-upload`

보안 점검표의 B 묶음(2번 내부 통신, 3번 업로드 검사, 4번 늦은 콜백 처리)과 피드 XSS 수정을 한 브랜치에서 했습니다.

---

## 1. 기술문서

### 1-1. 왜 바꿨나

분석은 이렇게 흘러갑니다.

```
브라우저 → Django(web) → Celery → cv_service /analyze → (분석) → Django 콜백 주소로 결과 전송
```

이 흐름에 구멍이 있었습니다. 회사 건물에 비유하면 이렇습니다.

| 구멍 | 비유 | 실제 문제 |
|---|---|---|
| cv_service 포트가 열려 있음 | 직원 전용 사무실이 길가로 문을 열어 둠 | 누구나 `localhost:8001/analyze`를 부를 수 있음 (Gemini 비용 발생) |
| cv_service에 출입증 검사가 없음 | 문 앞에 경비가 없음 | 터미널 실행 시에는 포트를 닫을 수 없으니 누구나 들어옴 |
| 콜백 주소를 그대로 믿음 | "이 소포 저기로 보내 줘" 하면 주소 확인 없이 배달 | **SSRF**: cv_service를 심부름꾼 삼아 내부망 주소로 요청을 보내게 만들 수 있음 |
| 콜백 토큰을 `!=`로 비교 | 송장 번호를 앞자리부터 대조하다 틀리면 바로 멈춤 | **타이밍 공격**: 응답 시간 차이로 토큰을 한 글자씩 알아낼 수 있음 |
| 완료된 분석에 콜백이 또 와도 받음 | 같은 택배를 두 번 받음 | 탐지 아이템이 두 벌 저장될 수 있음 |
| 업로드 파일을 열어 보지 않음 | 접수처가 소포 속을 확인 안 함 | 이미지가 아닌 파일이나 거대한 파일도 저장됨, 파일이 없으면 500 에러 |
| 피드가 `innerHTML`에 사용자 글을 넣음 | 손님이 쓴 메모를 "명령서"로 읽음 | **XSS**: 댓글에 쓴 `<img onerror=...>`가 코드로 실행됨 |

### 1-2. 바뀐 파일

| 파일 | 바뀐 내용 |
|---|---|
| `docker-compose.yml` | cv_service의 `ports` 삭제 (내부 네트워크에서만 접근) |
| `.env.example`, `cv_service/.env.example` | `INTERNAL_API_TOKEN` 자리 추가 |
| `config/settings.py` | `INTERNAL_API_TOKEN`을 `.env`에서 읽음 (없으면 서버가 안 켜짐) |
| `analysis/tasks.py` | cv_service에 요청할 때 `X-Internal-Token` 헤더를 실어 보냄 |
| `cv_service/app/main.py` | `/analyze` 첫머리에서 출입증 검사(401)와 콜백 주소 검사(400) |
| `cv_service/app/callback.py` | 콜백 주소 허용 목록 검사 함수, `allow_redirects=False` |
| `analysis/views.py` | 콜백: `compare_digest` 비교, 완료된 분석은 409, 늦게 살린 결과는 실패 문구 지움 / 업로드: 이미지 검사 |
| `accounts/views.py` | 프로필 사진 업로드에 같은 이미지 검사 |
| `config/validators.py` (새 파일) | 두 앱이 같이 쓰는 업로드 검사 함수 |
| `templates/base.html`, `static/css/base.css` | 검사 실패 안내(messages)를 보여 주는 빨간 알림 영역 |
| `static/js/feed.js` | 새 댓글·게시물 카드에서 사용자 글을 `textContent`/`append`로 넣음 |
| 테스트 4개 파일 | Django 49 → 57개, cv_service 23 → 30개 |

### 1-3. 요청 한 번이 거치는 검사

```
Celery ── POST /analyze ──▶ cv_service
          헤더: X-Internal-Token
          본문: image, callback_url, callback_token

  cv_service /analyze
   ├─ ① 출입증이 틀리거나, 서버에 정답이 설정 안 됨 → 401 (분석 시작 안 함)
   ├─ ② callback_url의 호스트가 web/localhost/127.0.0.1이 아님 → 400 (분석 시작 안 함)
   ├─ ③ 탐지 → 라벨링 → Gemini 해석
   └─ ④ 결과를 callback_url로 전송 (리다이렉트는 따라가지 않음)

  Django /analysis/api/<id>/callback/
   ├─ ⑤ callback_token이 틀림 → 403
   ├─ ⑥ 이미 완료된 분석 → 409
   └─ ⑦ 저장 (실패 상태였어도 받아서 완료로 살리고 실패 문구 삭제)
```

검사 순서에 이유가 있습니다.
- ①②를 ③보다 **앞**에 둔 이유: 이상한 요청 때문에 무거운 모델 처리와 Gemini 비용이 나가면 안 되니까요.
- ⑤를 ⑥보다 **앞**에 둔 이유: 토큰도 모르는 사람이 403인지 409인지를 보고 "이 분석이 끝났는지"를 알아내면 안 되니까요.

### 1-4. 응답 코드 정리

| 코드 | 어디서 | 뜻 |
|---|---|---|
| 401 | cv_service `/analyze` | 출입증(`X-Internal-Token`)이 없거나 틀림 |
| 400 | cv_service `/analyze` | 출입증은 맞지만 콜백 주소가 허용 목록 밖 |
| 422 | cv_service `/analyze` | 필수 값(`image`, `callback_url`, `callback_token`)이 빠짐 (FastAPI가 자동으로 냄) |
| 403 | Django 콜백 | 콜백 토큰이 틀림 |
| 409 | Django 콜백 | 이미 완료된 분석에 결과가 또 옴 |
| 302 + 빨간 안내 | Django 업로드 2곳 | 파일 없음 / 10MB 초과 / 이미지가 아님 → 원래 화면으로 돌려보냄 |

### 1-5. 환경변수

| 변수 | 파일 | 설명 |
|---|---|---|
| `INTERNAL_API_TOKEN` | `.env` **와** `cv_service/.env` | 두 파일에 **같은 값**. Django는 없으면 서버가 안 켜지고(`KeyError`), cv_service는 없으면 모든 분석 요청을 401로 거절 |

만드는 법: `python -c "import secrets; print(secrets.token_hex(32))"`

compose는 손대지 않았습니다. `web`/`celery`는 이미 `env_file: .env`로, `cv_service`는 `env_file: ./cv_service/.env`로 파일 전체를 받고 있어서, 각 `.env`에 줄만 추가하면 됩니다. 터미널 실행(방법 2)에서도 cv_service가 `cv_service/.env`를 읽으니까 두 파일에 넣는 게 가장 단순합니다.

### 1-6. 확인한 것

| 확인 | 결과 |
|---|---|
| 내 컴퓨터에서 `curl http://localhost:8001/health` | 연결 거부 (포트 닫힘) |
| `web` 컨테이너 안에서 `http://cv_service:8001/health` | `{"status":"ok"}` (내부는 통함) |
| `web` 컨테이너 안에서 출입증 없이 `/analyze` (필수 값은 채움) | 401 |
| 브라우저에서 AI 분석 (게시물 기반 / 독립 업로드) | 끝까지 완료 |
| `.txt`를 `.jpg`로 바꿔 AI 분석·프로필 사진에 업로드 | 빨간 안내, 저장 안 됨 |
| 댓글·캡션에 `<img src=x onerror=alert(1)>` | 알림창 없이 글자로 보임 |
| Django 테스트 | 57개 통과 |
| cv_service 테스트 | 30개 통과 |

---

## 2. 구성요소 단위 코드리뷰

### 2-1. `docker-compose.yml`: cv_service `ports` 삭제

- **좋은 점:** compose가 만드는 내부 네트워크는 `ports`와 상관없이 살아 있어서, `web`/`celery`는 `http://cv_service:8001`로 그대로 접근합니다. 코드는 한 줄도 안 바꾸고 외부 노출만 없앴습니다.
- **한계:** compose로 띄울 때만 효과가 있습니다. 터미널 실행에서는 `localhost:8001`이 그대로 열려 있으므로 2-2의 출입증 검사가 꼭 필요합니다.
- **대가:** compose 모드에서는 cv_service의 Swagger(`/docs`)를 브라우저로 못 봅니다. README에 "터미널 실행 시에만 확인 가능"이라고 적었습니다.

### 2-2. cv_service `/analyze`: 출입증 검사

```python
x_internal_token: str = Header(default="")
...
expected = os.environ.get("INTERNAL_API_TOKEN", "")
if not expected or not secrets.compare_digest(x_internal_token.encode(), expected.encode()):
    raise HTTPException(status_code=401, ...)
```

- **`Header(default="")`:** FastAPI는 변수 이름의 `_`를 `-`로 바꿔서 헤더를 찾습니다(`x_internal_token` → `X-Internal-Token`). 기본값을 빈 문자열로 둔 이유는 헤더가 없을 때 FastAPI의 422 대신 **우리가 정한 401**이 나가게 하려는 것입니다.
- **`if not expected` (fail closed):** 이 줄이 없으면 서버에 토큰 설정을 깜빡했을 때 `"" == ""`로 **모두 통과**합니다. "설정이 없으면 문을 잠근다"가 안전한 기본값입니다.
- **`compare_digest`:** 2-6에서 자세히 설명합니다.
- **`.encode()`:** `compare_digest`는 문자열에 비ASCII 글자(한글 등)가 있으면 `TypeError`를 냅니다. 바이트로 바꿔 비교해서 이상한 헤더가 와도 500이 아니라 401로 끝나게 했습니다.
- **Django는 `os.environ[...]`, cv_service는 `os.environ.get(...)`인 이유:** Django는 서버가 켜질 때 바로 멈추는 게 가장 확실합니다(`SECRET_KEY`와 같은 방식). cv_service는 모듈을 불러올 때 읽으면 테스트가 환경변수를 바꿔 끼우기 어려워서, 요청마다 읽고 비어 있으면 거절하도록 했습니다. 둘 다 결과적으로 "설정 없으면 막힘"입니다.
- **아쉬운 점:** 필수 값이 빠진 요청은 출입증 검사 전에 FastAPI가 422로 먼저 돌려보냅니다(5-2 참고). 422 응답에 필수 필드 이름이 보이긴 하지만, 분석은 시작되지 않으니 지금은 그대로 뒀습니다. 순서를 바꾸고 싶으면 출입증 검사를 `Depends`(의존성)로 옮기면 됩니다.

### 2-3. `callback.py`: `is_allowed_callback_url`

```python
ALLOWED_CALLBACK_HOSTS = {"web", "localhost", "127.0.0.1"}
parsed = urlparse(callback_url)
return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_CALLBACK_HOSTS
```

- **왜 문자열 검사(`"web" in url`)가 아니라 `urlparse`인가:** 문자열 검사는 `http://web.evil.com`, `http://evil.com/?q=web`, `http://localhost@evil.com`을 다 통과시킵니다. `urlparse(...).hostname`은 진짜 호스트(`web.evil.com`, `evil.com`, `evil.com`)만 꺼내 주고, 대문자도 소문자로 바꿔 줍니다.
- **`scheme` 검사:** `file:///etc/passwd` 같은 다른 종류의 주소를 막습니다.
- **허용 목록을 설정값이 아닌 상수로 둔 이유:** 바뀔 일이 없는 값이라 `.env`로 빼면 관리할 것만 늘어납니다. 배포하면서 주소가 바뀌면 그때 환경변수로 빼면 됩니다.
- **검사 위치를 `send_callback`이 아니라 `/analyze` 첫머리로 바꾼 이유:** 처음 계획은 보낼 때 검사하는 것이었는데, 그러면 탐지·라벨링·Gemini를 다 끝낸 뒤에야 거절하게 됩니다. 함수는 콜백 담당 파일(`callback.py`)에 두고, 호출만 앞쪽에서 합니다.
- **한계:** 호스트만 보고 포트는 안 봅니다. `http://localhost:6379`처럼 같은 호스트의 다른 포트로는 보낼 수 있습니다. 다만 cv_service 컨테이너 안의 `localhost`는 cv_service 자신이고, 출입증(2-2)이 있어야 여기까지 올 수 있으니 지금은 충분하다고 봤습니다.

### 2-4. `send_callback`: `allow_redirects=False`

- `requests.post`는 기본적으로 3xx(다른 곳으로 가라는 응답)를 **따라갑니다.** 허용된 주소가 `302 → http://evil.com`이라고 답하면 결국 허용 목록 밖으로 가게 되니까 꺼 둡니다.
- Django 콜백은 원래 리다이렉트를 안 하니까 정상 흐름에는 영향이 없습니다.

### 2-5. `analysis/tasks.py`: 헤더 추가

- `headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN}` 한 줄이 전부입니다.
- **커밋 순서:** Django가 헤더를 **보내는** 커밋을 먼저, cv_service가 **검사하는** 커밋을 나중에 했습니다. 반대로 하면 그 사이 커밋에서는 모든 분석이 401로 막힙니다. 커밋 하나하나가 "동작하는 상태"가 되도록 순서를 정한 것입니다.

### 2-6. `analysis_callback`: `compare_digest` + 409

```python
sent_token = str(data.get("callback_token", ""))
if not secrets.compare_digest(sent_token.encode(), analysis.callback_token.encode()):
    return JsonResponse(..., status=403)
if analysis.status == Analysis.STATUS_COMPLETED:
    return JsonResponse(..., status=409)
```

- **`!=` 대신 `compare_digest`:** `!=`는 앞 글자부터 비교하다가 다른 글자를 만나면 바로 멈춥니다. 그래서 "첫 글자가 맞으면 아주 조금 더 늦게" 답이 옵니다. 공격자가 이 차이를 수천 번 재면 한 글자씩 맞혀 갈 수 있습니다. `compare_digest`는 맞든 틀리든 끝까지 비교해서 시간이 항상 같습니다.
- **`str(...)`:** 토큰 자리에 숫자나 `null`이 와도 500 없이 403으로 끝납니다.
- **409를 403 뒤에 둔 이유:** 1-3에서 설명했습니다.
- **`failed`는 막지 않은 이유 (정책 결정):** 6분 기준으로 실패 처리됐지만 실제로는 분석이 조금 늦게 끝난 경우, 결과를 버리는 것보다 살리는 게 사용자에게 낫습니다. 한 번 받으면 `completed`가 되니까 그다음 콜백은 409에 걸립니다. 결과적으로 **토큰이 한 번만 쓰이는** 효과가 납니다.
- **`error_message = ""`:** 늦게 살린 결과에 "시간이 초과되었습니다" 문구가 남아 있지 않게 지웁니다. 이 줄이 빠졌을 때 새 테스트가 바로 잡아냈습니다.
- **알고 둔 한계 (`ponytail:` 주석):** 콜백 두 개가 **정확히 같은 순간**에 오면 둘 다 "아직 완료 아님"을 보고 통과할 수 있습니다. cv_service는 콜백을 한 번만 보내니까 지금은 과한 걱정이고, 필요해지면 `select_for_update()`로 DB 행을 잠그면 됩니다.
- **기존에도 반쯤 막혀 있었던 것:** `StyleScore`는 "한 분석에 같은 스타일 이름 중복 금지" DB 규칙이 있어서, 중복 콜백은 스타일 저장에서 에러가 나 되돌려지는 경우가 많았습니다. 하지만 스타일 점수가 비어 있으면 그대로 통과했습니다. "우연히 막힘"을 "의도해서 막음"으로 바꾼 것입니다.

### 2-7. `config/validators.py`: `validate_uploaded_image`

- **`forms.ImageField().clean(file)`:** Django에 이미 들어 있는 이미지 검사를 **필드 하나만 꺼내서** 빌려 씁니다. Pillow로 실제로 열어 보기 때문에 확장자만 바꾼 가짜 파일은 여기서 걸립니다. 직접 Pillow 코드를 쓸 필요가 없습니다. 검사가 끝나면 파일 읽는 위치를 맨 앞으로 되돌려 주니까, 그다음 저장도 정상입니다.
- **크기 검사를 이미지 검사보다 먼저 한 이유:** `file.size`는 숫자 하나 보는 거라 공짜이고, 이미지 검사는 파일을 엽니다. 큰 파일은 열기 전에 거절합니다.
- **`config/`에 둔 이유:** `analysis`와 `accounts` 두 앱이 같이 쓰니까 어느 한 앱에 두면 다른 앱이 남의 앱을 import하게 됩니다.
- **"모델에 `ImageField`가 있는데 왜 검사가 안 됐나?"** 모델의 `ImageField`는 "이미지 경로를 저장하는 칸"입니다. 진짜 이미지인지 확인하는 건 **폼**이 할 일인데, 뷰가 폼을 거치지 않고 바로 모델에 넣고 있어서 검사가 한 번도 일어나지 않았습니다.
- **범위 밖:** 게시물 작성 API(`posts`)는 DRF 시리얼라이저가 이미 이미지인지 검사합니다. 크기 제한은 없지만, 나중에 nginx의 `client_max_body_size`로 모든 업로드에 한 번에 걸 예정입니다.

### 2-8. 업로드 뷰 2곳 + messages

- **`request.FILES["image"]` → `.get("image")`:** 파일 없이 제출하면 `KeyError`로 500이 나던 것을 `None`으로 받아서 검사 함수가 "사진을 선택해 주세요"로 처리합니다.
- **실패 시 아무것도 만들지 않음:** 분석 업로드는 `Analysis`도 만들지 않고 Celery에 일도 넘기지 않습니다. 가짜 파일이 cv_service까지 가지 않습니다.
- **messages를 쓴 이유:** 실패하면 `redirect`로 원래 화면에 돌려보내는데, 리다이렉트를 하면 새 요청이 되어 변수를 넘길 수 없습니다. messages는 "다음 화면에서 한 번만 보여 줄 쪽지"를 세션에 넣어 두는 Django 기본 기능입니다. 이미 설치돼 있었고 화면에 보여 주는 곳만 없었으므로, `base.html`에 한 번 넣어서 모든 페이지에서 쓸 수 있게 했습니다.
- **HTML의 `accept="image/*"`만으로 안 되는 이유:** 파일 선택 창의 필터일 뿐이라 curl이나 개발자 도구로 보내면 아무 효과가 없습니다. 검사는 항상 서버에서 해야 합니다.

### 2-9. `feed.js`: `textContent` / `append` / `.alt`

- **뼈대는 `innerHTML`, 사용자 글은 따로:** 카드 구조는 우리가 쓴 고정 HTML이라 안전합니다. 그 안에 사용자가 쓴 글(댓글 내용, 캡션)만 나중에 글자로 채웁니다.
- **캡션을 `textContent`가 아니라 `append`로 넣은 이유:** `<p><strong>아이디</strong> 캡션</p>` 구조에서 `p.textContent = 캡션`을 하면 `<strong>`까지 지워집니다. `append(문자열)`은 글자 덩어리 하나를 뒤에 붙이기만 합니다.
- **`alt`도 직접 대입:** 속성 자리도 위험합니다. 캡션에 `" onerror="alert(1)`을 쓰면 따옴표를 닫고 새 속성을 만들 수 있습니다. `img.alt = 캡션`으로 대입하면 브라우저가 통째로 값으로만 취급합니다.
- **`comment.user`, `post.user`를 그대로 둔 이유:** Django 아이디는 영문·숫자·`@.+-_`만 허용되어 `<`나 `"`가 들어갈 수 없습니다. `post.id`(숫자), `post.image`(서버가 만든 주소)도 마찬가지입니다.
- **위험도가 낮았던 이유 (self-XSS):** 이 카드는 글쓴이 본인 화면에서만 JS로 그려집니다. 새로고침하면 Django 템플릿이 자동으로 `<`를 `&lt;`로 바꿔서(자동 이스케이프) 다른 사람에게는 안전하게 보입니다. 그래도 위험한 패턴이라 고쳤습니다. 같은 파일의 댓글 **수정** 기능은 원래부터 `textContent`를 쓰고 있었고, 이번에 새 댓글 쪽도 같은 방식으로 맞췄습니다.

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `cv_service/app/callback.py` (전체)

```python
import requests  # Django 콜백 주소로 HTTP 요청을 보낼 때 씀
from urllib.parse import urlparse  # 주소를 "http / web / 8000 / 경로"처럼 부분별로 쪼개 주는 표준 도구
from .schemas import CallbackPayload  # 보낼 데이터의 모양을 정의해둔 스키마

ALLOWED_CALLBACK_HOSTS = {"web", "localhost", "127.0.0.1"}  # 결과를 보내도 되는 곳: compose의 Django(web), 터미널 실행 시 내 컴퓨터


def is_allowed_callback_url(callback_url: str) -> bool:  # 콜백 주소를 받아 True/False를 돌려주는 함수
    """콜백 주소가 http(s)이고, 호스트가 허용 목록에 있을 때만 True"""
    parsed = urlparse(callback_url)  # 주소를 부분별로 쪼갬 (scheme="http", hostname="web", port=8000, path="/...")
    return parsed.scheme in ("http", "https") and parsed.hostname in ALLOWED_CALLBACK_HOSTS  # 종류가 http(s)이고 호스트가 목록 안이어야 True


def send_callback(callback_url: str, payload: CallbackPayload):  # 분석 결과를 Django에 보내는 함수
    response = requests.post(  # POST 요청 보내기 시작
        callback_url,  # 보낼 주소 (이미 /analyze 첫머리에서 허용 목록 검사를 통과한 주소)
        json=payload.model_dump(),  # Pydantic 객체를 dict로 바꿔서 JSON으로 전송
        timeout=10,                 # 10초 넘으면 포기
        allow_redirects=False,      # "다른 데로 가세요"(3xx) 응답을 따라가지 않음 → 허용 목록 우회 방지
    )  # 요청 끝
    response.raise_for_status()  # Django가 저장에 실패하면 예외 발생 → /analyze가 500으로 응답 → Celery가 실패로 기록
```

### 3-2. `cv_service/app/main.py` (바뀐 부분)

```python
from fastapi import FastAPI, UploadFile, Form, Header, HTTPException  # Header: 요청 헤더 값 받기, HTTPException: 에러 응답 보내기
from .callback import send_callback, is_allowed_callback_url  # Django로 결과 보내는 함수 + 콜백 주소 검사
import os  # 환경변수(INTERNAL_API_TOKEN)를 읽을 때 씀
import secrets  # 토큰을 안전하게(상수 시간으로) 비교할 때 씀

@app.post("/analyze")  # POST /analyze 요청을 이 함수가 처리
def analyze(  # 분석 요청을 받는 함수 (아래 4개가 요청에서 꺼낼 값)
    image: UploadFile,  # 업로드된 사진 파일
    callback_url: str = Form(...),  # 결과를 돌려보낼 주소 (필수)
    callback_token: str = Form(...),  # Django가 결과를 검증할 토큰 (필수)
    x_internal_token: str = Header(default=""),  # "X-Internal-Token" 헤더 값 (없으면 빈 문자열)
):  # 함수 본문 시작
    expected = os.environ.get("INTERNAL_API_TOKEN", "")  # 내가 알고 있는 정답 출입증 (설정 안 됐으면 빈 문자열)
    if not expected or not secrets.compare_digest(x_internal_token.encode(), expected.encode()):  # 정답이 설정 안 됐거나, 보낸 값이 다르면
        raise HTTPException(status_code=401, detail="invalid internal token")  # 분석 시작 전에 거절
    if not is_allowed_callback_url(callback_url):  # 결과를 보낼 주소가 허용 목록 밖이면
        raise HTTPException(status_code=400, detail="callback_url not allowed")  # Gemini를 시작하기 전에 거절
    pil_image = Image.open(image.file).convert("RGB")  # (여기부터는 기존 분석 흐름 그대로)
```

### 3-3. `config/settings.py` (추가한 줄)

```python
INTERNAL_API_TOKEN = os.environ["INTERNAL_API_TOKEN"]  # cv_service에 요청할 때 보내는 내부 출입증. 없으면 서버가 아예 안 켜짐(KeyError)
```

### 3-4. `analysis/tasks.py` (추가한 줄)

```python
                files={"image": image_file},                                  # 실제 이미지 파일
                headers={"X-Internal-Token": settings.INTERNAL_API_TOKEN},    # cv_service가 확인할 내부 출입증
                timeout=ANALYZE_TIMEOUT,                                       # 이 시간 넘게 답이 없으면 포기
```

### 3-5. `analysis/views.py`: `analysis_callback` (바뀐 부분)

```python
    data = json.loads(request.body)                              # 요청 본문(bytes 형태 JSON 문자열)을 dict로 변환

    sent_token = str(data.get("callback_token", ""))              # 요청에 실린 토큰 (없으면 빈 문자열, 숫자 등이 와도 글자로 바꿈)
    if not secrets.compare_digest(sent_token.encode(), analysis.callback_token.encode()):  # 끝까지 다 비교해서 시간 차이로 정답이 새지 않게 함
        return JsonResponse({"error": "invalid token"}, status=403)  # 안 맞으면 403(권한 없음)으로 거부하고 종료

    if analysis.status == Analysis.STATUS_COMPLETED:                # 토큰은 맞지만 이미 결과가 저장된 분석이면 (같은 콜백이 또 온 경우)
        return JsonResponse({"error": "already completed"}, status=409)  # 409(충돌): 결과를 두 벌 저장하지 않도록 거절
    # ponytail: 콜백 두 개가 정확히 동시에 오면 둘 다 이 검사를 통과할 수 있음. cv_service는 한 번만 보내므로 지금은 충분하고, 필요해지면 select_for_update로 행 잠금

    # ... (아이템·스타일 저장은 기존 그대로) ...
            analysis.interpretation = data.get("interpretation", "")     # LLM 해석 텍스트 채우기
            analysis.status = Analysis.STATUS_COMPLETED                    # 상태를 "완료"로 변경
            analysis.error_message = ""                                     # 늦게 도착해 살린 결과라면 남아 있던 실패 문구를 지움
            analysis.save()                                                 # 변경사항 DB에 저장 (여기까지 와야 묶음 전체가 확정됨)
```

### 3-6. `config/validators.py` (전체)

```python
from django import forms  # Django 폼 도구 (이미지 검사 기능이 들어 있음)
from django.core.exceptions import ValidationError  # "검사 실패"를 알리는 Django 표준 에러

MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 업로드 최대 크기: 10MB (1024*1024 바이트 = 1MB)


def validate_uploaded_image(file):  # 업로드 파일 하나를 받아 검사하는 함수 (통과하면 아무것도 안 돌려줌)
    """업로드 파일이 있고, 10MB 이하이고, 진짜 이미지인지 확인. 하나라도 아니면 ValidationError"""
    if file is None:  # 파일 없이 제출된 경우
        raise ValidationError("사진을 선택해 주세요.")  # 안내 문구와 함께 실패 알림
    if file.size > MAX_UPLOAD_SIZE:  # 크기 검사를 먼저: 큰 파일을 굳이 열어 보지 않도록
        raise ValidationError("사진은 10MB 이하만 올릴 수 있습니다.")  # 크기 초과 안내
    forms.ImageField().clean(file)  # Pillow로 실제로 열어 보고, 이미지가 아니면 ValidationError ("올바른 이미지를 업로드하세요...")
```

### 3-7. `analysis/views.py`: `upload_and_analyze` (바뀐 부분)

```python
from django.contrib import messages                          # 화면에 한 번 보여 줄 안내 문구를 남기는 도구
from django.core.exceptions import ValidationError           # 검사 실패 에러
from config.validators import validate_uploaded_image        # 업로드 사진 검사 함수

def upload_and_analyze(request):                                # 독립 업로드 분석 요청을 처리하는 뷰
    image = request.FILES.get("image")                          # [...] 대신 .get(): 파일이 없으면 KeyError(500) 대신 None
    try:                                                          # 검사 중 실패하면 아래 except로
        validate_uploaded_image(image)                            # 있음 / 10MB 이하 / 진짜 이미지인지 검사
    except ValidationError as error:                              # 검사에 걸렸으면
        messages.error(request, error.messages[0])                 # 실패 이유(첫 번째 문구)를 화면에 보여 주도록 남김
        return redirect("analysis:home")                           # 업로드 화면으로 돌려보냄 (분석은 만들지 않음)
    analysis = Analysis.objects.create(                          # (여기부터 기존 그대로) 검사를 통과한 사진으로 분석 생성
```

### 3-8. `accounts/views.py`: `update_profile_photo` (전체)

```python
@login_required(login_url="accounts:login_page")                   # 로그인 안 했으면 로그인 페이지로
@require_POST                                                       # POST 요청만 허용
def update_profile_photo(request):                                  # 프로필 사진 변경 뷰
    image = request.FILES.get("profile_image")                   # 파일이 없으면 None (KeyError 방지)
    try:                                                          # 검사 중 실패하면 아래 except로
        validate_uploaded_image(image)                             # 분석 업로드와 같은 검사
    except ValidationError as error:                              # 검사에 걸렸으면
        messages.error(request, error.messages[0])                  # 실패 이유를 화면에 보여 주도록 남김
        return redirect("accounts:mypage")                          # 마이페이지로 돌려보내고 안내 표시

    request.user.profile_image = image                              # 검사를 통과한 사진을 프로필 사진 칸에 넣음
    request.user.save()                                             # DB에 저장
    return redirect("accounts:mypage")                              # 마이페이지로 이동
```

### 3-9. `templates/base.html` (추가한 부분)

```html
    <main>                                                    {# 페이지 본문 영역 #}
        {% if messages %}                                     {# 뷰에서 messages.error(...)로 남긴 안내가 있으면 #}
        <ul class="messages">                                 {# 안내 목록 상자 #}
            {% for message in messages %}                     {# 남아 있는 안내를 하나씩 꺼냄 #}
            <li class="messages__item">{{ message }}</li>       {# 한 번 보여 주면 자동으로 지워짐 #}
            {% endfor %}                                      {# 반복 끝 #}
        </ul>                                                 {# 목록 끝 #}
        {% endif %}                                           {# 안내가 없으면 위 상자 자체를 안 그림 #}
        {% block content %}{% endblock %}                     {# 각 페이지 본문이 들어오는 자리 #}
    </main>
```

### 3-10. `static/css/base.css` (추가한 부분)

```css
.messages {                                         /* 뷰가 남긴 안내 문구 영역 (업로드 실패 등) */
    list-style: none;                               /* 목록 앞의 점 없애기 */
    margin: 0;                                      /* 바깥 여백 없음 */
    padding: var(--space-md) var(--space-md) 0;     /* 위·좌우 16px 안쪽 여백, 아래는 0 */
}

.messages__item {                                   /* 안내 한 줄 */
    padding: var(--space-sm) var(--space-md);       /* 위아래 8px, 좌우 16px 안쪽 여백 */
    border-radius: var(--radius-sm);                /* 살짝 둥근 모서리 */
    background: #fdecec;                            /* 옅은 빨강 배경: 문제가 있다는 신호 */
    color: #b42318;                                 /* 진한 빨강 글자 */
}
```

### 3-11. `static/js/feed.js` (바뀐 부분)

백틱(`` ` ``) 안은 문자열이라 `//` 주석을 쓰면 그대로 화면에 찍힙니다. 그래서 문자열 안쪽 줄의 설명은 코드 위에 따로 적었습니다.

**새 댓글**

```js
        // 고정 뼈대만 HTML로 채움. 아이디(comment.user)는 안전한 글자만 허용돼 그대로 쓰고, 내용(<span>) 자리는 비워 둠
        item.innerHTML = `
            <strong>
                <a href="/accounts/mypage/${comment.user}/" class="comment-list__username">${avatarImg}${comment.user}</a>
            </strong>
            <span class="comment-list__content"></span>
            <button class="comment-edit-button">수정</button>
            <button class="comment-delete-button">삭제</button>
        `;
        item.querySelector(".comment-list__content").textContent = comment.content;  // 사용자가 쓴 글은 HTML로 해석되지 않게 글자로만 넣음 (XSS 방지)
        list.appendChild(item);  // 만든 <li>를 목록 맨 끝에 실제로 붙임
```

**새 게시물**

```js
        // 고정 뼈대만 HTML로 채움. 사진의 alt와 캡션 자리는 비워 두고 아래에서 글자로 채움 (... 부분은 기존과 같음)
        article.innerHTML = `
            ...
            <img class="post-card__image" src="${post.image}" alt="">
            ...
            <p class="post-card__caption"><strong>${post.user}</strong> </p>
        `;
        article.querySelector(".post-card__image").alt = post.caption;    // 속성에 넣을 때도 직접 대입하면 글자로만 들어감
        uploadForm.after(article);  // 업로드 폼 바로 다음(=피드 맨 위)에 새 카드를 끼워 넣음
        article.querySelector(".post-card__caption").append(post.caption); // append(문자열)은 글자 덩어리로 붙임 → 태그로 해석 안 됨
```

### 3-12. 대표 테스트

**cv_service: 속임수 주소가 막히는지** (`cv_service/tests/test_callback.py`)

```python
    def test_tricky_urls_are_blocked(self):  # 이름만 비슷하거나 숨겨 놓은 주소는 막히는지 확인
        """이름만 비슷하거나 숨겨 놓은 주소는 막힘"""
        for url in (  # 아래 주소들을 하나씩 검사
            "http://evil.com/",                  # 그냥 외부 주소
            "http://web.evil.com/",              # 앞부분만 web
            "http://evil.com/?q=web",            # 뒤에 web을 숨김
            "http://localhost@evil.com/",        # @ 앞은 사용자 이름이라 진짜 호스트는 evil.com
            "http://169.254.169.254/latest/",    # 클라우드 서버의 비밀 정보 주소
            "file:///etc/passwd",                # http가 아닌 주소
            "",                                  # 빈 값
        ):  # 목록 끝
            with self.subTest(url=url):  # 하나가 실패해도 나머지도 검사하고, 어느 주소가 실패했는지 알려 줌
                self.assertFalse(is_allowed_callback_url(url))  # 전부 False여야 함
```

**Django: 늦게 온 콜백을 살리는지** (`analysis/tests.py`)

```python
    def test_late_callback_on_failed_analysis_is_accepted(self):  # 실패 처리 뒤 늦게 온 결과를 받는지 확인
        mark_failed(self.analysis.id, "분석 시간이 초과되었습니다.")  # 6분이 지나 실패 처리된 상황

        response = self.post_callback(self.payload)  # 그 뒤에 결과가 늦게 도착

        self.assertEqual(response.status_code, 200)  # 받아들여야 함
        self.analysis.refresh_from_db()  # DB에서 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.status, Analysis.STATUS_COMPLETED)  # 완료로 살아나야 함
        self.assertEqual(self.analysis.error_message, "")  # 실패 문구는 지워져야 함
        self.assertEqual(self.analysis.detected_items.count(), 1)  # 결과도 저장돼야 함
```

**Django: 크기 한도를 테스트 동안만 낮추기** (`analysis/tests.py`)

```python
    @patch("config.validators.MAX_UPLOAD_SIZE", 10)  # 진짜 10MB 파일을 만들긴 무거우니, 테스트 동안만 한도를 10바이트로 낮춤
    def test_upload_too_large_is_rejected(self, mock_task):  # 클래스의 @patch가 넘겨 주는 mock_task 하나만 받음 (값을 직접 준 @patch는 인자를 안 늘림)
        self.client.force_login(self.user)  # 로그인한 상태로
        response = self.client.post(reverse("analysis:upload"), {"image": generate_test_image()})  # 진짜 이미지지만 10바이트보다 큼

        self.assertEqual(Analysis.objects.count(), 1)  # setUp의 1건 말고 새로 만들어지면 안 됨
        mock_task.delay.assert_not_called()  # 분석 요청도 가면 안 됨
        self.assertIn("10MB", str(list(get_messages(response.wsgi_request))[0]))  # 크기 안내 문구여야 함
```

---

## 4. 복습

### SSRF: 남의 서버를 심부름꾼으로 쓰기
서버가 "사용자가 준 주소로 요청을 보내는" 기능을 갖고 있으면, 공격자는 그 서버만 닿을 수 있는 주소(내부망, 클라우드 비밀 정보 주소 `169.254.169.254` 등)를 넣어서 대신 두드리게 만듭니다. 막는 방법은 **보낼 곳을 허용 목록으로 제한**하고, 리다이렉트로 우회하지 못하게 하는 것입니다.

### 주소 검사는 문자열이 아니라 "쪼개서"
`"web" in url`은 `web.evil.com`도 통과시킵니다. `urlparse(url).hostname`으로 진짜 호스트만 꺼내서 **정확히 일치**하는지 봐야 합니다. `@` 앞은 사용자 이름이라는 것처럼, 주소에는 사람이 보기에 헷갈리는 규칙이 많아서 직접 자르지 말고 표준 도구에 맡깁니다.

### 타이밍 공격과 `compare_digest`
`==`는 "틀린 글자를 찾는 순간 멈추는" 비교입니다. 그래서 몇 글자째까지 맞았는지가 응답 시간에 묻어 나옵니다. 비밀번호·토큰 같은 비밀값은 항상 끝까지 비교하는 `secrets.compare_digest`로 비교합니다. 비교하는 시간이 같으니 시간으로는 아무 힌트도 얻을 수 없습니다.

### fail closed: 설정이 없으면 잠근다
"토큰이 설정돼 있으면 검사한다"로 짜면, 설정을 깜빡한 날 문이 열립니다. "토큰이 없으면 전부 거절"로 짜야 실수해도 안전한 쪽으로 망가집니다.

### 401 / 400 / 403 / 409 / 422
- **401** "누구세요?" (신원 확인 실패, 출입증 없음)
- **403** "누군지는 알겠는데 안 돼요" (권한 없음, 여기서는 콜백 토큰 틀림)
- **400** "요청 내용이 이상해요" (허용 안 된 콜백 주소)
- **409** "지금 상태랑 안 맞아요" (이미 끝난 분석에 결과가 또 옴)
- **422** "필수 칸이 비었어요" (FastAPI가 자동으로 냄)

### 검사 순서 = 정보 노출 순서
토큰 검사보다 상태 검사를 먼저 하면, 토큰이 없는 사람도 응답 코드 차이(403 vs 409)로 "이 분석은 끝났구나"를 알 수 있습니다. **신원 확인이 항상 먼저**입니다. 또 비싼 일(분석, Gemini) 앞에 싼 검사(헤더, 주소)를 둡니다.

### 모델 `ImageField` vs 폼 `ImageField`
모델의 `ImageField`는 "파일 경로를 저장하는 칸"이고, 진짜 이미지인지 확인하는 건 폼의 `ImageField`입니다. 뷰에서 `request.FILES`를 바로 모델에 넣으면 검사가 한 번도 일어나지 않습니다. 폼 전체가 필요 없으면 `forms.ImageField().clean(file)`처럼 필드 하나만 빌려 써도 됩니다.

### `accept="image/*"`는 보안이 아니다
HTML의 `accept`, `required`, JS 검사는 **사용자 편의**용입니다. 브라우저를 거치지 않는 요청(curl 등)에는 효과가 없으니 같은 검사를 서버에서 반드시 다시 합니다.

### Django messages: 다음 화면에 한 번 보여 줄 쪽지
`redirect`를 하면 새 요청이 되어 변수를 넘길 수 없습니다. `messages.error(request, "...")`는 쪽지를 세션에 넣어 두고, 다음 화면이 `{% for message in messages %}`로 꺼내 보여 주면 자동으로 지워집니다.

### `innerHTML` vs `textContent`
- `innerHTML = "<b>안녕</b>"` → **굵은** "안녕" (HTML로 해석, 코드도 실행될 수 있음)
- `textContent = "<b>안녕</b>"` → 화면에 `<b>안녕</b>`이라는 글자 그대로

사용자가 쓴 글은 항상 `textContent`나 `append(문자열)`, 속성은 `요소.속성 = 값`으로 넣습니다. Django 템플릿은 `{{ }}`가 자동으로 이스케이프해 주지만, JS로 직접 그릴 때는 그 보호가 없습니다.

### compose 내부 네트워크와 `ports`
compose는 서비스끼리 이름으로 부를 수 있는 내부 네트워크를 자동으로 만듭니다. `ports`는 그 네트워크와 **내 컴퓨터 바깥**을 잇는 문입니다. 서비스끼리만 쓰는 서버(cv_service, db)는 `ports`를 열 필요가 없습니다.

### 이미지에 구운 코드는 재빌드해야 바뀐다
루트 `Dockerfile`의 `COPY . .`는 빌드하는 순간의 코드를 이미지에 복사합니다. 코드를 고친 뒤 브라우저로 확인하려면 `docker compose up --build`가 필요합니다. 테스트(`manage.py test`)는 내 컴퓨터 코드를 바로 읽으니 재빌드가 필요 없습니다.

### 커밋 순서도 설계다
"보내는 쪽"을 먼저, "검사하는 쪽"을 나중에 커밋하면 중간 어느 커밋으로 돌아가도 프로그램이 동작합니다. 반대로 하면 그 사이 커밋은 깨진 상태가 됩니다.

---

## 5. 트러블슈팅

### 5-1. 포트를 닫은 뒤 내부 접속도 `Connection refused`
- **증상:** `ports`를 지우고 `docker compose up` 직후, `web` 컨테이너 안에서 `http://cv_service:8001/health`를 불렀더니 `ConnectionRefusedError`가 났습니다.
- **원인:** 포트 문제가 아니라 **cv_service가 아직 켜지는 중**이었습니다. cv_service는 서버 문을 열기 전에 Hugging Face에서 모델을 받아 메모리에 올립니다. 로그 마지막 줄이 `You are sending unauthenticated requests to the HF Hub`였고, `Uvicorn running on ...` 줄은 아직 없었습니다.
- **구분법:** 에러가 `Name or service not known`이 아니라 `Connection refused`라는 건, 이름(`cv_service`)은 찾았고 네트워크도 정상이지만 그 안에서 기다리는 프로그램이 아직 없다는 뜻입니다.
- **해결:** `docker compose logs -f cv_service`로 `Uvicorn running`이 뜰 때까지 기다린 뒤 다시 확인 → `{"status":"ok"}`.

### 5-2. 출입증 확인 명령이 401이 아니라 422
- **증상:** `requests.post('http://cv_service:8001/analyze')`(본문 없이)를 보냈더니 401이 아니라 422가 나왔습니다.
- **원인:** FastAPI는 함수 본문을 실행하기 **전에** 필수 값(`image`, `callback_url`, `callback_token`)부터 검사합니다. 아무것도 안 보냈으니 거기서 422로 돌려보냈고, 함수 첫 줄의 출입증 검사는 실행되지도 않았습니다. 확인 명령을 잘못 만든 것이었습니다.
- **해결:** 필수 값은 채우고 출입증만 빼서 보내도록 명령을 바꿨습니다 → 401. 이때 가짜 이미지(`b'x'`)를 넣었기 때문에, 예전 코드가 돌고 있었다면 이미지 열기에서 500이 났을 겁니다. 그래서 "새 코드가 반영됐는지"까지 한 번에 구분할 수 있었습니다.
- **배운 점:** 동작을 확인하는 명령은 "확인하려는 검사까지 실제로 도달하는지"부터 따져야 합니다.

### 5-3. 설계 변경: 콜백 주소 검사 위치
- **처음 계획:** `send_callback`(결과를 보낼 때)에서 검사.
- **문제:** 그러면 탐지·라벨링·**Gemini 호출(비용)**을 다 끝낸 뒤에야 거절합니다.
- **변경:** 검사 함수는 `callback.py`에 두되, 호출은 `/analyze` 첫머리(출입증 검사 바로 다음)로 옮겼습니다. 그 결과 기존 테스트의 콜백 주소(`http://django/callback/`)가 허용 목록 밖이 되어, `http://web:8000/callback/`으로 바꿨습니다.

### 남은 과제 (이번 브랜치에서는 하지 않음)
- 동시에 도착한 중복 콜백: 필요해지면 `select_for_update()`로 행 잠금 (코드에 `ponytail:` 주석으로 표시).
- 게시물 작성 API의 업로드 크기 제한: 배포 단계(점검표 10번)에서 nginx `client_max_body_size`로 전체 적용.
- 콜백 본문이 JSON이 아니면 `json.loads`에서 500: 토큰 검사 전이라 저장되는 건 없지만, 400으로 정리할 수 있음.
- 콜백 허용 목록은 호스트만 보고 포트는 보지 않음 (2-3 참고).
- 다음 묶음(C 브랜치): 분석 결과에 `Analysis.user` 연결, 업로드 파일 이름을 UUID로, 로그인 시도 횟수 제한.
