import uuid
from pathlib import Path
from django.db import models
from django.contrib.auth.models import AbstractUser

def profile_image_path(instance, filename):
    """프로필 사진도 무작위 이름으로 저장"""
    return f"profiles/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"



class User(AbstractUser):
    profile_image = models.ImageField(upload_to=profile_image_path, blank=True, null=True)
