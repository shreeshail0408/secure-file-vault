"""
Django settings for Secure File Vault.

Every secret and environment-specific value comes from backend/.env
(see .env.example). Nothing secret is hardcoded here.
"""

import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from cryptography.fernet import Fernet
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load variables from backend/.env into os.environ.
# Real environment variables win over the file (override=False).
load_dotenv(BASE_DIR / ".env")


def require_env(name):
    """Return an environment variable or stop startup with a clear message."""
    value = os.environ.get(name)
    if not value:
        raise ImproperlyConfigured(
            f"{name} is not set. Copy .env.example to .env and fill it in."
        )
    return value


def env_list(name, default=""):
    """Comma-separated env variable -> list, ignoring blanks ("a, b," -> ["a", "b"])."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


def env_bool(name, default):
    return os.environ.get(name, str(default)).lower() == "true"


# --- Core -------------------------------------------------------------------

SECRET_KEY = require_env("SECRET_KEY")
DEBUG = env_bool("DEBUG", False)  # off unless .env says DEBUG=True
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# Origins allowed to POST forms with a CSRF cookie (the Django admin login over HTTPS),
# e.g. "https://yourname.pythonanywhere.com".
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")


# --- HTTPS / security headers (production) ----------------------------------
# All on by default when DEBUG is off; `python manage.py check --deploy` is clean.
# Locally (DEBUG=True) they are off, because runserver only speaks plain HTTP.

# PythonAnywhere's front-end proxy talks HTTPS to the browser and plain HTTP to
# Django, and tells us the original scheme in X-Forwarded-Proto. Without this,
# Django would think every request is HTTP and redirect forever.
# Only safe behind a proxy that always sets (or overwrites) this header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)  # http:// -> https://
SESSION_COOKIE_SECURE = not DEBUG  # admin session cookie only over HTTPS
CSRF_COOKIE_SECURE = not DEBUG
# HSTS: browsers remember "HTTPS only" for this many seconds. Start small (1 hour);
# raise it (e.g. 31536000 = 1 year) once HTTPS is known to work.
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0" if DEBUG else "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
# HSTS "preload" needs a domain you own and submitting it to hstspreload.org;
# not possible for a *.pythonanywhere.com subdomain, so that one check is silenced.
SILENCED_SYSTEM_CHECKS = ["security.W021"]
# Already Django's defaults, written out so the review can see them:
SECURE_CONTENT_TYPE_NOSNIFF = True  # X-Content-Type-Options: nosniff
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# --- Encryption key ---------------------------------------------------------
# Every stored file is encrypted with this key. If it is lost, the files
# cannot be recovered, so we refuse to start with a missing or invalid key.

FERNET_KEY = require_env("FERNET_KEY")
try:
    Fernet(FERNET_KEY)
except ValueError:
    raise ImproperlyConfigured(
        "FERNET_KEY is invalid. It must be 32 url-safe base64-encoded bytes. "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; "
        "print(Fernet.generate_key().decode())\""
    )

# Encrypted files (*.enc) live here. Not served as static/media on purpose:
# the only way to reach a file is through an authenticated API view.
STORAGE_DIR = BASE_DIR / "storage"

# Largest upload we accept (bytes).
MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB

# Keep uploads in memory only. Django's default would also use
# TemporaryFileUploadHandler, which writes files over 2.5 MB to a temp file on
# disk while parsing the request, which would put plaintext on disk.
FILE_UPLOAD_HANDLERS = ["django.core.files.uploadhandler.MemoryFileUploadHandler"]
# The in-memory handler only accepts request bodies up to this size; bigger
# bodies are rejected in files.validation before Django parses them.
# +1 MB leaves room for the multipart form overhead around the file.
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE + 1024 * 1024


# --- Apps -------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    # Our apps
    "accounts",
    "files",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves the collected static files (React build + admin CSS) from Django itself.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # must come before CommonMiddleware
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database ---------------------------------------------------------------
# DATABASE_URL examples:
#   sqlite:///db.sqlite3
#   postgres://user:pass@host:5432/dbname
#   mysql://user:pass@host:3306/dbname
# Falls back to a local SQLite file if not set.

def resolve_sqlite_path(db_config, base_dir):
    """Make a relative SQLite path relative to backend/, not the current folder.

    dj_database_url turns "sqlite:///db.sqlite3" into NAME="db.sqlite3", which
    SQLite would open relative to wherever manage.py was started from, silently
    creating an empty database when run from another folder.
    """
    name = db_config.get("NAME", "")
    if db_config.get("ENGINE") == "django.db.backends.sqlite3" and name and name != ":memory:":
        if not Path(name).is_absolute():
            db_config["NAME"] = str(base_dir / name)
    return db_config


DATABASES = {
    "default": resolve_sqlite_path(
        dj_database_url.config(default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600),
        BASE_DIR,
    )
}

# Optional MySQL (e.g. PythonAnywhere's): needs `pip install mysqlclient`.
if DATABASES["default"]["ENGINE"] == "django.db.backends.mysql":
    DATABASES["default"].setdefault("OPTIONS", {}).update({
        "charset": "utf8mb4",  # full UTF-8, so any file name (even emoji) can be stored
        "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",  # error instead of silently cutting data
    })


# --- Auth -------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    # Every request is authenticated with a JWT "Authorization: Bearer <token>" header.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    # Locked down by default; public views (register/login) opt out explicitly.
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # How many proxies sit in front of Django; used to find the client IP for
    # throttling. 0 (local): ignore X-Forwarded-For, which a client can fake.
    # 1 (PythonAnywhere): use the last X-Forwarded-For entry, the one the proxy added.
    # (DRF's default, None, trusts the whole header, so faking it would bypass throttling.)
    "NUM_PROXIES": int(os.environ.get("NUM_PROXIES", "0")),
}

# Brute-force protection for login and register, per client IP.
# Read at request time by accounts.throttles.AuthRateThrottle, so tests can
# override it. Counts are kept in Django's cache (per-process LocMem by default;
# use a shared cache such as Redis when running several server processes).
AUTH_THROTTLE_RATES = {
    "login": "5/min",
    "register": "5/min",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# --- CORS -------------------------------------------------------------------
# Only the React dev server / deployed frontend may call the API from a browser.

# Comma-separated, e.g. "http://localhost:5173,http://127.0.0.1:5173".
# In production Django serves the React app itself (same origin), so CORS isn't used there.
CORS_ALLOWED_ORIGINS = env_list("FRONTEND_URL", "http://localhost:5173")
# Let the frontend read the filename on downloads.
CORS_EXPOSE_HEADERS = ["Content-Disposition"]


# --- I18N / static ----------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# The React build (`npm run build` -> frontend/dist) is served by Django:
#   dist/index.html  -> every non-API URL (config.views.frontend_app, for React Router)
#   dist/assets/*    -> collected into STATIC_ROOT and served under /static/
#                       (Vite builds with base "/static/", see frontend/vite.config.js)
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # `manage.py collectstatic` copies files here
# Only if it was built, so `manage.py` still works before the first `npm run build`.
STATICFILES_DIRS = [FRONTEND_DIST] if FRONTEND_DIST.exists() else []
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Adds pre-compressed .gz/.br copies. No hashed "manifest" names: Vite's
    # output names already contain a content hash.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}


def immutable_file_test(path, url):
    """Vite puts a content hash in every file name under assets/, so a file at a
    given URL never changes: browsers may cache it forever (WhiteNoise header)."""
    return url.startswith("/static/assets/")


WHITENOISE_IMMUTABLE_FILE_TEST = immutable_file_test
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
