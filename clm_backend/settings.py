from pathlib import Path
from datetime import timedelta
import os
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from this project reliably (do not depend on CWD).
load_dotenv(dotenv_path=BASE_DIR / '.env', override=False)

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-dev-key-12345')

DEBUG = os.getenv('DEBUG', 'False').strip().lower() in ('1', 'true', 'yes', 'y', 'on')

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'authentication',
    'contracts',
    'workflows',
    'notifications',
    'audit_logs',
    'search',
    'repository',
    'metadata',
    'ocr',
    'redaction',
    'ai',
    'rules',
    'approvals',
    'tenants',
    'calendar_events',
    'reviews',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'clm_backend.middleware.TenantIsolationMiddleware',
    'clm_backend.middleware.AuditLoggingMiddleware',
    'clm_backend.middleware.PIIProtectionLoggingMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'clm_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'clm_backend.wsgi.application'

# Database configuration (Supabase/PostgreSQL only)
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
DB_ENGINE = os.getenv('DB_ENGINE', 'django.db.backends.postgresql')
DB_HOST = os.getenv('DB_HOST', '')
DB_PORT = os.getenv('DB_PORT', '5432')


def _parse_database_url(database_url: str) -> dict:
    """Parse a Postgres DATABASE_URL into Django DATABASES['default'] keys."""
    parsed = urlparse(database_url)
    scheme = (parsed.scheme or '').lower()
    if scheme not in ('postgres', 'postgresql'):
        raise ValueError('DATABASE_URL must start with postgresql://')

    name = (parsed.path or '').lstrip('/')
    if not name:
        name = 'postgres'

    user = unquote(parsed.username or '')
    password = unquote(parsed.password or '')
    host = parsed.hostname or ''
    port = str(parsed.port or 5432)

    qs = parse_qs(parsed.query or '')
    sslmode = (qs.get('sslmode', [None])[0] or os.getenv('DB_SSLMODE', 'require'))

    # Keep compatibility with Supabase pooler constraints.
    using_pooler = 'pooler.supabase.com' in (host or '')

    # Supabase pooler requires the user in the form `postgres.<project_ref>`.
    # If a DATABASE_URL is accidentally set to `postgres@...pooler.supabase.com`,
    # authentication will fail (and can trigger the pooler circuit-breaker).
    if using_pooler and (not user or '.' not in user):
        env_user = (os.getenv('DB_USER', '') or '').strip()
        env_password = (os.getenv('DB_PASSWORD', '') or '').strip()
        if env_user and '.' in env_user:
            user = env_user
            if not password and env_password:
                password = env_password
    default_conn_max_age = 0 if using_pooler else 60
    conn_max_age = int(os.getenv('DB_CONN_MAX_AGE', str(default_conn_max_age)))

    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': name,
        'USER': user,
        'PASSWORD': password,
        'HOST': host,
        'PORT': port,
        'CONN_MAX_AGE': conn_max_age,
        'CONN_HEALTH_CHECKS': True,
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            'sslmode': sslmode,
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '20')),
            'keepalives': 1,
            'keepalives_idle': int(os.getenv('DB_KEEPALIVES_IDLE', '30')),
            'keepalives_interval': int(os.getenv('DB_KEEPALIVES_INTERVAL', '10')),
            'keepalives_count': int(os.getenv('DB_KEEPALIVES_COUNT', '5')),
            'options': os.getenv(
                'DB_PG_OPTIONS',
                '-c statement_timeout=120000 -c idle_in_transaction_session_timeout=120000',
            ),
        },
        'TEST': {
            'NAME': os.getenv('DB_TEST_NAME', 'test_postgres'),
            'MIGRATE': os.getenv('DB_TEST_MIGRATE', 'false').strip().lower() in ('1', 'true', 'yes', 'y', 'on'),
        },
    }

# Supabase pooler notes:
# - If you use the Supabase pooler host (contains "pooler.supabase.com"), you MUST avoid long-lived connections.
#   Session mode poolers have a small pool_size; persistent Django connections can exhaust it quickly.
# - If possible, prefer Supabase pooler in TRANSACTION mode (often port 6543 in Supabase UI), and keep CONN_MAX_AGE=0.
USING_SUPABASE_POOLER = 'pooler.supabase.com' in (DB_HOST or '')
DEFAULT_CONN_MAX_AGE = 0 if USING_SUPABASE_POOLER else 60

DATABASES = {
    'default': {
        'ENGINE': DB_ENGINE,
        'NAME': os.getenv('DB_NAME', 'postgres'),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': DB_HOST,
        'PORT': DB_PORT,
        # For Supabase pooler: keep this at 0 to avoid "max clients reached".
        'CONN_MAX_AGE': int(os.getenv('DB_CONN_MAX_AGE', str(DEFAULT_CONN_MAX_AGE))),
        # Recommended for pgbouncer/poolers.
        'CONN_HEALTH_CHECKS': True,
        'DISABLE_SERVER_SIDE_CURSORS': True,
        'OPTIONS': {
            'sslmode': os.getenv('DB_SSLMODE', 'require'),
            # psycopg2/libpq connect timeout (seconds)
            'connect_timeout': int(os.getenv('DB_CONNECT_TIMEOUT', '20')),
            # libpq keepalives
            'keepalives': 1,
            'keepalives_idle': int(os.getenv('DB_KEEPALIVES_IDLE', '30')),
            'keepalives_interval': int(os.getenv('DB_KEEPALIVES_INTERVAL', '10')),
            'keepalives_count': int(os.getenv('DB_KEEPALIVES_COUNT', '5')),
            # Server-side timeouts (ms)
            'options': os.getenv('DB_PG_OPTIONS', '-c statement_timeout=120000 -c idle_in_transaction_session_timeout=120000'),
        },
        'TEST': {
            # Use a stable Supabase test DB name; run tests with --keepdb.
            'NAME': os.getenv('DB_TEST_NAME', 'test_postgres'),
            # Skip migrations to reduce long-running operations against Supabase.
            'MIGRATE': os.getenv('DB_TEST_MIGRATE', 'false').strip().lower() in ('1', 'true', 'yes', 'y', 'on'),
        },
    }
}

# If a single DATABASE_URL is provided, it takes precedence.
if DATABASE_URL:
    DATABASES['default'] = _parse_database_url(DATABASE_URL)

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

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'authentication.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50,
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=24),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'user_id',
    'USER_ID_CLAIM': 'user_id',
}

# Cloudflare R2 settings (used by authentication.r2_service.R2StorageService)
R2_ACCOUNT_ID = os.getenv('R2_ACCOUNT_ID', '')
R2_ACCESS_KEY_ID = os.getenv('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = os.getenv('R2_SECRET_ACCESS_KEY', '')
R2_BUCKET_NAME = os.getenv('R2_BUCKET_NAME', '')
R2_ENDPOINT_URL = os.getenv('R2_ENDPOINT_URL', '')

if not R2_ENDPOINT_URL and R2_ACCOUNT_ID:
    R2_ENDPOINT_URL = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

R2_PUBLIC_URL = os.getenv('R2_PUBLIC_URL', '')

CORS_ALLOWED_ORIGINS = [
    # Local Development
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
    "http://localhost:4000",
    "http://127.0.0.1:4000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Production - Render
    "http://127.0.0.1:8000",
    # Allow all origins (for development/testing - restrict in production)
    "http://localhost",
    "http://127.0.0.1",
]

# Alternative: Allow all origins (use with caution in production)
# CORS_ALLOW_ALL_ORIGINS = True

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_METHODS = ['DELETE', 'GET', 'OPTIONS', 'PATCH', 'POST', 'PUT']
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-api-key',
]

# AI/ML API Keys
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
VOYAGE_API_KEY = os.getenv('VOYAGE_API_KEY', '')
VOYAGE_CONTEXT = os.getenv('VOYAGE_CONTEXT', '')  # Fallback for compatibility

# Email Configuration - Google SMTP with App Password
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('GMAIL', 'suhaib96886@gmail.com')
EMAIL_HOST_PASSWORD = os.getenv('APP_PASSWORD', 'ruuo ntzn djvu hddg')
DEFAULT_FROM_EMAIL = os.getenv('GMAIL', 'suhaib96886@gmail.com')
SERVER_EMAIL = os.getenv('GMAIL', 'suhaib96886@gmail.com')

# Celery Configuration
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes max
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes soft limit
