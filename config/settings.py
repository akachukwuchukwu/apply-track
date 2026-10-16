"""
Django settings for the Apply Track API.

Everything that differs between a laptop and a public server is read from
environment variables (or a local .env file), so the same code runs in both.
The defaults are tuned for local development; production is switched on by
setting DJANGO_DEBUG=False and supplying a real DJANGO_SECRET_KEY — and the
app refuses to start in that mode if the key is missing, rather than quietly
running on a key that is published in the repository.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# ---------- Core / security ----------

# Obviously-fake key so a fresh clone runs with no setup. It is public (it's in
# this repo), so it must never be accepted outside development: JWTs are signed
# with SECRET_KEY, and anyone who knows it can forge a login token for any user.
DEV_SECRET_KEY = "django-insecure-dev-only-key-replace-in-production"

DEBUG = env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY") or DEV_SECRET_KEY

if not DEBUG:
    if SECRET_KEY == DEV_SECRET_KEY:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is False. "
            "Refusing to start on the publicly known development key."
        )
    if len(SECRET_KEY) < 32:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY is too short: use at least 32 random characters.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Needed for the admin login over HTTPS behind a reverse proxy, e.g.
# DJANGO_CSRF_TRUSTED_ORIGINS=https://applytrack.example.com
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# Only enable when gunicorn is reachable *solely* through a proxy that sets
# X-Forwarded-Proto itself (see deploy/). If the app were exposed directly, a
# client could send that header and make Django believe the request was HTTPS.
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Optional hardening for once HTTPS is confirmed working end to end. Both are off
# by default: Apache already redirects HTTP to HTTPS, and HSTS tells browsers to
# refuse plain HTTP for that many seconds, which is painful to undo if the domain
# or certificate setup changes. If you turn on the redirect, health checks must use
# HTTPS or send X-Forwarded-Proto: https, because plain HTTP will get a 301.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", False)
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "0"))

# Cookies are only marked Secure outside development, where HTTPS is assumed.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'rest_framework',
    'rest_framework_simplejwt',
    'django_filters',

    'tracker',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# In production, WhiteNoise serves the admin's CSS/JS straight from gunicorn, so
# no separate static-file configuration is needed in the web server. It is left
# out in development, where runserver already serves static files itself.
if not DEBUG:
    MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# ---------- Database ----------

# SQLite by default: zero setup, and plenty for a demo. DJANGO_DB_PATH moves the
# file outside the code directory (the server keeps it in /var/lib/applytrack so
# a code update can never overwrite it). The longer timeout stops two gunicorn
# workers from failing instantly when one holds the write lock. Moving to
# Postgres means changing this one setting; nothing else is SQLite-specific.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.getenv("DJANGO_DB_PATH", str(BASE_DIR / 'db.sqlite3')),
        'OPTIONS': {'timeout': 20},
    }
}

# File-based so every gunicorn worker shares the same rate-limit counters (the
# default per-process memory cache would give each worker its own allowance).
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.getenv("DJANGO_CACHE_DIR", str(BASE_DIR / '.django_cache')),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # Compressed but not manifest-hashed: a missing manifest would make every
    # admin page fail with a 500 if collectstatic were ever skipped.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------- Django REST Framework ----------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    'DEFAULT_FILTER_BACKENDS': (
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,

    # Brute-force protection on the login endpoint (see tracker/views.py).
    'DEFAULT_THROTTLE_RATES': {
        'login': os.getenv("DJANGO_LOGIN_THROTTLE", "10/minute"),
    },
    # How many reverse proxies sit in front of the app. This must be set
    # deliberately: DRF's default (None) trusts the client-supplied
    # X-Forwarded-For header, so anyone could dodge the rate limit by sending a
    # different fake address on every request. 0 means "use the real socket
    # address"; behind one trusted proxy (Apache) set DJANGO_NUM_PROXIES=1.
    'NUM_PROXIES': int(os.getenv("DJANGO_NUM_PROXIES", "0")),
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
