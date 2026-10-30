# Mini Project 1 — 패션 SNS

Django(+DRF)로 웹/API 서버를 구성하고, 게시물 이미지의 스타일 분석은 별도 FastAPI 서버(`cv_service/`)가 콜백 방식으로 처리하는 구조입니다. 실제 CV 객체 탐지 모델과 비전 LLM(Gemini)이 연동되어, 아이템 탐지·세부 라벨·스타일 비율·해석 텍스트가 모두 실제 모델 결과로 동작합니다.

## 기술 스택

- Python >= 3.12
- Django >= 6.0.7
- Django REST Framework >= 3.17.1
- drf-spectacular (Django API 명세 자동 생성 + Swagger 화면)
- Pillow (이미지 처리)
- PostgreSQL 17 (Docker Compose 실행 시 사용) / SQLite (Docker 없이 로컬에서 직접 실행할 때의 기본값)
- psycopg (Django ↔ PostgreSQL 접속 드라이버)
- Celery + Redis (AI 분석 비동기 작업 큐)
- FastAPI + uvicorn (`cv_service/` — CV/LLM 분석 전용 서버, Django와 독립된 가상환경)
- PyTorch + Transformers + timm (`cv_service/` — 객체 탐지/이미지-텍스트 모델 추론)
- Gemini API (`google-genai`, `gemini-3.8-flash` — 스타일 비율·해석 텍스트·아이템 세부 라벨 생성)
- 패키지 관리: [uv](https://docs.astral.sh/uv/)
- Docker + Docker Compose (web / celery / cv_service / redis / db(PostgreSQL) 5개 컨테이너를 한 번에 실행)

## 프로젝트 구조

```
config/         # 프로젝트 설정, URL 라우팅
accounts/       # 커스텀 유저 모델, 마이페이지/로그인 화면
posts/          # 게시물, 댓글, 좋아요 (모델 + DRF API)
analysis/       #  이미지 스타일 분석 (Celery 비동기 파이프라인, Django 측 로직은 완성 / 실제 CV·LLM은 cv_service 연동)
config/celery.py  # Celery 앱 설정
cv_service/     # FastAPI 기반 CV/LLM 분석 서버 (Django와 별도 pyproject.toml/가상환경, 포트 8001). 객체 탐지 + 세부 라벨링 + 비전 LLM(Gemini) 연동 완료
Dockerfile      # Django + Celery 공용 이미지 (루트), cv_service/Dockerfile은 FastAPI용
docker-compose.yml  # web, celery, cv_service, redis, db(PostgreSQL) 5개 서비스 구성
templates/      # 서버 렌더링 템플릿 (feed, mypage, login, analysis)
static/         #  CSS(디자인 시스템 변수 기반), JS, 이미지
media/          # 업로드된 게시물 이미지
```

## 앱별 기능

### accounts
- `AUTH_USER_MODEL`을 커스텀 `User`(`AbstractUser` 상속)로 교체
- 세션 기반 회원가입 / 로그인 / 로그아웃 구현
  - `/signup/` — 회원가입 (아이디/비밀번호), 이미 로그인한 상태면 피드로 리다이렉트
  - `/login/` — 로그인, 이미 로그인한 상태면 피드로 리다이렉트
  - `/logout/` — 로그아웃 (POST 전용, GET 요청으로는 접근 차단)
- `/mypage/` — 마이페이지, 로그인한 본인 게시물만 3열 그리드로 표시 (비로그인 접근 시 로그인 페이지로 리다이렉트)

### posts
- `Post`: 이미지 + 캡션 게시물
- `Comment`: 게시물별 댓글 (N:1)
- `Like`: 게시물별 좋아요 (post, user 조합 unique)
- `/` : 피드 페이지 (좋아요 개수, 댓글 목록, 로그인 유저의 좋아요 여부 표시)
  - 로그인 유저는 피드 상단 인라인 폼으로 이미지+캡션 게시물 등록 가능 (등록 즉시 새 카드가 피드 최상단에 반영)
  - 댓글 작성 / 수정 / 삭제는 새로고침 없이 JS(`fetch`)로 처리 (작성자 본인만 수정·삭제 가능)
- DRF API
  - `GET/POST /api/posts/` — 게시물 목록 조회 / 작성
  - `GET/POST /api/posts/<post_id>/comments/` — 댓글 목록 조회 / 작성
  - `GET/PUT/PATCH/DELETE /api/posts/<post_id>/comments/<comment_id>/` — 댓글 단건 조회 / 수정 / 삭제 (작성자 본인만 수정·삭제 가능)
  - `POST /api/posts/<post_id>/like/` — 좋아요 토글
  - 댓글 단건 API는 URL의 `post_id`에 속한 댓글만 대상으로 삼음 (다른 게시물의 댓글 번호를 넣으면 404)
- API 문서(Swagger): `http://localhost:8000/api/docs/` — 게시물·댓글·좋아요 API를 "게시물/댓글/좋아요" 그룹으로 보여 주고 화면에서 바로 요청을 보낼 수 있음 (명세 원본 데이터는 `/api/schema/`)
  - 세션 로그인 방식이라 같은 브라우저에서 `/login/`으로 먼저 로그인한 뒤 열면 로그인 상태로 요청됨
  - 게시물 작성은 파일 선택 버튼으로 이미지 업로드 가능
  - AI 분석 주소(`/analysis/...`)는 DRF가 아닌 일반 Django 뷰라 이 문서에서 제외. 분석 서버의 API는 `cv_service`의 `http://localhost:8001/docs`에서 확인 (`/analyze`는 실제 분석을 실행하므로 화면에서 Execute는 비권장)

### analysis
- `Analysis`: 스타일 분석 요청/상태(`대기중`/`분석중`/`완료`/`실패`) 관리. `post` 또는 `image` 둘 중 하나로 "무엇을 분석하는지" 연결(둘 다 nullable), 콜백 검증용 토큰 보유
- `DetectedItem`: 분석으로 검출된 의류 아이템(카테고리, 바운딩 박스, 쇼핑 검색 링크)
- `StyleScore`: 스타일별 비율 점수
- Celery task(`run_analysis`)는 이미지를 `cv_service`의 `/analyze`로 전달하고, `cv_service`가 결과를 Django 콜백으로 되돌려주는 구조로 연동되어 있음. 비동기 파이프라인(요청 → FastAPI 호출 → 콜백 → 상태 전환) 전체가 실제 모델 기반으로 동작함 — `detected_items`의 카테고리/바운딩박스는 CV 탐지 모델, 세부 라벨·`style_scores`·`interpretation`은 Gemini가 생성한 결과.
- 실패 처리: 분석이 끝나지 못하면 상태를 `실패`로 바꾸고 결과 페이지에 안내 문구를 표시 (화면이 "분석 중"으로 멈춰 있지 않음)
  - cv_service 연결 불가 / 응답 시간 초과(연결 5초, 응답 300초) / cv_service 에러 응답 → Celery task가 감지해 `error_message`에 안내 문구 저장
  - Django 콜백 저장 실패 → 아이템·스타일·상태 저장을 `transaction.atomic()`으로 묶어 일부만 저장된 채 남지 않게 전부 취소하고, 분석을 즉시 `실패`로 표시한 뒤 500 응답 → cv_service가 콜백 응답을 확인해 에러로 응답 → 위와 같은 경로로 실패 기록
  - Celery/Redis가 꺼져 작업이 시작조차 안 된 경우 → 상태 조회 API가 요청 후 6분이 지난 미완료 분석을 실패로 전환
  - 이미 `완료`된 분석은 실패로 덮어쓰지 않음
- 로그: `config/settings.py`의 `LOGGING`이 `analysis` 앱 로그를 `시각 단계 파일이름: 내용` 형식으로 터미널(Celery worker 포함)에 출력. `run_analysis`의 실패는 연결 실패·시간 초과는 `logger.error`, 그 밖의 오류는 원인 위치까지 남기는 `logger.exception`으로 기록하고, 콜백 저장 실패도 `logger.exception`으로 기록
- 두 가지 분석 요청 방식:
  - **게시물 기반**: `/posts/<id>/` 상세 페이지의 "AI 분석 요청" 버튼 — 로그인한 유저라면 소유자 여부와 무관하게 누구나 요청 가능, 재분석도 횟수 제한 없음
  - **독립 업로드**: `/analysis/` 에서 게시물 없이 이미지 한 장만 업로드해 분석
- 분석 대기 중에는 결과 페이지가 3초마다 상태를 폴링(JS `fetch`)해서, 완료되면 자동으로 새로고침됨 (수동 새로고침 불필요)
- 결과 화면 (게시물 기반/독립 업로드 공용 조각 `templates/analysis/_result_body.html`)
  - 분석한 사진 위에 탐지된 아이템 위치를 번호가 붙은 박스로 표시 (저장된 0~1 정규화 좌표를 % 위치로 변환)
  - 스타일 비율은 큰 순서대로 막대 그래프로 표시
  - 탐지된 아이템은 사진의 박스와 같은 번호가 붙은 카드로 표시, 카드마다 쇼핑 검색 버튼 (라벨이 없으면 카테고리만 표시)
  - 게시물의 재분석이 실패해도 이전에 완료된 결과가 있으면 그 결과를 보여주고, 재분석 실패 사실은 안내 문구로 표시
- 주요 경로
  - `/analysis/` — 업로드 폼 (분석 홈)
  - `/posts/<post_id>/` 상세 페이지 내 요청 버튼 → `/analysis/post/<post_id>/request/`, 결과는 `/analysis/post/<post_id>/result/`
  - `/analysis/upload/` — 독립 업로드 처리, 결과는 `/analysis/<analysis_id>/result/`
  - `/analysis/api/<analysis_id>/callback/` — Celery task → Django 콜백 (토큰 검증)
  - `/analysis/api/<analysis_id>/status/` — 결과 페이지 폴링용 상태 조회 API (오래된 미완료 분석의 실패 전환도 여기서 처리)

### 관리자 페이지 (Django Admin, `/admin/`)
- **게시물 중심 화면**: 게시물 하나를 열면 사진, AI 분석 결과(해석·스타일 비율 표·탐지 아이템 표), 댓글, 좋아요가 한 화면에 모임. 탐지 아이템·스타일 비율·댓글·좋아요는 별도 메뉴 없이 게시물(또는 분석) 안에서 확인
  - 게시물 목록: 썸네일, 분석 수·좋아요 수·댓글 수(클릭 정렬), 검색(캡션·작성자·댓글 내용)
  - 댓글 삭제 가능(내용 수정은 불가), 좋아요는 보기 전용
- **분석 화면** (`Analysis`): 게시물 없이 올린 독립 업로드 분석의 보관 장소. 분석한 사진 미리보기, 상태 필터(대기중/분석중/완료/실패), 탐지 아이템 수·실패 사유 표시
- 표시 이름 통일: `게시물 #1 (캡션) · 분석 #2`, `독립 업로드 · 분석 #3`처럼 어느 게시물의 데이터인지 항상 보임
- AI 결과·콜백 토큰은 읽기 전용, 분석·아이템·좋아요 직접 추가 불가 (분석 상태만 수정 가능)
- 알려진 아쉬운 점: 사이드바에 `Analysiss`로 표시됨(자동 복수형), 인라인 줄 제목이 한 번 더 나옴

### cv_service (FastAPI)
- Django와 완전히 분리된 독립 프로젝트 (`cv_service/pyproject.toml`, 자체 가상환경, 포트 8001)
- `POST /analyze` — 이미지 + `callback_url` + `callback_token`을 받아 분석을 수행하고, 결과를 `callback_url`로 POST
- `GET /health` — 서버 생존 확인용
- `app/ml_models.py` — 서버 기동 시 모델을 한 번만 로딩 (모듈 레벨 로딩, 요청마다 재로딩 방지)
- `app/detection.py` — 객체 탐지 모델(`yainage90/fashion-object-detection`, conditional-detr-resnet-50 파인튜닝)로 옷 아이템의 바운딩박스 + 큰 카테고리(상의/하의/아우터/원피스/신발/가방/모자) 탐지, 0~1 정규화 좌표로 변환
- `app/labeling.py` — 탐지된 박스 영역을 크롭해 세부 라벨링 모델(`patrickjohncyh/fashion-clip`)로 zero-shot 세부 분류 (카테고리별 한글 후보 라벨 목록 기반). Gemini 호출이 실패했을 때 쓰는 예비 라벨 역할이며, 카테고리와 라벨이 같은 중복 아이템(좌우 신발 등)을 합치는 `merge_duplicates`도 포함
- `app/interpretation.py` — 사진과 탐지 결과(번호·카테고리·위치)를 Gemini에 보내 스타일 비율(`style_scores`), 해석 텍스트(`interpretation`), 아이템별 세부 라벨을 한 번의 호출로 생성. 구조화 출력(JSON 스키마)을 사용하고, 스타일 이름 중복 병합과 비율 합 100 정규화를 거침 (반올림 오차는 마지막 스타일이 남은 값을 가져가 합이 정확히 100이 됨)
- Gemini 호출이 성공하면 세부 라벨을 Gemini 결과로 덮어쓰고, 실패하면 FashionCLIP 라벨과 안내 문구로 대체해 탐지 결과는 그대로 저장
- Gemini 응답 지연 대비: 요청 한 번당 30초 제한(`LLM_TIMEOUT`), 서버 혼잡(503) 시 재시도 1회(`LLM_RETRY_ATTEMPTS`)로 제한 → Gemini가 응답하지 않아도 약 1분 안에 탐지 결과만으로 분석이 완료됨 (제한이 없을 때는 Celery의 300초 제한에 걸려 분석 전체가 실패했음)
- 로그: `app/main.py`의 `logging.basicConfig`로 `시각 단계 파일이름: 내용` 형식을 설정하고, Gemini 호출 실패는 `logger.warning`으로 기록
- API 키는 `cv_service/.env`의 `GEMINI_API_KEY`로 관리 (깃 추적 제외, 견본은 `cv_service/.env.example`)


## 웹 화면

### 회원가입

비밀번호 규칙 안내가 항상 보이고, 규칙을 어기면 빨간 문구로 이유를 알려 줍니다.

<img src="docs/images/web/signup-form.jpg" width="320">
<img src="docs/images/web/signup-password-invalid.jpg" width="320">
<img src="docs/images/web/signup-password-mismatch.jpg" width="320">
<img src="docs/images/web/signup-password-confirm-required.jpg" width="320">

가입이 끝나면 바로 로그인된 상태로 피드로 이동합니다.

<img src="docs/images/web/signup-complete.jpg" width="320">

### 피드·게시물

**피드** — 사진과 캡션을 올리고, 좋아요,댓글을 남깁니다.

<img src="docs/images/web/feed-default.jpg" width="320">
<img src="docs/images/web/post-created.jpg" width="320">

**게시물 상세** — 여기서 "AI 분석 요청" 버튼으로 분석을 시작합니다.

<img src="docs/images/web/post-detail.jpg" width="320">

### AI 분석 (게시물 기반)

**분석 중** — 3초마다 상태를 확인하다가 완료되면 자동으로 새로고침됩니다.

<img src="docs/images/web/post-analysis-loading.jpg" width="320">

**분석 완료** — 박스 번호와 아이템 카드 번호가 대응됩니다.

<img src="docs/images/web/post-analysis-done-1.jpg" width="320">
<img src="docs/images/web/post-analysis-done-2.jpg" width="320">

**LLM 호출 실패** — 탐지 결과는 그대로 보여 주고, 해석 자리에 안내 문구를 표시합니다.

<img src="docs/images/web/post-analysis-llm-fail.jpg" width="320">

### AI 분석 (독립 업로드)

게시물 없이 사진 한 장만 올려 분석합니다.

<img src="docs/images/web/analyze-upload.jpg" width="320">
<img src="docs/images/web/analyze-loading.jpg" width="320">

**분석 완료**

<img src="docs/images/web/analyze-done-1.jpg" width="320">
<img src="docs/images/web/analyze-done-2.jpg" width="320">

**LLM 호출 실패**

<img src="docs/images/web/analyze-llm-fail.jpg" width="320">

### 마이페이지

프로필 사진을 바꾸면 기본 아이콘이 새 사진으로 바뀝니다.

<img src="docs/images/web/mypage-default.jpg" width="320">
<img src="docs/images/web/mypage-profile-changed.jpg" width="320">

## API 문서·관리자 화면

### Swagger (`/api/docs/`)

게시물·댓글·좋아요 API를 그룹별로 보여 주고, 화면에서 바로 요청을 보낼 수 있습니다.

<img src="docs/images/swagger/01-overview.jpg" width="760">

**게시물 작성** — 파일 선택 버튼으로 이미지를 올리면 `201`이 반환됩니다.

<img src="docs/images/swagger/02-post-create-form.jpg" width="760">
<img src="docs/images/swagger/02-post-create-response.jpg" width="760">

**댓글 단건 조회 404** — Swagger로 테스트하다가 URL의 게시물 번호를 무시하던 버그를 찾아 고쳤습니다. 다른 게시물의 댓글 번호를 넣으면 404가 반환됩니다 (재발 방지 테스트 포함).

<img src="docs/images/swagger/06-comment-404.jpg" width="760">

**남의 댓글 삭제 403** — 작성자만 삭제할 수 있습니다.

<img src="docs/images/swagger/07-comment-delete-403-response.jpg" width="760">

<details>
<summary>Swagger 화면 더 보기 (좋아요 토글, 수정 권한, 입력 화면)</summary>

**게시물 작성 결과 (피드에 반영)**

<img src="docs/images/swagger/03-post-create-feed.jpg" width="320">

**좋아요 추가 (201, `liked: true`) → 피드 ♥1**

<img src="docs/images/swagger/04-like-created-form.jpg" width="760">
<img src="docs/images/swagger/04-like-created-response.jpg" width="760">
<img src="docs/images/swagger/04-like-created-feed.jpg" width="320">

**좋아요 취소 (200, `liked: false`) → 피드 ♡0**

<img src="docs/images/swagger/05-like-canceled-response.jpg" width="760">
<img src="docs/images/swagger/05-like-canceled-feed.jpg" width="320">

**남의 댓글 삭제 시도 (입력 화면)**

<img src="docs/images/swagger/07-comment-delete-403-form.jpg" width="760">

**남의 댓글 수정 시도 403**

<img src="docs/images/swagger/more-comment-update-403-form.jpg" width="760">
<img src="docs/images/swagger/more-comment-update-403-response.jpg" width="760">

</details>

### 관리자 페이지 (`/admin/`)

**게시물 목록** — 썸네일과 분석·좋아요·댓글 수가 한눈에 보입니다.

<img src="docs/images/admin/01-post-list.jpg" width="900">

**게시물 상세** — AI 분석 결과(해석, 스타일 비율, 탐지 아이템)와 댓글·좋아요가 게시물 안에 모여 있습니다.

<img src="docs/images/admin/02-post-detail-analysis.jpg" width="900">
<img src="docs/images/admin/03-post-detail-comments-likes.jpg" width="900">

**분석 목록** — 상태 필터, 탐지 아이템 수, 실패 사유. 게시물 없이 올린 분석은 `독립 업로드`로 표시됩니다.

<img src="docs/images/admin/04-analysis-list.jpg" width="900">

<details>
<summary>관리자 화면 더 보기 (게시물 상세 위쪽, 분석 상세)</summary>

**게시물 상세 (위쪽)**

<img src="docs/images/admin/more-post-detail-top.jpg" width="900">

**분석 상세 (게시물 기반)** — 사진, 해석, 탐지 아이템, 스타일 비율

<img src="docs/images/admin/more-analysis-detail.jpg" width="900">
<img src="docs/images/admin/more-analysis-detail-items.jpg" width="900">

**분석 상세 (독립 업로드)**

<img src="docs/images/admin/more-analysis-standalone.jpg" width="900">
<img src="docs/images/admin/more-analysis-standalone-items.jpg" width="900">

</details>

## 디자인 시스템

- `static/css/base.css`의 `:root`에 색상/여백/둥근모서리/그림자를 CSS 변수로 정의하고, 모든 페이지가 이 변수를공유합니다.
  - 포인트 컬러: 라벤더/보라 계열 (`--color-accent`), 기존 인스타그램풍 파란색에서 교체
  - 버튼: `.btn--primary`(채워진 버튼) / `.btn--ghost`(테두리만 있는 보조 버튼) 두 종류로 통일
- 적용된 페이지: 공통 상/하단 바, 피드, 마이페이지, 게시글 상세, 로그인/회원가입, AI 분석(업로드 폼, 결과 화면)
- 페이지별 CSS는 `static/css/`에 파일 단위로 분리 (`feed.css`, `mypage.css`, `auth.css`, `analysis.css`)

## 실행 방법

AI 분석 기능은 Redis + Celery worker + cv_service(FastAPI)가 같이 떠 있어야 동작합니다.

### 사전 준비 — `.env` 파일 2개

비밀값은 코드에 적지 않고 `.env` 파일에서 읽습니다 (`.env`는 깃 추적과 Docker 이미지에서 제외). 견본 파일을 복사한 뒤 값을 채우세요.

```bash
cp .env.example .env                        # Django용: SECRET_KEY, DEBUG, DB 접속 정보
cp cv_service/.env.example cv_service/.env  # cv_service용: GEMINI_API_KEY

# .env의 DJANGO_SECRET_KEY에 넣을 새 키 만들기 ($, # 같은 문자가 섞일 수 있으니 작은따옴표로 감싸서 넣기)
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

| 변수 | 파일 | 설명 |
|---|---|---|
| `DJANGO_SECRET_KEY` | `.env` | 필수. 없으면 서버가 `KeyError`로 시작되지 않음 |
| `DJANGO_DEBUG` | `.env` | 정확히 `True`일 때만 켜짐. 값이 없으면 꺼짐 (개발 중에는 `True`) |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `.env` | Docker의 PostgreSQL 접속 정보 (개발용 값) |
| `GEMINI_API_KEY` | `cv_service/.env` | Gemini API 키 (발급: Google AI Studio) |

### 방법 1 — Docker Compose (권장)

한 번에 5개(web, celery, cv_service, redis, db)가 같이 뜹니다. 위의 `.env` 파일 2개가 있어야 합니다.

```bash
docker compose build   # 이미지 만들기 (처음 한 번, 의존성이 바뀌면 다시)
docker compose up -d   # 전체 실행 (백그라운드, 로그는 docker compose logs -f)

# 처음 한 번만: 빈 PostgreSQL DB에 테이블과 관리자 계정 만들기
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

- 접속: Django `http://localhost:8000` (API 문서 `/api/docs/`), cv_service `http://localhost:8001` (API 문서 `/docs`)
- 컨테이너끼리는 서비스 이름(`redis`, `web`, `cv_service`)으로 서로를 부르며, `config/settings.py`가 환경변수(`REDIS_URL`, `INTERNAL_BASE_URL`, `CV_SERVICE_BASE_URL`)로 주소를 읽습니다. 환경변수가 없으면 기존 `localhost` 값을 쓰므로 아래 방법 2도 그대로 동작합니다.
- DB는 PostgreSQL 컨테이너(`db`)를 사용하고, 데이터는 Docker 볼륨(`postgres_data`)에 저장되어 컨테이너를 지워도 남습니다. `docker compose down -v`는 볼륨까지 지우므로 DB 데이터가 사라집니다. `db`의 포트는 컴퓨터 밖으로 열지 않았으며, 직접 확인하려면 `docker compose exec db psql -U postgres -d mom_vision`을 사용합니다.
- `config/settings.py`는 환경변수 `POSTGRES_HOST`가 있을 때만 PostgreSQL(`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT`)을 사용하고, 없으면 기존 SQLite(`db.sqlite3`)를 사용합니다. 아래 방법 2는 그대로 SQLite로 동작합니다.
- 업로드 이미지(`media/`)는 내 컴퓨터의 폴더를 컨테이너에 연결해서 사용합니다.
- `web`, `celery`는 `env_file`로 `.env` 전체를 받고, `db`는 `${POSTGRES_PASSWORD}`처럼 필요한 값 3개만 골라 받습니다 (DB 컨테이너에는 Django `SECRET_KEY`가 필요 없음).
- DB 비밀번호(`postgres`)는 개발용 값입니다. PostgreSQL은 볼륨이 처음 만들어질 때만 이 값을 읽으므로, 기존 볼륨이 있는 상태에서 `.env`의 값만 바꾸면 접속에 실패합니다. 배포 때는 새 볼륨에 강한 비밀번호를 넣어야 합니다.

### 방법 2 — 터미널 4개로 직접 실행

터미널 4개를 띄워서 각각 실행하세요.

```bash
# 터미널 1 — Redis (Celery 작업 큐)
redis-server

# 터미널 2 — cv_service (FastAPI, Django와 별도 가상환경)
cd cv_service
uv sync
uv run --env-file .env uvicorn app.main:app --reload --port 8001
# cv_service/.env에 GEMINI_API_KEY=발급받은_키가 있어야 서버가 기동됩니다. (키 발급: Google AI Studio)

# 터미널 3 — Celery worker
uv sync
uv run --env-file .env celery -A config worker -l info

# 터미널 4 — Django 서버
uv run --env-file .env python manage.py migrate
uv run --env-file .env python manage.py runserver
# 루트 .env에 DJANGO_SECRET_KEY가 있어야 합니다. (POSTGRES_HOST는 넣지 않으므로 SQLite로 동작)

```


---


## 테스트 실행

```bash
uv run --env-file .env python manage.py test posts
uv run --env-file .env python manage.py test accounts
uv run --env-file .env python manage.py test analysis
```

- settings.py가 `.env`에서 `DJANGO_SECRET_KEY`를 읽으므로 `--env-file .env`가 필요합니다.

- posts: 좋아요/댓글 생성·조회·수정·삭제, 다른 게시물의 댓글 접근 차단, 게시물 등록 API 테스트 (17개)
- accounts: 회원가입/로그인/로그아웃/마이페이지 테스트 (13개)
- analysis: 콜백 토큰 검증·결과 저장(저장 실패 시 전체 롤백 + 실패 처리), 분석 요청 권한(게시물 기반/독립 업로드), 상태 조회의 오래된 분석 실패 전환, 실패 기록 함수, Celery task의 실패 처리(실패 로그 기록 확인 포함), 결과 페이지(사진 표시·재분석 실패 시 이전 결과 표시) 테스트 (19개)
  - Celery와 cv_service 호출은 `unittest.mock`으로 대체하므로 Redis/Celery/cv_service를 켜지 않아도 실행됩니다.
  - 테스트용 이미지는 임시 폴더에 저장되고 테스트가 끝나면 삭제됩니다 (`media/`에 남지 않음).

`cv_service`는 별도 가상환경이라 해당 폴더에서 따로 실행합니다 (Django 없이 파이썬 기본 `unittest` 사용).

```bash
cd cv_service
uv run --env-file .env python -m unittest -v
```

- cv_service: 스타일 비율 정리(`normalize_scores`), 라벨 적용(`apply_labels`), 중복 아이템 병합(`merge_duplicates`), Gemini 호출의 성공·실패·잘못된 응답·제한 시간 전달·실패 로그 기록(`interpret_style`), `/analyze` 전체 흐름(콜백 데이터 구성·검색 링크·중복 병합·콜백 실패 시 500) 테스트 (23개)
  - Gemini 접속 객체와 탐지·라벨링·콜백 전송을 `unittest.mock`으로 대체하므로 인터넷 연결이나 API 사용량 없이 실행됩니다 (모듈을 불러올 때 API 키를 읽으므로 `--env-file .env`는 필요).

## 참고

- 모델 설계(ERD)는 [`docs/erd.md`](docs/erd.md)에 있습니다.
- `LANGUAGE_CODE`, `TIME_ZONE`은 한국(`ko-kr`, `Asia/Seoul`) 기준으로 설정되어 있습니다.
- `SECRET_KEY`는 `.env`에서 읽습니다. 예전에 코드에 적혀 있던 키는 git 기록에 남아 있어 폐기했고, 새로 만든 키로 교체했습니다.
- 이미지 분석을 담당할 `cv_service`(FastAPI)는 이 저장소에 포함되어 있으며, 실제 객체 탐지 + 세부 라벨링 모델이 동작합니다. 스타일 비율/해석 텍스트/세부 라벨은 Gemini API로 생성하며, Django ↔ FastAPI 간 비동기 요청→콜백→상태 전환 전체 흐름은 검증된 상태입니다.
- `cv_service`를 처음 실행하면 허깅페이스에서 모델 가중치를 다운로드하므로 기동에 시간이 걸릴 수 있습니다 (직접 실행 시 이후엔 로컬 캐시 사용). Docker로 실행하면 컨테이너를 새로 만들 때마다 다시 내려받습니다 (모델 캐시 볼륨 연결은 추후 과제).
- Docker 구성 관련 한계: `redis`는 `depends_on`이 시작 순서만 보장합니다(`db`는 `healthcheck`로 준비 완료까지 대기). 서버는 개발용 `runserver`입니다 (`DEBUG=False`로 바꾸면 CSS·이미지가 나오지 않으므로, 배포 단계에서 whitenoise/nginx와 함께 전환 예정). 자동 테스트(`manage.py test`)는 Docker 없이 SQLite로 실행하는 것을 기준으로 합니다.
- 알려진 한계: 작은 신발/부츠는 탐지되지 않을 수 있습니다 (탐지 모델이 해당 박스를 낮은 점수로만 인식하며, 기준값 조정으로는 해결되지 않음). Gemini 해석 글에는 언급되지만 박스는 표시되지 않습니다. 근본 해결은 고도화 단계에서 다룹니다.
- 서버를 켠 직후의 첫 분석은 모델 준비 시간 때문에 1분 이상 걸릴 수 있고, 이후 분석은 수 초 내에 끝납니다.