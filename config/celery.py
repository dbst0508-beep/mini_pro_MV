import os                                                    # 환경변수(DJANGO_SETTINGS_MODULE) 설정용
from celery import Celery                                     # Celery 앱 클래스

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")  # celery worker가 Django settings를 찾을 수 있게 지정

app = Celery("config")                                          # "config"라는 이름으로 Celery 앱 생성
app.config_from_object("django.conf:settings", namespace="CELERY")  # settings.py에서 CELERY_로 시작하는 값들만 가져와 설정
app.autodiscover_tasks()                                         # 설치된 각 앱(analysis 등)의 tasks.py를 자동으로 찾아 등록