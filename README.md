# Mini Project 1 — 패션 SNS

Django(+DRF)로 웹/API 서버를 구성하고, 게시물 이미지의 스타일 분석은 별도 FastAPI 서버(`cv_service/`)가 콜백 방식으로 처리하는 구조입니다. 현재 FastAPI는 더미 결과를 반환하는 뼈대 단계이며, 실제 CV 탐지/세부 라벨링/비전 LLM 연동이 예정되어 있습니다.

## 기술 스택

- Python >= 3.12
- Django >= 6.0.7
- Django REST Framework >= 3.17.1
- Pillow (이미지 처리)
- SQLite (개발용 DB)
- Celery + Redis (AI 분석 비동기 작업 큐)
- FastAPI + uvicorn (`cv_service/` — CV/LLM 분석 전용 서버, Django와 독립된 가상환경)
- 패키지 관리: [uv](https://docs.astral.sh/uv/)

## 프로젝트 구조

```
config/         # 프로젝트 설정, URL 라우팅
accounts/       # 커스텀 유저 모델, 마이페이지/로그인 화면
posts/          # 게시물, 댓글, 좋아요 (모델 + DRF API)
analysis/       #  이미지 스타일 분석 (Celery 비동기 파이프라인, Django 측 로직은 완성 / 실제 CV·LLM은 cv_service 연동)
config/celery.py  # Celery 앱 설정
cv_service/     # FastAPI 기반 CV/LLM 분석 서버 (Django와 별도 pyproject.toml/가상환경, 포트 8001). 현재 더미 결과 반환 뼈대 단계
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

### analysis
- `Analysis`: 스타일 분석 요청/상태(`대기중`/`분석중`/`완료`/`실패`) 관리. `post` 또는 `image` 둘 중 하나로 "무엇을 분석하는지" 연결(둘 다 nullable), 콜백 검증용 토큰 보유
- `DetectedItem`: 분석으로 검출된 의류 아이템(카테고리, 바운딩 박스, 쇼핑 검색 링크)
- `StyleScore`: 스타일별 비율 점수
- Celery task(`run_dummy_analysis`)는 이미지를 `cv_service`의 `/analyze`로 전달하고, `cv_service`가 결과를 Django 콜백으로 되돌려주는 구조로 연동되어 있음. 현재 `cv_service`는 실제 모델 없이 고정된 더미 결과를 즉시 반환하는 뼈대 단계이며, 비동기 파이프라인(요청 → FastAPI 호출 → 콜백 → 상태 전환) 자체는 실제 서비스와 동일하게 구현되어 있음.
- 두 가지 분석 요청 방식:
  - **게시물 기반**: `/posts/<id>/` 상세 페이지의 "AI 분석 요청" 버튼 — 로그인한 유저라면 소유자 여부와 무관하게 누구나 요청 가능, 재분석도 횟수 제한 없음
  - **독립 업로드**: `/analysis/` 에서 게시물 없이 이미지 한 장만 업로드해 분석
- 분석 대기 중에는 결과 페이지가 3초마다 상태를 폴링(JS `fetch`)해서, 완료되면 자동으로 새로고침됨 (수동 새로고침 불필요)
- 주요 경로
  - `/analysis/` — 업로드 폼 (분석 홈)
  - `/posts/<post_id>/` 상세 페이지 내 요청 버튼 → `/analysis/post/<post_id>/request/`, 결과는 `/analysis/post/<post_id>/result/`
  - `/analysis/upload/` — 독립 업로드 처리, 결과는 `/analysis/<analysis_id>/result/`
  - `/analysis/api/<analysis_id>/callback/` — Celery task → Django 콜백 (토큰 검증)
  - `/analysis/api/<analysis_id>/status/` — 결과 페이지 폴링용 상태 조회 API

### cv_service (FastAPI)
- Django와 완전히 분리된 독립 프로젝트 (`cv_service/pyproject.toml`, 자체 가상환경, 포트 8001)
- `POST /analyze` — 이미지 + `callback_url` + `callback_token`을 받아 분석을 수행하고, 결과를 `callback_url`로 POST. 현재는 실제 모델 없이 고정된 더미 결과를 즉시 반환
- `GET /health` — 서버 생존 확인용
- 실제 CV 탐지 모델(`yainage90/fashion-object-detection`) + 세부 라벨링(`patrickjohncyh/fashion-clip`) + 비전 LLM 연동은 예정 (설계는 완료, 구현 전)


## 실행 방법
## 디자인 시스템

- `static/css/base.css`의 `:root`에 색상/여백/둥근모서리/그림자를 CSS 변수로 정의하고, 모든 페이지가 이 변수를공유합니다.
  - 포인트 컬러: 라벤더/보라 계열 (`--color-accent`), 기존 인스타그램풍 파란색에서 교체
  - 버튼: `.btn--primary`(채워진 버튼) / `.btn--ghost`(테두리만 있는 보조 버튼) 두 종류로 통일
- 적용된 페이지: 공통 상/하단 바, 피드, 마이페이지, 게시글 상세, 로그인/회원가입, AI 분석(플레이스홀더)
- 페이지별 CSS는 `static/css/`에 파일 단위로 분리 (`feed.css`, `mypage.css`, `auth.css`, `analysis.css`)

AI 분석 기능은 Redis + Celery worker + cv_service(FastAPI)가 같이 떠 있어야 동작합니다. 터미널 4개를 띄워서 각각 실행하세요.

```bash
# 터미널 1 — Redis (Celery 작업 큐)
redis-server

# 터미널 2 — cv_service (FastAPI, Django와 별도 가상환경)
cd cv_service
uv sync
uv run uvicorn app.main:app --reload --port 8001

# 터미널 3 — Celery worker
uv sync
uv run celery -A config worker -l info

# 터미널 4 — Django 서버
uv run python manage.py migrate
uv run python manage.py runserver

```


---


## 테스트 실행

```bash
uv run python manage.py test posts
uv run python manage.py test accounts
```

- posts: 좋아요/댓글 생성·조회·수정·삭제, 게시물 등록 API 테스트 (16개)
- accounts: 회원가입/로그인/로그아웃/마이페이지 테스트 (13개)

## 참고

- `LANGUAGE_CODE`, `TIME_ZONE`은 한국(`ko-kr`, `Asia/Seoul`) 기준으로 설정되어 있습니다.
- `SECRET_KEY`는 개발용 기본값이며, 배포 전 환경 변수 등으로 교체가 필요합니다.
- 이미지 분석을 담당할 `cv_service`(FastAPI)는 이 저장소에 포함되어 있으나, 실제 CV/LLM 모델 없이 더미 결과를 반환하는 뼈대 단계입니다. Django ↔ FastAPI 간 비동기 요청→콜백→상태 전환 전체 흐름은 검증된 상태입니다.