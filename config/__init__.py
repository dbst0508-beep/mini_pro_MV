from .celery import app as celery_app   # Django가 시작될 때 celery.py의 app을 미리 로드해서 등록

__all__ = ("celery_app",)                 # "from config import *" 했을 때 celery_app만 노출 (관례적인 표기)