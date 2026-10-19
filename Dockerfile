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
