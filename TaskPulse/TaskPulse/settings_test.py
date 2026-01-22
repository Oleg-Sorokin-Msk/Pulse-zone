from pathlib import Path

from .settings import *  # noqa: F401,F403

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CELERY_TASK_ALWAYS_EAGER = True

CELERY_TASK_EAGER_PROPAGATES = True

BASE_DIR = Path(__file__).resolve().parent.parent

MEDIA_ROOT = BASE_DIR / ".pytest_media"

DEBUG = True
MEDIA_URL = "/media/"

