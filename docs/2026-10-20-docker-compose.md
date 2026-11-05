# Docker Compose로 전체 서버 한 번에 띄우기 (2026-10-20)

브랜치: `feature/docker-compose`

> 한 줄 요약: 지금까지는 터미널 4개(Redis / cv_service / Celery / Django)를 따로 켜야 했는데, `docker compose up` 한 번으로 4개가 같이 뜨도록 바꿨다. 컨테이너 안에서 사진 업로드 → AI 분석 → 결과 화면까지 끝까지 동작하는 것을 확인했다.

---

## 1. 기술문서

### 1-1. 이 작업이 필요했던 이유

AI 분석 기능은 서로 다른 프로그램 4개가 동시에 켜져 있어야 동작한다.

| 프로그램 | 하는 일 | 포트 |
|---|---|---|
| Django (`web`) | 화면과 API를 제공, 분석 결과 저장 | 8000 |
| Celery (`celery`) | 오래 걸리는 분석 작업을 뒤에서 대신 처리하는 일꾼 | 없음 |
| Redis (`redis`) | Django가 "이 작업 해줘"라고 적어 두는 대기표 보관함 | 6379 (내부용) |
| FastAPI (`cv_service`) | 사진을 보고 옷 탐지 + Gemini로 스타일 해석 | 8001 |

**Docker**는 "프로그램 + 실행에 필요한 환경"을 하나의 상자(컨테이너)에 담는 도구다. **Docker Compose**는 여러 상자를 한 파일(`docker-compose.yml`)에 적어 두고 한 번에 켜고 끄는 도구다. 내 컴퓨터에 파이썬 버전이나 Redis를 따로 깔지 않아도 같은 환경이 재현된다.

### 1-2. 이번에 추가·변경된 파일

| 파일 | 구분 | 역할 |
|---|---|---|
| `Dockerfile` (루트) | 신규 | Django와 Celery가 함께 쓰는 이미지 설계도 |
| `.dockerignore` (루트) | 신규 | 이미지에 넣지 않을 파일 목록 |
| `cv_service/Dockerfile` | 신규 | FastAPI 이미지 설계도 |
| `cv_service/.dockerignore` | 신규 | cv_service 이미지에 넣지 않을 파일 목록 |
| `docker-compose.yml` | 신규 | 4개 서비스를 어떻게 묶어 띄울지 적은 파일 |
| `config/settings.py` | 수정 | 주소 3종과 `ALLOWED_HOSTS`를 컨테이너 환경에 맞게 변경 |

### 1-3. 서비스 구성도

```
브라우저
   │ http://localhost:8000
   ▼
┌────────┐  ① 작업 등록  ┌───────┐  ② 작업 꺼내감  ┌────────┐
│  web   │ ────────────▶ │ redis │ ◀────────────── │ celery │
│ Django │               └───────┘                 └───┬────┘
└────────┘                                             │ ③ 이미지 전달
   ▲                                                   ▼
   │ ④ 분석 결과 콜백 (http://web:8000/...)       ┌────────────┐
   └───────────────────────────────────────────── │ cv_service │
                                                   │  FastAPI   │
                                                   └────────────┘
```

### 1-4. 컨테이너끼리 부르는 이름 (가장 중요한 개념)

컨테이너 안에서 `localhost`는 "그 컨테이너 자기 자신"이다. 그래서 Django 컨테이너가 `localhost:6379`로 Redis를 찾으면 못 찾는다. Compose는 같은 네트워크 안의 컨테이너를 **서비스 이름**으로 부를 수 있게 해 준다.

| 용도 | 로컬 실행 때 | Docker 안에서 |
|---|---|---|
| Redis 주소 | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| 콜백을 받을 Django 주소 | `http://localhost:8000` | `http://web:8000` |
| cv_service 주소 | `http://localhost:8001` | `http://cv_service:8001` |

### 1-5. 환경변수

`config/settings.py`는 아래 환경변수가 있으면 그 값을, 없으면 기존 `localhost` 값을 쓴다. 그래서 Docker 없이 예전 방식으로 실행해도 그대로 동작한다.

| 환경변수 | 기본값 | compose에서 넣는 값 |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | `redis://redis:6379/0` |
| `INTERNAL_BASE_URL` | `http://localhost:8000` | `http://web:8000` |
| `CV_SERVICE_BASE_URL` | `http://localhost:8001` | `http://cv_service:8001` |
| `GEMINI_API_KEY` (cv_service) | 없음 | `cv_service/.env` 파일에서 주입 |

### 1-6. 실행 방법

```bash
docker compose build   # 이미지 만들기 (처음 한 번, 의존성이 바뀌면 다시)
docker compose up      # 4개 한꺼번에 실행 (중지: Ctrl+C)
docker compose up -d   # 백그라운드 실행
docker compose ps      # 상태 확인
docker compose logs -f # 로그 보기
docker compose down    # 컨테이너 정리
```

---

## 2. 구성요소 단위 코드리뷰

이번 브랜치에는 클래스나 함수가 없어서, 파일(서비스) 단위로 "왜 이렇게 썼는지 / 잘한 점 / 나중에 다시 볼 점"을 정리한다.

### 2-1. 루트 `Dockerfile` (web과 celery가 공유)
- **왜 이렇게**: Django와 Celery는 같은 코드를 쓰고 실행 명령만 다르다. 이미지를 하나만 만들고, celery는 compose에서 `command`로 실행 명령만 바꿨다.
- **잘한 점**: `pyproject.toml`과 `uv.lock`만 먼저 복사해서 설치하고, 코드는 맨 마지막에 복사했다. 코드만 바뀌면 오래 걸리는 패키지 설치 단계는 캐시로 건너뛴다. `--frozen`으로 `uv.lock`에 적힌 버전 그대로 설치해서 어디서나 같은 환경이 나온다.
- **다시 볼 점**: `uv`를 `latest` 태그로 가져와서 시점에 따라 버전이 달라질 수 있다. 서버 실행도 개발용 `runserver`다.

### 2-2. 루트 `.dockerignore`
- **왜 이렇게**: `COPY . .`는 폴더를 통째로 복사하므로, 빼야 할 것을 이 파일로 막는다.
- **잘한 점**: `.venv`를 제외했다. 내 컴퓨터의 가상환경을 복사하면 컨테이너(리눅스 slim)와 맞지 않아 깨질 수 있다. `db.sqlite3`와 `media`도 이미지에 굽지 않고 볼륨으로 연결한다. `cv_service`는 자체 Dockerfile이 있어서 제외했다.
- **다시 볼 점**: `tests` 폴더 등은 아직 이미지에 같이 들어간다.

### 2-3. `cv_service/Dockerfile`
- **왜 이렇게**: Django와 별도 가상환경을 쓰는 독립 프로젝트라 자체 Dockerfile을 둔다. 구조는 루트와 같고 `app` 폴더만 복사하며 8001 포트로 uvicorn을 띄운다.
- **잘한 점**: `cv_service/.dockerignore`가 `.env`를 제외한다. API 키가 이미지 안에 굳어 들어가지 않는다.
- **다시 볼 점**: 모델 가중치(Hugging Face)를 이미지나 볼륨에 저장하지 않아서, 컨테이너를 새로 만들 때마다 다시 내려받는다. 첫 분석이 느린 원인 중 하나다.

### 2-4. `docker-compose.yml`
- **왜 이렇게**: 서비스 이름(`web`, `redis`, `cv_service`)이 곧 컨테이너 간 주소가 되도록 `settings.py`의 주소와 정확히 맞췄다.
- **잘한 점**: `GEMINI_API_KEY`는 `env_file`로 실행할 때만 주입하고 이미지에는 남기지 않는다. `web`과 `celery`가 같은 `db.sqlite3`와 `media`를 보도록 볼륨을 맞췄다.
- **다시 볼 점**
  - `depends_on`은 "시작 순서"만 보장하고 "준비 완료"는 기다리지 않는다. 지금은 우연히 문제가 없었지만, 느린 PC에서는 Redis가 준비되기 전에 celery가 접속을 시도할 수 있다 (`healthcheck`로 해결 가능).
  - sqlite 파일을 web과 celery가 동시에 쓴다. 쓰기가 겹치면 `database is locked`가 날 수 있다 (PostgreSQL 전환 시 해결).
  - celery가 root 권한으로 실행되어 경고가 나온다.

### 2-5. `config/settings.py` 변경분
- **왜 이렇게**: `os.environ.get("이름", "기본값")`은 환경변수가 있으면 쓰고 없으면 기본값을 쓴다. 코드를 하나로 두고 실행 환경에 따라 주소만 바꾼다.
- **잘한 점**: 기본값을 기존 `localhost`로 둬서 Docker 없이 실행하는 방식도 깨지지 않는다.
- **다시 볼 점**: `ALLOWED_HOSTS`는 아직 코드에 직접 적혀 있다. `SECRET_KEY`와 `DEBUG`도 개발용 값 그대로다.

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `Dockerfile` (루트)

```dockerfile
# 파이썬 3.12가 이미 깔려 있는 가벼운 리눅스를 출발점으로 삼음 (pyproject의 requires-python >=3.12에 맞춤)
FROM python:3.12-slim

# uv(패키지 설치 도구)를 공식 이미지에서 복사해 옴
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 이후 명령어를 실행할 컨테이너 안의 작업 폴더 (없으면 자동으로 만들어 줌)
WORKDIR /app

# 의존성 목록 파일 2개만 먼저 복사 (코드가 바뀌어도 이 층은 캐시되어 재설치를 건너뜀)
COPY pyproject.toml uv.lock ./

# uv.lock에 적힌 그대로 패키지를 설치 (--frozen: 잠금 파일을 새로 고치지 않고 그대로 따름)
RUN uv sync --frozen

# 설치된 가상환경(.venv)의 실행 파일을 PATH 맨 앞에 추가: python, celery 등을 이름만으로 실행할 수 있게 됨
ENV PATH="/app/.venv/bin:$PATH"

# Django 프로젝트 코드를 전부 복사 (자주 바뀌는 것이라 맨 마지막에 복사)
# 무엇을 제외할지는 .dockerignore가 결정함
COPY . .

# 이 컨테이너가 8000번 포트를 쓴다는 안내 (실제 연결은 실행할 때 -p 또는 compose의 ports로 함)
EXPOSE 8000

# 컨테이너가 시작될 때 실행할 명령어: Django 개발 서버 켜기
# 0.0.0.0: 컨테이너 밖에서도 접속 가능하게 함 (기본값 127.0.0.1은 컨테이너 안에서만 접속됨)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
```

### 3-2. `.dockerignore` (루트)

```
# 로컬 가상환경: 컨테이너 안에서 uv sync로 새로 만들기 때문에 복사하면 안 됨
.venv
__pycache__
*.pyc

# git / 에디터 / Claude 설정은 이미지에 불필요
.git
.vscode
.claude

# 로컬 DB와 업로드 파일: 이미지에 굽지 않고 나중에 볼륨으로 연결할 것
db.sqlite3
media

# 문서와 별도 서비스(cv_service는 자체 Dockerfile이 있음)
docs
cv_service
```

### 3-3. `cv_service/Dockerfile`

```dockerfile
# 파이썬 3.12가 이미 깔려 있는 가벼운 리눅스를 출발점으로 삼음 (pyproject의 requires-python >=3.12에 맞춤)
FROM python:3.12-slim

# uv(패키지 설치 도구)를 공식 이미지에서 복사해 옴
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 이후 명령어를 실행할 컨테이너 안의 작업 폴더 (없으면 자동으로 만들어 줌)
WORKDIR /app

# 의존성 목록 파일 2개만 먼저 복사 (코드보다 먼저 복사해야 "층 캐시"가 효과를 냄)
COPY pyproject.toml uv.lock ./

# uv.lock에 적힌 그대로 패키지를 설치 (--frozen: 잠금 파일을 새로 고치지 않고 그대로 따름)
RUN uv sync --frozen

# 설치된 가상환경(.venv)의 실행 파일을 PATH 맨 앞에 추가: uvicorn을 이름만으로 실행할 수 있게 됨
ENV PATH="/app/.venv/bin:$PATH"

# 서버 코드를 복사 (자주 바뀌는 것이라 맨 마지막에 복사)
COPY app ./app

# 이 컨테이너가 8001번 포트를 쓴다는 안내 (실제 연결은 실행할 때 -p로 함)
EXPOSE 8001

# 컨테이너가 시작될 때 실행할 명령어: uvicorn으로 FastAPI 서버 켜기
# --host 0.0.0.0: 컨테이너 밖에서도 접속 가능하게 함 (기본값 127.0.0.1은 컨테이너 안에서만 접속됨)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

### 3-4. `docker-compose.yml`

```yaml
services:                                   # 띄울 컨테이너(서비스)들의 목록 시작

  redis:                                    # 서비스 이름. 다른 컨테이너가 "redis"라는 이름으로 이 컨테이너를 찾음
    image: redis:7                          # 직접 빌드하지 않고 공식 Redis 이미지를 그대로 사용

  web:                                      # Django 서버. 이름이 "web"이라 콜백 주소가 http://web:8000이 됨
    build: .                                # 현재 폴더(루트)의 Dockerfile로 이미지를 만듦
    ports:
      - "8000:8000"                         # 내 컴퓨터 8000번 포트 → 컨테이너 8000번 포트 (브라우저에서 접속하기 위함)
    environment:                            # 컨테이너 안에 환경변수를 넣음 (settings.py의 os.environ.get이 읽는 값)
      REDIS_URL: redis://redis:6379/0       # localhost 대신 redis 서비스 이름으로 접속
      INTERNAL_BASE_URL: http://web:8000    # 콜백 주소의 기준을 web 서비스로 지정
      CV_SERVICE_BASE_URL: http://cv_service:8001  # cv_service 서비스 이름으로 접속
    volumes:
      - ./db.sqlite3:/app/db.sqlite3        # 내 컴퓨터의 DB 파일을 컨테이너에 연결해서 데이터가 유지되게 함
      - ./media:/app/media                  # 업로드된 이미지도 같은 방식으로 연결
    depends_on:
      - redis                               # redis가 먼저 시작된 뒤에 web을 시작

  celery:                                   # Celery 워커. web과 같은 코드를 쓰고 실행 명령만 다름
    build: .                                # web과 같은 Dockerfile로 이미지를 만듦
    command: celery -A config worker -l info   # CMD를 덮어써서 Django 서버 대신 Celery 워커를 실행
    environment:                            # web과 같은 환경변수 (워커도 Redis와 서비스 주소를 알아야 함)
      REDIS_URL: redis://redis:6379/0
      INTERNAL_BASE_URL: http://web:8000
      CV_SERVICE_BASE_URL: http://cv_service:8001
    volumes:
      - ./db.sqlite3:/app/db.sqlite3        # 워커도 같은 DB 파일을 봐야 결과를 저장할 수 있음
      - ./media:/app/media                  # 워커도 같은 이미지 파일을 읽어야 함
    depends_on:
      - redis                               # redis가 먼저 시작된 뒤에 시작

  cv_service:                               # FastAPI 이미지 분석 서버
    build: ./cv_service                     # cv_service 폴더의 Dockerfile로 이미지를 만듦
    env_file:                               # 파일 안의 KEY=값 줄들을 전부 컨테이너 환경변수로 넣어 줌
      - ./cv_service/.env                   # GEMINI_API_KEY가 들어 있는 파일. 이미지에는 굽지 않고 실행할 때만 주입됨
    ports:
      - "8001:8001"                         # 내 컴퓨터에서 직접 확인하기 위해 포트 열기
```

### 3-5. `config/settings.py` 변경분

```python
import os                                                 # 환경변수(os.environ)를 읽기 위해 os 모듈 불러오기

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "web"]        # 접속을 허용할 주소 목록. "web"은 cv_service가 콜백할 때 쓰는 compose 서비스 이름이라 꼭 필요함

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")      # 환경변수 REDIS_URL이 있으면 그 값, 없으면 기존 localhost 값 사용 (작업 큐)
CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")  # 결과 저장소도 같은 방식으로 환경변수 우선

INTERNAL_BASE_URL = os.environ.get("INTERNAL_BASE_URL", "http://localhost:8000")  # 콜백 주소의 기준. compose에서는 http://web:8000으로 덮어씀

CV_SERVICE_BASE_URL = os.environ.get("CV_SERVICE_BASE_URL", "http://localhost:8001")  # cv_service 주소. compose에서는 http://cv_service:8001로 덮어씀
```

---

## 4. 복습

### 이미지와 컨테이너
- **이미지**는 요리 레시피와 재료가 같이 들어 있는 밀키트, **컨테이너**는 그걸로 실제로 만든 요리다. 이미지 하나로 컨테이너를 여러 개 만들 수 있다. 이번에 `web`과 `celery`가 같은 이미지(`build: .`)에서 나온 것이 그 예다.
- `Dockerfile`은 이미지를 만드는 레시피이고, 위에서부터 한 줄씩 실행되며 **한 줄이 한 층**이 된다.

### 왜 `pyproject.toml`을 코드보다 먼저 복사할까 (층 캐시)
- Docker는 줄마다 결과를 저장해 두고, 그 줄과 그 위쪽이 하나도 안 바뀌었으면 다시 실행하지 않고 저장본을 쓴다.
- 코드는 자주 바뀌고 패키지 목록은 드물게 바뀐다. 그래서 의존성 설치를 위쪽에, 코드 복사를 아래쪽에 두면, 코드만 고쳤을 때 오래 걸리는 설치를 건너뛴다.
- 반대로 코드를 먼저 복사하면 한 글자만 고쳐도 매번 패키지를 다시 설치한다.

### `localhost`의 의미가 바뀐다
- 컨테이너 안의 `localhost`는 그 컨테이너 자신이다. 컨테이너끼리는 compose의 **서비스 이름**으로 부른다.
- 서버가 `127.0.0.1`(자기 자신만)이 아니라 `0.0.0.0`(밖에서 오는 연결도 받음)으로 켜져야 `ports`로 연결한 내 컴퓨터가 접속할 수 있다.

### `ports`와 `EXPOSE`의 차이
- `EXPOSE`는 안내 문구일 뿐이고 실제로 길을 열지는 않는다.
- `ports: "8000:8000"`이 "내 컴퓨터 포트:컨테이너 포트"를 실제로 이어 준다. redis는 `ports`가 없어서 내 컴퓨터에서는 접속되지 않고, 컨테이너끼리만 쓸 수 있다.

### 비밀 값은 이미지에 굽지 않는다
- 이미지는 파일처럼 공유될 수 있어서 API 키가 들어가면 같이 새어 나간다.
- 그래서 `.dockerignore`로 `.env`를 이미지에서 빼고, 실행할 때 `env_file`로만 넣는다.
- `GEMINI_API_KEY`는 코드에서 따로 읽지 않아도 된다. `genai.Client()`가 같은 이름의 환경변수를 자동으로 찾기 때문이다.

### `os.environ.get("이름", "기본값")`
- 환경변수가 있으면 그 값, 없으면 기본값을 돌려준다.
- 코드를 하나로 두고 실행 환경(내 컴퓨터 / Docker / 나중의 서버)에 따라 값만 바꿀 수 있는 가장 흔한 방법이다.

### 볼륨(`volumes`)
- 컨테이너는 지우면 안의 파일도 같이 사라진다. 지우면 안 되는 데이터(DB, 업로드 이미지)는 내 컴퓨터의 파일을 컨테이너에 연결(`./media:/app/media`)해서 밖에 남긴다.
- 주의: 연결하려는 파일(`./db.sqlite3`)이 내 컴퓨터에 아직 없으면, Docker가 파일이 아니라 같은 이름의 **폴더**를 만들어 버린다.

### `depends_on`은 "순서"만 보장한다
- redis 컨테이너가 "시작"되는 것과 redis가 "접속 받을 준비가 끝나는" 것은 다르다. 더 엄격하게 하려면 `healthcheck`를 쓴다.

---

## 5. 트러블슈팅

### 컨테이너 안에서는 `localhost`로 다른 서비스를 찾을 수 없었다
- **원인**: `settings.py`에 Redis, 콜백 서버, cv_service 주소가 모두 `localhost`로 박혀 있었다. 컨테이너 안의 `localhost`는 자기 자신이라서 그대로 두면 연결이 전부 실패한다.
- **해결**: 3개 주소를 `os.environ.get`으로 바꾸고, 기본값은 기존 `localhost`로 두어 Docker 없이 실행하는 방식도 유지했다. compose의 `environment`에서 서비스 이름 주소로 덮어썼다.
- **확인**: celery 시작 로그에 `transport: redis://redis:6379/0`이 찍혔고, 브라우저에서 분석 요청부터 결과 표시까지 정상 동작했다.

### 콜백이 `Host: web:8000`으로 들어오는 문제 (실행 전에 예방)
- **원인**: Django는 요청의 Host 헤더가 `ALLOWED_HOSTS`에 없으면 요청을 막는다(`DisallowedHost`). cv_service가 결과를 돌려줄 때 Host가 `web:8000`이 된다. 원래 `ALLOWED_HOSTS = []`는 `DEBUG=True`일 때 localhost 계열만 허용한다.
- **해결**: 실행해서 에러를 겪기 전에 설정을 읽고 미리 `"web"`을 허용 목록에 넣었다.

### `.env`가 이미지에서 빠져서 Gemini 키를 못 읽을 수 있는 문제 (실행 전에 예방)
- **원인**: `cv_service/.dockerignore`가 `.env`를 제외하므로(의도된 보안 조치) 컨테이너 안에는 키가 없다.
- **해결**: compose의 `cv_service`에 `env_file: ./cv_service/.env`를 추가해 실행할 때 환경변수로 주입했다.

### 남은 과제 (이번 브랜치에서는 하지 않음)
- cv_service 모델 가중치를 컨테이너를 새로 만들 때마다 다시 내려받음 → 모델 캐시 폴더를 볼륨으로 연결하면 해결
- `depends_on`에 `healthcheck` 추가
- sqlite 동시 쓰기 → PostgreSQL 전환 검토
- 운영용 서버(gunicorn 등), `DEBUG`/`SECRET_KEY`/`ALLOWED_HOSTS` 환경변수화
