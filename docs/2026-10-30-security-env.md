# 비밀값을 코드에서 `.env`로 옮기기 (2026-10-30)

브랜치: `feature/security-env` (보안 점검 A 브랜치)

> 한 줄 요약: 코드에 직접 적혀 있던 `SECRET_KEY`, `DEBUG`, DB 비밀번호를 `.env` 파일 한 곳으로 모았다. git 기록에 남아 있던 SECRET_KEY는 폐기하고 새 키로 바꿨다. 자동 테스트 49개 통과, Docker 재빌드 후 접속·재로그인·AI 분석까지 브라우저에서 정상 동작을 확인했다.

---

## 1. 기술문서

### 1-1. 왜 바꿨나

| 문제 | 위치 | 위험 |
|---|---|---|
| `SECRET_KEY`가 코드에 그대로 적혀 있음 | `config/settings.py` | 첫 커밋(`93b3af1`)부터 git 기록에 남아 있다. 저장소가 공개되면 누구나 이 키로 로그인 세션을 위조할 수 있다 |
| `DEBUG = True` 고정 | `config/settings.py` | 배포할 때 깜빡하면 에러 화면에 코드·설정·경로가 그대로 보인다 |
| DB 비밀번호가 3곳에 중복 | `docker-compose.yml` (db, web, celery) | 한 곳만 바꾸면 접속이 깨지고, 비밀번호가 코드에 노출된다 |

포트폴리오 저장소를 공개하기 전에 해야 할 보안 점검 10개 항목 중 1번(비밀값 분리)과 7번(설정 정리)에 해당한다.

### 1-2. 바뀐 파일

| 파일 | 구분 | 내용 |
|---|---|---|
| `config/settings.py` | 수정 | `SECRET_KEY`, `DEBUG`를 환경변수에서 읽음 |
| `docker-compose.yml` | 수정 | `web`·`celery`에 `env_file: .env` 추가, `db`는 `${...}`로 값을 읽음, 중복된 DB 비밀번호 줄 삭제 |
| `.env.example` | 새 파일 | 루트 `.env`의 견본 (가짜 값, git에 올림) |
| `cv_service/.env.example` | 새 파일 | `cv_service/.env`의 견본 |
| `.dockerignore` | 수정 | `.env` 추가 (web 이미지에 비밀값이 복사되지 않게) |
| `README.md` | 수정 | 사전 준비(`.env`) 섹션 추가, 터미널 실행·테스트 명령에 `--env-file .env` 추가 |

### 1-3. 비밀값이 흘러가는 길

```
.env (git 제외, 진짜 값)
  │
  ├─ uv run --env-file .env ...        → 터미널 실행(runserver, celery, test)의 환경변수
  │
  ├─ docker-compose.yml  env_file: .env → web, celery 컨테이너의 환경변수 (전부)
  │
  └─ docker-compose.yml  ${POSTGRES_*}  → db 컨테이너의 환경변수 (3개만)
                                              │
                                 settings.py의 os.environ이 읽음

.env.example (git 포함, 가짜 값) → 새로 받은 사람이 cp로 복사해 .env를 만드는 견본
```

### 1-4. 환경변수

| 변수 | 없을 때 | 개발용 값 | 설명 |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | **`KeyError`로 서버가 멈춤** | 새로 만든 키 | 세션·CSRF 토큰 서명용 비밀키 |
| `DJANGO_DEBUG` | `False` (꺼짐) | `True` | 정확히 문자열 `"True"`일 때만 켜짐 |
| `POSTGRES_DB` | (compose에서 빈 값) | `mom_vision` | DB 이름 |
| `POSTGRES_USER` | (compose에서 빈 값) | `postgres` | 접속 사용자 |
| `POSTGRES_PASSWORD` | (compose에서 빈 값) | `postgres` | 비밀번호 (**개발용 값**) |

`POSTGRES_HOST`는 `.env`에 넣지 않는다. 이 값이 있으면 settings.py가 PostgreSQL로 전환되므로, 터미널 실행은 계속 SQLite를 쓰도록 compose의 `environment`에만 둔다.

### 1-5. 실행 명령 변화

| 실행 | 전 | 후 |
|---|---|---|
| Django 서버 | `uv run python manage.py runserver` | `uv run --env-file .env python manage.py runserver` |
| Celery | `uv run celery -A config worker -l info` | `uv run --env-file .env celery -A config worker -l info` |
| 테스트 | `uv run python manage.py test` | `uv run --env-file .env python manage.py test` |
| Docker | `docker compose up` | 그대로 (`env_file`이 대신 넣어 줌) |

### 1-6. 확인한 것
- `uv run --env-file .env python manage.py test`: 49개 전부 통과
- `docker compose config`: db의 `POSTGRES_PASSWORD`가 `postgres`로 채워지는 것 확인
- `docker compose up --build` 후 브라우저 확인
  - `variable is not set` 경고 없음
  - 피드 화면이 CSS와 함께 정상 표시
  - 기존 로그인이 풀림 → 다시 로그인하면 정상 (SECRET_KEY 교체가 적용됐다는 증거)
  - 이미지 업로드 → 분석 중 → 결과까지 정상

---

## 2. 구성요소 단위 코드리뷰

### 2-1. `SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]`
- **왜 이렇게**: 비밀키는 없으면 실행 자체가 되면 안 되는 값이라 `.get()`이 아니라 `[]`로 꺼낸다. 값이 없으면 `KeyError`가 나서 서버가 바로 멈춘다.
- **잘한 점**: "키 없이 조용히 뜨는" 사고가 불가능하다. 기본값을 두지 않았으므로 코드 어디에도 키가 남지 않는다.
- **다시 볼 점**: 에러 메시지가 `KeyError: 'DJANGO_SECRET_KEY'`뿐이라 처음 보는 사람에게는 불친절하다. README의 사전 준비 섹션으로 보완했다.

### 2-2. `DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"`
- **왜 이렇게**: 환경변수는 항상 문자열이다. `bool("False")`는 비어 있지 않은 문자열이라 `True`가 되므로, 문자열을 직접 비교해야 한다.
- **잘한 점**: 값이 없거나 오타가 나면 **꺼지는 쪽**으로 동작한다 (안전한 기본값). 배포 때 코드는 그대로 두고 `.env`만 바꾸면 된다.
- **다시 볼 점**: `"true"`(소문자)도 꺼짐으로 처리된다. 지금은 `.env.example`에 `True`로 적어 두어 문제없다. `=` 뒤 공백이 두 칸인 것은 동작에는 영향 없다.

### 2-3. `docker-compose.yml`: `env_file`과 `${...}`를 나눠 쓴 것
- **왜 이렇게**: Django(web, celery)는 `.env`의 값이 전부 필요하고, PostgreSQL(db)은 3개만 필요하다.
- **잘한 점**: db 컨테이너에는 Django SECRET_KEY가 들어가지 않는다 (최소 권한 원칙). 비밀번호를 고칠 곳이 `.env` 한 곳으로 줄었다.
- **다시 볼 점**: healthcheck 줄의 `-U postgres -d mom_vision`은 여전히 직접 적혀 있다. DB 이름이나 사용자를 바꾸면 이 줄도 함께 바꿔야 한다.

### 2-4. `.env.example`
- **왜 이렇게**: `.env`는 git에 올라가지 않으므로, 저장소를 새로 받은 사람은 어떤 값을 채워야 하는지 알 수 없다. 항목 이름만 담은 견본을 함께 올린다.
- **잘한 점**: 진짜 키 자리에 `여기에_새로_만든_키`라는 가짜 값이 들어 있어서 실수로 진짜 키가 올라갈 일이 없다.

### 2-5. `.dockerignore`에 `.env` 추가
- **왜 이렇게**: Dockerfile의 `COPY . .`는 `.dockerignore`에 없는 파일을 전부 이미지에 복사한다. `cv_service/.dockerignore`에는 `.env`가 있었지만 루트에는 없었다. 그래서 루트에 `.env`를 만드는 순간 SECRET_KEY가 web 이미지 안에 파일로 구워지게 된다.
- **잘한 점**: 비밀값은 실행할 때 `env_file`로만 들어가고 이미지에는 남지 않는다. 이미지를 다른 곳에 올려도 키가 새지 않는다.

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `config/settings.py`

```python
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]                # .env에서 비밀키를 읽음. 없으면 KeyError로 서버가 바로 멈춤
DEBUG = os.environ.get("DJANGO_DEBUG", "False") == "True"   # 문자열이 정확히 "True"일 때만 켜짐. 값이 없으면 "False" → 꺼짐
```

### 3-2. `.env.example`

```
# 이 파일을 복사해 .env로 저장한 뒤 값을 채우세요: cp .env.example .env
DJANGO_SECRET_KEY=여기에_새로_만든_키     # 가짜 값. 진짜 키는 .env에만 넣음
DJANGO_DEBUG=True                         # 개발 중이라 켜 둠 (배포 때 False)
POSTGRES_DB=mom_vision                    # Docker PostgreSQL DB 이름
POSTGRES_USER=postgres                    # 접속 사용자
POSTGRES_PASSWORD=postgres                # 비밀번호 (개발용 값)
```
(실제 `.env` 파일에는 줄 끝 주석을 쓰지 않는다. 위 주석은 설명용이다.)

진짜 `.env`의 SECRET_KEY는 작은따옴표로 감싼다.
```
DJANGO_SECRET_KEY='(발급받은 키 전체'      # '...' 안은 글자 그대로. $나 #가 섞여 있어도 잘리지 않음
```

### 3-3. `docker-compose.yml` (바뀐 부분)

```yaml
  db:
    environment:                            # 이 컨테이너가 처음 켜질 때 DB를 만드는 데 쓰는 값
      POSTGRES_DB: ${POSTGRES_DB}           # ${...}: compose가 같은 폴더의 .env에서 같은 이름의 값을 찾아 채워 넣음
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

  web:
    env_file:                               # .env의 모든 줄을 컨테이너 환경변수로 넣음 (SECRET_KEY, DEBUG, DB 접속 정보)
      - .env
    environment:                            # 비밀이 아닌 "Docker 안에서의 주소" 값은 그대로 여기에 둠
      REDIS_URL: redis://redis:6379/0
      INTERNAL_BASE_URL: http://web:8000
      CV_SERVICE_BASE_URL: http://cv_service:8001
      POSTGRES_HOST: db                     # 이 값이 있으면 settings.py가 PostgreSQL을 사용

  celery:
    env_file:                               # web과 같은 .env를 사용
      - .env
```

### 3-4. `.dockerignore` (추가한 줄)

```
.env      # 비밀값 파일은 이미지에 복사하지 않음 (실행할 때 env_file로만 주입)
```

---

## 4. 복습

### `.env`와 `.env.example`: 작성한 신청서와 빈 양식
- `.env`는 **내 정보를 적은 신청서**다. 진짜 값이 들어 있고 git에 올라가지 않는다.
- `.env.example`은 **빈 신청서 양식**이다. 항목 이름과 가짜 값만 있고 git에 올라간다.
- 새 키는 **`.env`에만** 넣는다. 양식에 진짜 값을 적으면 그대로 git에 올라간다.

### `cp`는 덮어쓴다
- `cp A B`는 B가 이미 있으면 경고 없이 내용을 바꾼다. 휴지통도 없다.
- 불안하면 `cp -n`을 쓴다 (`-n`: 같은 이름이 있으면 복사하지 않음).

### `os.environ["X"]` vs `os.environ.get("X", 기본값)`
- `[]`: 없으면 에러. **없으면 안 되는 값**(SECRET_KEY)에 쓴다.
- `.get()`: 없으면 기본값. **없어도 되는 값**(DEBUG → 꺼짐)에 쓴다.

### 환경변수는 항상 문자열
- `.env`에 `DJANGO_DEBUG=False`라고 써도 파이썬에는 문자열 `"False"`로 들어온다.
- `bool("False")`는 `True`다 (빈 문자열만 `False`). 그래서 `== "True"`로 비교한다.

### compose의 `${이름}`: 빈칸 채우기
- compose는 실행할 때 `docker-compose.yml`과 **같은 폴더에서 이름이 정확히 `.env`인 파일**을 자동으로 연다. compose 프로그램에 정해진 규칙이다.
- `KEY=값` 줄로 표를 만들고, YAML의 `${이름}`과 **글자가 똑같은** 항목을 찾아 바꿔 끼운다. 터미널에서 `export`한 값이 있으면 그 값이 우선한다.
- 이름에 오타가 있으면 `variable is not set` 경고와 함께 **빈 문자열**이 들어간다.
- `docker compose config`로 빈칸이 채워진 최종 결과를 볼 수 있다.

### `env_file` vs `${...}`: 서랍째 주기 vs 골라서 주기
- `env_file`: `.env` 전체를 컨테이너에 넣는다 → 값이 다 필요한 Django
- `${...}`: 지정한 값만 넣는다 → 3개만 필요한 PostgreSQL
- 필요한 것만 준다 = **최소 권한 원칙**. 비밀값이 들어가는 곳이 적을수록 샐 경로도 줄어든다.

### SECRET_KEY를 바꾸면 로그인이 풀린다
- 로그인 세션은 SECRET_KEY로 서명된다. 키가 바뀌면 예전 서명을 믿을 수 없게 되어 모두 로그아웃된다.
- 그래서 "다시 로그인해야 했다"는 것은 키 교체가 실제로 적용됐다는 증거다.

### git 기록에 남은 비밀값은 "교체"해야 한다
- 코드에서 지워도 예전 커밋에는 그대로 남아 있다. 그러니 지우는 것으로 끝내지 말고 **새 키를 만들어 바꿔야** 예전 키가 쓸모없어진다.
- `cv_service/.env`(Gemini 키)는 처음부터 git에 올라간 적이 없어서 교체할 필요가 없다.

### PostgreSQL 비밀번호는 "처음 한 번만" 적용
- `POSTGRES_PASSWORD`는 볼륨이 비어 있을 때만 읽는다. 기존 볼륨이 있는데 `.env`의 값만 바꾸면 DB는 옛 비밀번호를 기억하고 있어서 접속에 실패한다.
- 그래서 이번에는 값을 바꾸지 않고 **위치만 옮겼다**. 강한 비밀번호는 배포 때 새 볼륨에 넣는다.

---

## 5. 트러블슈팅

### 파일 이름 오타: `.env.exmple`
- **증상**: 견본 파일 이름이 `.env.exmple`(`a` 빠짐)로 만들어졌다.
- **해결**: `mv .env.exmple .env.example`로 이름을 바꿨다. README와 문서가 안내하는 `cp .env.example .env`가 동작하려면 이름이 정확해야 한다.

### 시크릿 키에 특수문자가 섞여 있음
- **증상**: `get_random_secret_key()`로 만든 키가 `(`로 시작했고, `$`·`#` 같은 문자가 섞일 수 있다.
- **원인**: compose는 `$이름`을 변수로, 공백 뒤의 `#`을 주석으로 해석한다. 그대로 붙여 넣으면 키의 일부가 사라질 수 있다.
- **해결**: 키를 작은따옴표 `'...'`로 감싸서 글자 그대로 쓰게 했다. Django가 만드는 키에는 `'` 문자가 없어서 안전하다.

### 루트 `.dockerignore`에 `.env`가 없었음
- **발견**: 문서를 정리하며 `Dockerfile`의 `COPY . .`와 `.dockerignore`를 대조하다 발견했다. `cv_service/.dockerignore`에는 `.env`가 있었지만 루트에는 없었다.
- **위험**: 루트 `.env`(SECRET_KEY)가 web 이미지 안에 파일로 복사된다. 이미지를 레지스트리에 올리면 키도 같이 올라간다.
- **해결**: 루트 `.dockerignore`에 `.env`를 추가하고 `docker compose build`로 다시 빌드했다.

### 남은 과제 (이번 브랜치에서는 하지 않음)
- `DEBUG=False` 전환: whitenoise/nginx로 static·media 제공, `ALLOWED_HOSTS`에 실제 도메인 추가 (보안 점검 10번)
- 배포 때 PostgreSQL 강한 비밀번호 + 새 볼륨, 관리자 계정 대신 권한을 줄인 DB 사용자
- healthcheck의 `-U postgres -d mom_vision`도 `.env` 값과 연결할지 검토
- 다음 브랜치 B: 콜백 토큰 필수화, cv_service 콜백의 timeout·`allow_redirects=False`, 업로드 이미지 검증, `feed.js`의 `innerHTML` → `textContent`
