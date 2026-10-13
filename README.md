# Mini Project 1 — 패션 SNS

Django(+DRF)로 웹/API 서버를 구성하고, 게시물 이미지의 스타일 분석은 별도 FastAPI 서버(`cv_service/`)가 콜백 방식으로 처리하는 구조입니다. 실제 CV 객체 탐지 모델과 비전 LLM(Gemini)이 연동되어, 아이템 탐지·세부 라벨·스타일 비율·해석 텍스트가 모두 실제 모델 결과로 동작합니다.

## 기술 스택

- Python >= 3.12
- Django >= 6.0.7
- Django REST Framework >= 3.17.1
- Pillow (이미지 처리)
- SQLite (개발용 DB)
- Celery + Redis (AI 분석 비동기 작업 큐)
- FastAPI + uvicorn (`cv_service/` — CV/LLM 분석 전용 서버, Django와 독립된 가상환경)
- PyTorch + Transformers + timm (`cv_service/` — 객체 탐지/이미지-텍스트 모델 추론)
- Gemini API (`google-genai`, `gemini-3.8-flash` — 스타일 비율·해석 텍스트·아이템 세부 라벨 생성)
- 패키지 관리: [uv](https://docs.astral.sh/uv/)

## 프로젝트 구조

```
config/         # 프로젝트 설정, URL 라우팅
accounts/       # 커스텀 유저 모델, 마이페이지/로그인 화면
posts/          # 게시물, 댓글, 좋아요 (모델 + DRF API)
analysis/       #  이미지 스타일 분석 (Celery 비동기 파이프라인, Django 측 로직은 완성 / 실제 CV·LLM은 cv_service 연동)
config/celery.py  # Celery 앱 설정
cv_service/     # FastAPI 기반 CV/LLM 분석 서버 (Django와 별도 pyproject.toml/가상환경, 포트 8001). 객체 탐지 + 세부 라벨링 + 비전 LLM(Gemini) 연동 완료
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
- Celery task(`run_analysis`)는 이미지를 `cv_service`의 `/analyze`로 전달하고, `cv_service`가 결과를 Django 콜백으로 되돌려주는 구조로 연동되어 있음. 비동기 파이프라인(요청 → FastAPI 호출 → 콜백 → 상태 전환) 전체가 실제 모델 기반으로 동작함 — `detected_items`의 카테고리/바운딩박스는 CV 탐지 모델, 세부 라벨·`style_scores`·`interpretation`은 Gemini가 생성한 결과.
- 실패 처리: 분석이 끝나지 못하면 상태를 `실패`로 바꾸고 결과 페이지에 안내 문구를 표시 (화면이 "분석 중"으로 멈춰 있지 않음)
  - cv_service 연결 불가 / 응답 시간 초과(연결 5초, 응답 300초) / cv_service 에러 응답 → Celery task가 감지해 `error_message`에 안내 문구 저장
  - Django 콜백 저장 실패 → cv_service가 콜백 응답을 확인해 에러로 응답 → 위와 같은 경로로 실패 기록
  - Celery/Redis가 꺼져 작업이 시작조차 안 된 경우 → 상태 조회 API가 요청 후 6분이 지난 미완료 분석을 실패로 전환
  - 이미 `완료`된 분석은 실패로 덮어쓰지 않음
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

### cv_service (FastAPI)
- Django와 완전히 분리된 독립 프로젝트 (`cv_service/pyproject.toml`, 자체 가상환경, 포트 8001)
- `POST /analyze` — 이미지 + `callback_url` + `callback_token`을 받아 분석을 수행하고, 결과를 `callback_url`로 POST
- `GET /health` — 서버 생존 확인용
- `app/ml_models.py` — 서버 기동 시 모델을 한 번만 로딩 (모듈 레벨 로딩, 요청마다 재로딩 방지)
- `app/detection.py` — 객체 탐지 모델(`yainage90/fashion-object-detection`, conditional-detr-resnet-50 파인튜닝)로 옷 아이템의 바운딩박스 + 큰 카테고리(상의/하의/아우터/원피스/신발/가방/모자) 탐지, 0~1 정규화 좌표로 변환
- `app/labeling.py` — 탐지된 박스 영역을 크롭해 세부 라벨링 모델(`patrickjohncyh/fashion-clip`)로 zero-shot 세부 분류 (카테고리별 한글 후보 라벨 목록 기반). Gemini 호출이 실패했을 때 쓰는 예비 라벨 역할이며, 카테고리와 라벨이 같은 중복 아이템(좌우 신발 등)을 합치는 `merge_duplicates`도 포함
- `app/interpretation.py` — 사진과 탐지 결과(번호·카테고리·위치)를 Gemini에 보내 스타일 비율(`style_scores`), 해석 텍스트(`interpretation`), 아이템별 세부 라벨을 한 번의 호출로 생성. 구조화 출력(JSON 스키마)을 사용하고, 스타일 이름 중복 병합과 비율 합 100 정규화를 거침
- Gemini 호출이 성공하면 세부 라벨을 Gemini 결과로 덮어쓰고, 실패하면 FashionCLIP 라벨과 안내 문구로 대체해 탐지 결과는 그대로 저장
- Gemini 응답 지연 대비: 요청 한 번당 30초 제한(`LLM_TIMEOUT`), 서버 혼잡(503) 시 재시도 1회(`LLM_RETRY_ATTEMPTS`)로 제한 → Gemini가 응답하지 않아도 약 1분 안에 탐지 결과만으로 분석이 완료됨 (제한이 없을 때는 Celery의 300초 제한에 걸려 분석 전체가 실패했음)
- API 키는 `cv_service/.env`의 `GEMINI_API_KEY`로 관리 (깃 추적 제외)


## 실행 방법
## 디자인 시스템

- `static/css/base.css`의 `:root`에 색상/여백/둥근모서리/그림자를 CSS 변수로 정의하고, 모든 페이지가 이 변수를공유합니다.
  - 포인트 컬러: 라벤더/보라 계열 (`--color-accent`), 기존 인스타그램풍 파란색에서 교체
  - 버튼: `.btn--primary`(채워진 버튼) / `.btn--ghost`(테두리만 있는 보조 버튼) 두 종류로 통일
- 적용된 페이지: 공통 상/하단 바, 피드, 마이페이지, 게시글 상세, 로그인/회원가입, AI 분석(업로드 폼, 결과 화면)
- 페이지별 CSS는 `static/css/`에 파일 단위로 분리 (`feed.css`, `mypage.css`, `auth.css`, `analysis.css`)

AI 분석 기능은 Redis + Celery worker + cv_service(FastAPI)가 같이 떠 있어야 동작합니다. 터미널 4개를 띄워서 각각 실행하세요.

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
uv run python manage.py test analysis
```

- posts: 좋아요/댓글 생성·조회·수정·삭제, 게시물 등록 API 테스트 (16개)
- accounts: 회원가입/로그인/로그아웃/마이페이지 테스트 (13개)
- analysis: 콜백 토큰 검증·결과 저장, 분석 요청 권한(게시물 기반/독립 업로드), 상태 조회의 오래된 분석 실패 전환, 실패 기록 함수, Celery task의 실패 처리, 결과 페이지(사진 표시·재분석 실패 시 이전 결과 표시) 테스트 (18개)
  - Celery와 cv_service 호출은 `unittest.mock`으로 대체하므로 Redis/Celery/cv_service를 켜지 않아도 실행됩니다.
  - 테스트용 이미지는 임시 폴더에 저장되고 테스트가 끝나면 삭제됩니다 (`media/`에 남지 않음).

`cv_service`는 별도 가상환경이라 해당 폴더에서 따로 실행합니다 (Django 없이 파이썬 기본 `unittest` 사용).

```bash
cd cv_service
uv run --env-file .env python -m unittest -v
```

- cv_service: 스타일 비율 정리(`normalize_scores`), 라벨 적용(`apply_labels`), 중복 아이템 병합(`merge_duplicates`), Gemini 호출의 성공·실패·잘못된 응답·제한 시간 전달(`interpret_style`) 테스트 (17개)
  - Gemini 접속 객체를 `unittest.mock`으로 대체하므로 인터넷 연결이나 API 사용량 없이 실행됩니다 (모듈을 불러올 때 API 키를 읽으므로 `--env-file .env`는 필요).

## 참고

- `LANGUAGE_CODE`, `TIME_ZONE`은 한국(`ko-kr`, `Asia/Seoul`) 기준으로 설정되어 있습니다.
- `SECRET_KEY`는 개발용 기본값이며, 배포 전 환경 변수 등으로 교체가 필요합니다.
- 이미지 분석을 담당할 `cv_service`(FastAPI)는 이 저장소에 포함되어 있으며, 실제 객체 탐지 + 세부 라벨링 모델이 동작합니다. 스타일 비율/해석 텍스트/세부 라벨은 Gemini API로 생성하며, Django ↔ FastAPI 간 비동기 요청→콜백→상태 전환 전체 흐름은 검증된 상태입니다.
- `cv_service`를 처음 실행하면 허깅페이스에서 모델 가중치를 다운로드하므로 기동에 시간이 걸릴 수 있습니다 (이후엔 로컬 캐시 사용).
- 서버를 켠 직후의 첫 분석은 모델 준비 시간 때문에 1분 이상 걸릴 수 있고, 이후 분석은 수 초 내에 끝납니다.