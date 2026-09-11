from __future__ import annotations


SECRET_KEY = "not-a-secret"
DEBUG = True
ALLOWED_HOSTS = ["localhost", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
]

MIDDLEWARE = [
    "stash.middleware.StashMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "testapp.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

USE_TZ = True
