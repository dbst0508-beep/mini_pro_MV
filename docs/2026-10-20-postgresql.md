# DB를 SQLite에서 PostgreSQL로 바꾸기 (2026-10-20)

브랜치: `feature/postgresql`

> 한 줄 요약: Docker로 실행할 때는 PostgreSQL을 DB로 쓰도록 바꿨다. `docker-compose.yml`에 `db` 컨테이너를 추가했고, `settings.py`는 환경변수가 있으면 PostgreSQL, 없으면 기존 SQLite를 쓴다. 회원가입, 게시물 업로드, 좋아요, 댓글, AI 분석이 전부 새 DB에서 정상 동작하는 것을 브라우저에서 확인했다.

---

## 1. 기술문서

### 1-1. 왜 바꿨나

| | SQLite | PostgreSQL |
|---|---|---|
| 정체 | 프로젝트 폴더 안의 **파일 하나** (`db.sqlite3`) | 따로 켜 두는 **DB 서버 프로그램** |
| 동시에 쓰기 | 쓰는 순간 파일 전체를 잠가서, 여러 프로그램이 동시에 쓰면 `database is locked`가 날 수 있음 | 서버가 여러 요청을 알아서 교통정리함 |
| 이 프로젝트에서의 문제 | `web`과 `celery`가 같은 파일을 동시에 씀 (분석 결과 저장 등) | 해당 없음 |
| 배포 | 파일을 서버에 올려야 해서 부적합 | 대부분의 배포 환경에서 표준 |

지난 브랜치(Docker Compose)에서 "남은 과제"로 적어 둔 `database is locked` 가능성과, 프로젝트 메모의 "DB 엔진: 미정" 항목을 이번에 정리했다.

### 1-2. 바뀐 파일

| 파일 | 구분 | 내용 |
|---|---|---|
| `pyproject.toml`, `uv.lock` | 수정 | `psycopg[binary]` 추가 (파이썬이 PostgreSQL에 접속하는 도구) |
| `config/settings.py` | 수정 | `DATABASES`를 환경변수 유무로 PostgreSQL / SQLite 중 선택 |
| `docker-compose.yml` | 수정 | `db` 서비스, `postgres_data` 볼륨, `healthcheck` 추가. `web`, `celery`의 DB 환경변수 추가, `db.sqlite3` 마운트 삭제 |

### 1-3. 서비스 구성도 (4개 → 5개)

```
브라우저
   │ http://localhost:8000
   ▼
┌────────┐  작업 등록   ┌───────┐  작업 꺼내감  ┌────────┐
│  web   │ ───────────▶ │ redis │ ◀──────────── │ celery │
└───┬────┘              └───────┘               └───┬────┘
    │ 읽기/쓰기                                      │ 읽기/쓰기, 이미지 전달
    ▼                                                ▼
┌────────┐                                     ┌────────────┐
│   db   │ ◀───────────────────────────────────│ cv_service │ (콜백은 web으로)
│Postgres│                                     └────────────┘
└────────┘
```
`db`의 5432번 포트는 내 컴퓨터로 열지 않았다. compose 안의 컨테이너끼리만 접속할 수 있다.

### 1-4. DB 선택 규칙

`settings.py`는 환경변수 `POSTGRES_HOST`가 있는지만 본다.

| 상황 | `POSTGRES_HOST` | 사용하는 DB |
|---|---|---|
| `docker compose up` | 있음 (`db`) | PostgreSQL |
| Docker 없이 `runserver` | 없음 | SQLite (`db.sqlite3`) |

### 1-5. 환경변수

| 환경변수 | 기본값 | compose에서 넣는 값 | 설명 |
|---|---|---|---|
| `POSTGRES_HOST` | 없음 (이 값이 있어야 PostgreSQL 사용) | `db` | DB 서버 주소 = 서비스 이름 |
| `POSTGRES_DB` | `mom_vision` | `mom_vision` | DB 이름 |
| `POSTGRES_USER` | `postgres` | `postgres` | 접속 사용자 |
| `POSTGRES_PASSWORD` | 빈 문자열 | `postgres` | 비밀번호 (**개발용 값**) |
| `POSTGRES_PORT` | `5432` | (넣지 않음) | PostgreSQL 기본 포트 |

### 1-6. 데이터 처리 결정

- 기존 `db.sqlite3`의 데이터는 **옮기지 않고 새로 시작**했다. (개발 데이터라 회원가입·업로드를 다시 하는 게 더 빠르다.)
- 새 DB는 완전히 빈 상태라 `migrate`로 테이블을 만들고 `createsuperuser`로 관리자를 다시 만들어야 한다.
- 기존 `db.sqlite3` 파일은 지우지 않고 남아 있다 (Docker 이미지에는 `.dockerignore` 때문에 들어가지 않음). 백업 용도로 둬도 되고 지워도 된다.
- `media/` 폴더의 예전 업로드 이미지는 파일로는 남아 있지만, 새 DB에는 그 이미지를 가리키는 기록이 없다.

### 1-7. 실행과 관리 명령

```bash
docker compose build                                      # psycopg 추가 후 이미지를 다시 만듦
docker compose up -d                                      # 백그라운드로 전체 실행
docker compose exec web python manage.py migrate          # 새 DB에 테이블 생성
docker compose exec web python manage.py createsuperuser  # 관리자 계정 생성
docker compose exec db psql -U postgres -d mom_vision     # DB에 직접 접속해서 확인 (\dt: 테이블 목록, \q: 나가기)
docker compose down                                       # 컨테이너 정리 (데이터는 볼륨에 남음)
docker compose down -v                                    # 컨테이너 + 볼륨까지 삭제 (DB 데이터가 사라짐, 주의)
```

### 1-8. 확인한 것 (브라우저 수동 확인)
- 회원가입, 게시물 업로드, 좋아요, 댓글 작성, AI 분석 모두 정상 동작
- 자동 테스트(`manage.py test`)는 이번 브랜치에서는 돌려 보지 않았다.

---

## 2. 구성요소 단위 코드리뷰

### 2-1. `config/settings.py`의 `DATABASES`
- **왜 이렇게**: 지난번 주소 3종을 환경변수로 바꾼 것과 같은 방식이다. 한 코드로 Docker(PostgreSQL)와 로컬(SQLite)을 모두 지원한다.
- **잘한 점**: `POSTGRES_HOST`가 있는 경우에만 PostgreSQL 설정을 만들고, 그 안에서는 `os.environ["POSTGRES_HOST"]`로 꺼낸다. 값이 없으면 애초에 이 분기에 들어오지 않으므로 안전하다. 로컬 실행 방식이 깨지지 않는다.
- **다시 볼 점**: 개발은 SQLite, Docker는 PostgreSQL로 갈라져서, "로컬에서는 되는데 Docker에서만 안 되는" 차이(DB마다 다른 동작)가 생길 수 있다. 배포 단계에서는 PostgreSQL 하나로 통일하는 것도 고려할 만하다.

### 2-2. `docker-compose.yml`의 `db` 서비스
- **왜 이렇게**: 공식 `postgres:17` 이미지를 그대로 쓰고, `POSTGRES_DB/USER/PASSWORD`로 처음 켤 때 DB와 사용자를 자동으로 만든다.
- **잘한 점**
  - 데이터 폴더를 이름 있는 볼륨(`postgres_data`)에 연결해서 컨테이너를 지워도 데이터가 남는다.
  - `healthcheck`로 "접속 받을 준비 완료"를 확인한다.
  - 5432를 `ports`로 열지 않아 외부에서 DB에 직접 접속할 수 없다.
- **다시 볼 점**
  - 비밀번호가 `db`, `web`, `celery` 3곳에 똑같이 적혀 있다 (한 곳만 바꾸면 접속이 깨짐).
  - 관리자 계정(`postgres`)을 앱이 그대로 쓴다. 배포 때는 권한을 줄인 별도 사용자가 좋다.
  - 5432를 열지 않았으므로 DBeaver 같은 외부 도구로는 접속이 안 된다 (필요하면 `ports`를 추가하거나 `docker compose exec db psql`을 쓴다).

### 2-3. `web`·`celery`의 `depends_on` 변경
- **왜 이렇게**: `migrate`나 서버가 DB보다 먼저 뜨면 접속 에러가 난다. `condition: service_healthy`는 `db`의 `healthcheck`가 성공할 때까지 기다린다.
- **잘한 점**: 지난 브랜치에서 "시작 순서만 보장한다"고 적어 둔 한계를 DB에 대해서는 해결했다.
- **다시 볼 점**: `redis`는 여전히 `service_started`만 확인한다. `redis`에도 `healthcheck`를 달 수 있다.

### 2-4. `psycopg[binary]`
- **왜 이렇게**: `[binary]`는 PostgreSQL 연결용 C 라이브러리를 패키지 안에 같이 담고 있다. Dockerfile에 `apt install` 줄을 추가하지 않아도 되고, 그래서 Dockerfile은 이번에 손대지 않았다.
- **다시 볼 점**: 이미지 크기를 극단적으로 줄여야 할 때는 `binary` 대신 시스템 라이브러리 방식을 검토한다. 지금은 불필요하다.

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `config/settings.py` — DATABASES

```python
if os.environ.get("POSTGRES_HOST"):                                  # 환경변수 POSTGRES_HOST가 있으면(= Docker 안에서 실행 중이면) PostgreSQL을 사용
    DATABASES = {                                                     # Django에게 알려 줄 DB 설정 묶음
        'default': {                                                  # 기본으로 쓸 DB 하나
            'ENGINE': 'django.db.backends.postgresql',                # 이 DB가 PostgreSQL이라고 알려 주는 접속 모듈 이름
            'NAME': os.environ.get("POSTGRES_DB", "mom_vision"),      # 사용할 DB 이름 (환경변수가 없으면 mom_vision)
            'USER': os.environ.get("POSTGRES_USER", "postgres"),      # DB에 접속할 사용자 이름
            'PASSWORD': os.environ.get("POSTGRES_PASSWORD", ""),      # 그 사용자의 비밀번호
            'HOST': os.environ["POSTGRES_HOST"],                      # DB 서버 주소 (compose에서는 서비스 이름 db). if에서 있다고 확인했으니 바로 읽음
            'PORT': os.environ.get("POSTGRES_PORT", "5432"),          # PostgreSQL의 기본 포트
        }
    }
else:                                                                 # 환경변수가 없으면(= Docker 없이 로컬 실행) 기존 방식 유지
    DATABASES = {                                                     # 기존 sqlite 설정 그대로
        'default': {                                                  # 기본으로 쓸 DB 하나
            'ENGINE': 'django.db.backends.sqlite3',                   # sqlite3 접속 모듈
            'NAME': BASE_DIR / 'db.sqlite3',                          # 프로젝트 폴더의 db.sqlite3 파일
        }
    }
```

### 3-2. `docker-compose.yml` (현재 전체)

```yaml
services:                                   # 띄울 컨테이너(서비스)들의 목록 시작

  redis:                                    # 서비스 이름. 다른 컨테이너가 "redis"라는 이름으로 이 컨테이너를 찾음
    image: redis:7                          # 직접 빌드하지 않고 공식 Redis 이미지를 그대로 사용

  db:                                       # PostgreSQL 서버 컨테이너. 이름이 "db"라 다른 컨테이너가 "db"로 이 DB를 찾음
    image: postgres:17                      # 공식 PostgreSQL 이미지를 그대로 사용
    environment:                            # 이 컨테이너가 처음 켜질 때 DB를 만드는 데 쓰는 값
      POSTGRES_DB: mom_vision               # 만들어 둘 DB 이름 (settings.py의 NAME과 같아야 함)
      POSTGRES_USER: postgres               # DB 관리자 사용자 이름
      POSTGRES_PASSWORD: postgres           # 그 사용자의 비밀번호 (개발용 값. 배포 때는 반드시 바꿀 것)
    volumes:
      - postgres_data:/var/lib/postgresql/data   # DB 파일이 저장되는 폴더를 이름 있는 볼륨에 연결해 컨테이너를 지워도 데이터가 남게 함
    healthcheck:                            # "DB가 접속 받을 준비가 됐는지"를 주기적으로 검사하는 설정
      test: ["CMD-SHELL", "pg_isready -U postgres -d mom_vision"]  # pg_isready: PostgreSQL이 연결 가능한 상태인지 알려 주는 도구
      interval: 3s                          # 3초마다 검사
      timeout: 3s                           # 검사 한 번에 최대 3초까지 기다림
      retries: 10                           # 10번 연속 실패하면 "비정상"으로 판단

  web:                                      # Django 서버. 이름이 "web"이라 콜백 주소가 http://web:8000이 됨
    build: .                                # 현재 폴더(루트)의 Dockerfile로 이미지를 만듦
    ports:
      - "8000:8000"                         # 내 컴퓨터 8000번 포트 → 컨테이너 8000번 포트 (브라우저에서 접속하기 위함)
    environment:                            # 컨테이너 안에 환경변수를 넣음 (settings.py의 os.environ.get이 읽는 값)
      REDIS_URL: redis://redis:6379/0       # localhost 대신 redis 서비스 이름으로 접속
      INTERNAL_BASE_URL: http://web:8000    # 콜백 주소의 기준을 web 서비스로 지정
      CV_SERVICE_BASE_URL: http://cv_service:8001  # cv_service 서비스 이름으로 접속
      POSTGRES_HOST: db                     # DB 서버 주소 = db 서비스 이름 (이 값이 있으면 settings.py가 PostgreSQL을 사용)
      POSTGRES_DB: mom_vision               # 접속할 DB 이름
      POSTGRES_USER: postgres               # 접속할 사용자
      POSTGRES_PASSWORD: postgres           # 비밀번호 (db 서비스의 값과 같아야 함)
    volumes:
      - ./media:/app/media                  # 업로드된 이미지는 내 컴퓨터의 media 폴더와 연결 (DB와 달리 파일은 그대로 폴더에 저장)
    depends_on:
      redis:
        condition: service_started          # redis는 "시작"만 되면 충분
      db:
        condition: service_healthy          # db는 위의 healthcheck가 "준비 완료"라고 할 때까지 기다린 뒤 시작

  celery:                                   # Celery 워커. web과 같은 코드를 쓰고 실행 명령만 다름
    build: .                                # web과 같은 Dockerfile로 이미지를 만듦
    command: celery -A config worker -l info   # CMD를 덮어써서 Django 서버 대신 Celery 워커를 실행
    environment:                            # web과 같은 환경변수 (워커도 Redis, DB, 서비스 주소를 알아야 함)
      POSTGRES_HOST: db                     # DB 서버 주소 = db 서비스 이름
      POSTGRES_DB: mom_vision               # 접속할 DB 이름
      POSTGRES_USER: postgres               # 접속할 사용자
      POSTGRES_PASSWORD: postgres           # 비밀번호 (db 서비스의 값과 같아야 함)
      REDIS_URL: redis://redis:6379/0       # 작업 큐로 쓸 Redis 주소
      INTERNAL_BASE_URL: http://web:8000    # 콜백 주소의 기준
      CV_SERVICE_BASE_URL: http://cv_service:8001  # cv_service 주소
    volumes:
      - ./media:/app/media                  # 워커도 같은 이미지 파일을 읽어야 함
    depends_on:
      redis:
        condition: service_started          # redis는 "시작"만 되면 충분
      db:
        condition: service_healthy          # db가 준비 완료될 때까지 기다린 뒤 시작

  cv_service:                               # FastAPI 이미지 분석 서버
    build: ./cv_service                     # cv_service 폴더의 Dockerfile로 이미지를 만듦
    env_file:                               # 파일 안의 KEY=값 줄들을 전부 컨테이너 환경변수로 넣어 줌
      - ./cv_service/.env                   # GEMINI_API_KEY가 들어 있는 파일. 이미지에는 굽지 않고 실행할 때만 주입됨
    ports:
      - "8001:8001"                         # 내 컴퓨터에서 직접 확인하기 위해 포트 열기

volumes:                                    # compose가 관리하는 이름 있는 볼륨 목록
  postgres_data:                            # DB 데이터를 보관할 볼륨 (위 db 서비스가 이 이름으로 연결함)
```

### 3-3. `pyproject.toml` — 추가된 의존성

```toml
    "psycopg[binary]>=3.3.6",   # 파이썬 ↔ PostgreSQL 접속 도구. [binary]는 필요한 C 라이브러리를 함께 담은 버전
```

---

## 4. 복습

### SQLite와 PostgreSQL의 차이: 공유 노트 vs 사서가 있는 도서관
- SQLite는 **여러 사람이 돌려 쓰는 노트 한 권**과 같다. 한 명이 쓰는 동안은 다른 사람이 쓰지 못하고 기다려야 한다. 오래 기다리면 `database is locked`가 난다.
- PostgreSQL은 **사서가 있는 도서관**과 같다. 사서(DB 서버)가 여러 사람의 요청을 받아 순서와 충돌을 알아서 정리한다.
- 그래서 `web`과 `celery`처럼 여러 프로그램이 동시에 DB를 쓸 때 PostgreSQL이 안전하다.

### DB가 바뀌면 `migrate`부터 다시
- 마이그레이션은 "테이블을 이렇게 만들어라"라는 설계도다. 설계도 파일(`migrations/`)은 그대로지만, **새 DB는 비어 있어서** 이 설계도를 다시 적용해야 테이블이 생긴다.
- 유저 정보도 옛 DB에 있었으므로 `createsuperuser`로 관리자를 새로 만들어야 한다.

### 바인드 마운트와 이름 있는 볼륨
- `./media:/app/media`: **내 폴더**를 컨테이너에 연결한다. 내 컴퓨터에서 파일이 보이고 직접 열 수 있다.
- `postgres_data:/var/lib/...`: **Docker가 관리하는 저장 공간**에 연결한다. 내 폴더에서는 안 보이지만 PostgreSQL 데이터 파일처럼 Docker가 알아서 다루는 데 적합하다.
- 둘 다 컨테이너를 지워도 데이터가 남는다. 단, `docker compose down -v`는 이름 있는 볼륨까지 지운다.

### `depends_on`의 두 가지 조건
- `service_started`: 컨테이너가 "시작"만 되면 된다.
- `service_healthy`: `healthcheck`가 성공해서 "일할 준비가 끝났다"고 확인될 때까지 기다린다.
- DB처럼 켜지는 데 몇 초 걸리는 프로그램은 `service_healthy`가 필요하다.

### `POSTGRES_DB/USER/PASSWORD`는 "처음 한 번만" 적용된다
- 공식 PostgreSQL 이미지는 **데이터 폴더가 비어 있을 때만** 이 값으로 DB와 사용자를 만든다. 볼륨에 이미 데이터가 있으면 나중에 이 값을 바꿔도 반영되지 않는다.
- 비밀번호나 DB 이름을 바꾸고 싶으면 `docker compose down -v`로 볼륨을 지워서 처음부터 다시 만들어야 한다 (데이터는 사라진다).

### 컨테이너 밖에서 DB로 접속할 수 없는 이유
- `db`에는 `ports`가 없다. compose 네트워크 안의 컨테이너끼리는 `db`라는 이름으로 접속할 수 있지만, 내 컴퓨터에서는 접속할 길이 없다.
- 데이터를 직접 보고 싶으면 `docker compose exec db psql ...`로 컨테이너 안에서 접속한다.

---

## 5. 트러블슈팅

이번 세션에서는 DB 연결과 마이그레이션 중에 실제로 겪은 에러는 없었다. 설정 단계의 사소한 실수(들여쓰기 위치 등)는 실행 전에 코드 확인에서 바로 고쳤다.

### 설계 판단: `depends_on`을 `service_started`에서 `service_healthy`로
- **문제 가능성**: PostgreSQL은 컨테이너가 시작된 뒤에도 몇 초 동안 접속을 받지 못한다. 그 사이에 `web`이나 `migrate`가 접속하면 에러가 난다.
- **해결**: `db`에 `healthcheck`를 달고 `web`과 `celery`가 `service_healthy`를 기다리게 했다.

### 남은 과제 (이번 브랜치에서는 하지 않음)
- 자동 테스트(`manage.py test`)를 PostgreSQL 환경에서도 돌려 보기 (이번에는 브라우저 수동 확인만 했다)
- 비밀번호를 `.env` 파일 하나로 모으기 (지금은 3곳에 중복)
- 배포 방식이 정해지면 `postgres` 관리자 계정 대신 권한을 줄인 사용자 사용, 서비스형 DB 사용 여부 검토
- DB 백업 방법 정리 (`pg_dump`)
- SQLite 분기를 유지할지, PostgreSQL 하나로 통일할지 결정
