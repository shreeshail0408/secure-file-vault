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


# --- Core -------------------------------------------------------------------

SECRET_KEY = require_env("SECRET_KEY")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


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

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
    )
}


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
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# --- CORS -------------------------------------------------------------------
# Only the React dev server / deployed frontend may call the API from a browser.

CORS_ALLOWED_ORIGINS = [os.environ.get("FRONTEND_URL", "http://localhost:5173")]
# Let the frontend read the filename on downloads.
CORS_EXPOSE_HEADERS = ["Content-Disposition"]


# --- I18N / static ----------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
