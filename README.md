# Mini Project 1 — 패션 SNS

이미지를 올려 스타일을 공유하고, 좋아요·댓글로 소통하는 패션 SNS 서비스입니다.
Django(+DRF)로 웹/API 서버를 구성하고, 게시물 이미지의 스타일 분석은 별도 FastAPI 서버가 콜백 방식으로 처리하는 구조를 목표로 합니다.

## 기술 스택

- Python >= 3.12
- Django >= 6.0.7
- Django REST Framework >= 3.17.1
- Pillow (이미지 처리)
- SQLite (개발용 DB)
- 패키지 관리: [uv](https://docs.astral.sh/uv/)

## 프로젝트 구조

```
config/         # 프로젝트 설정, URL 라우팅
accounts/       # 커스텀 유저 모델, 마이페이지/로그인 화면
posts/          # 게시물, 댓글, 좋아요 (모델 + DRF API)
analysis/       # 이미지 스타일 분석 결과 (FastAPI 콜백 연동 예정)
templates/      # 서버 렌더링 템플릿 (feed, mypage, login, analysis)
static/         # CSS, JS, 이미지
media/          # 업로드된 게시물 이미지
```

## 앱별 기능

### accounts
- `AUTH_USER_MODEL`을 커스텀 `User`(`AbstractUser` 상속)로 교체
- `/mypage/`, `/login/` 페이지 (현재 화면 뼈대만 존재, 로그인 로직 미구현)


### posts
- `Post`: 이미지 + 캡션 게시물
- `Comment`: 게시물별 댓글 (N:1)
- `Like`: 게시물별 좋아요 (post, user 조합 unique)
- `/` : 피드 페이지 (좋아요 개수, 댓글 목록, 로그인 유저의 좋아요 여부 표시)
  - 댓글 작성 / 수정 / 삭제는 새로고침 없이 JS(`fetch`)로 처리 (작성자 본인만 수정·삭제 가능)
- DRF API
  - `GET/POST /api/posts/` — 게시물 목록 조회 / 작성
  - `GET/POST /api/posts/<post_id>/comments/` — 댓글 목록 조회 / 작성
  - `GET/PUT/PATCH/DELETE /api/posts/<post_id>/comments/<comment_id>/` — 댓글 단건 조회 / 수정 / 삭제 (작성자 본인만 수정·삭제 가능)
  - `POST /api/posts/<post_id>/like/` — 좋아요 토글

### analysis
- `Analysis`: 게시물에 대한 스타일 분석 요청/상태(`대기중`/`분석중`/`완료`/`실패`) 관리, FastAPI 콜백 검증용 토큰 보유
- `DetectedItem`: 분석으로 검출된 의류 아이템(카테고리, 바운딩 박스, 쇼핑 검색 링크)
- `StyleScore`: 스타일별 비율 점수
- `/analysis/` : 분석 홈 페이지 (뼈대만 존재)

## 실행 방법

```bash
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

## 참고

- `LANGUAGE_CODE`, `TIME_ZONE`은 한국(`ko-kr`, `Asia/Seoul`) 기준으로 설정되어 있습니다.
- `SECRET_KEY`는 개발용 기본값이며, 배포 전 환경 변수 등으로 교체가 필요합니다.
- 이미지 분석을 담당할 FastAPI 서버는 아직 이 저장소에 포함되어 있지 않습니다.
