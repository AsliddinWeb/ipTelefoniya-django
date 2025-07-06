# core/settings/prod.py
from .base import *
import os

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

# Environment variables dan olinadi
SECRET_KEY = os.getenv('SECRET_KEY', SECRET_KEY)

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# Database - PostgreSQL for production with psycopg2-binary
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'loyiha_db'),
        'USER': os.getenv('DB_USER', 'loyiha_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
        'OPTIONS': {
            'connect_timeout': 60,
            'keepalives_idle': 600,
            'keepalives_interval': 30,
            'keepalives_count': 3,
        },
        'CONN_MAX_AGE': 600,  # Connection pooling
    }
}

# Static files for production
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files for production
MEDIA_ROOT = BASE_DIR / 'media'

# Production logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.getenv('LOG_FILE', BASE_DIR / 'logs' / 'production.log'),
            'maxBytes': 1024 * 1024 * 15,  # 15MB
            'backupCount': 10,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'WARNING',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['file', 'console', 'mail_admins'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file', 'mail_admins'],
            'level': 'ERROR',
            'propagate': False,
        },
        'apps': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Performance settings
# DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
# FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
# DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# Development muhitida HTTPS redirect ni o'chirish
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Agar base.py da yoki boshqa joyda HTTPS sozlamalari bo'lsa, ularni override qilish:
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

print("🚀 Production mode is ON")
