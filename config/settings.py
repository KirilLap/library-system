import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()


def env_bool(name, default=False):
    return os.getenv(name, str(default)).strip().lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [x.strip() for x in os.getenv(name, default).split(',') if x.strip()]

BASE_DIR = Path(__file__).resolve().parent.parent

_INSECURE_KEY = 'django-insecure-fallback-key-change-me'
SECRET_KEY = os.getenv('SECRET_KEY', _INSECURE_KEY)

# На сервере DEBUG должен быть выключен. На своём компьютере поставьте DEBUG=True в .env
DEBUG = env_bool('DEBUG', False)

if not DEBUG and SECRET_KEY == _INSECURE_KEY:
    raise ImproperlyConfigured('Задайте SECRET_KEY в файле .env (при DEBUG=False это обязательно).')

# Адреса, по которым открывается сайт (через запятую): домен и/или IP сервера.
ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', '127.0.0.1,localhost')

# Полные адреса с http:// или https:// (через запятую), нужны для форм входа за HTTPS.
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')

# Включайте USE_HTTPS=True только когда на сайте уже работает HTTPS.
USE_HTTPS = env_bool('USE_HTTPS', False)
if USE_HTTPS:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

LIBRARY_NAME = os.getenv('LIBRARY_NAME', 'Библиотека')
LIBRARY_PHONE = os.getenv('LIBRARY_PHONE', '')

# Сколько дней читатель может держать книгу, прежде чем она считается просроченной.
LOAN_PERIOD_DAYS = int(os.getenv('LOAN_PERIOD_DAYS', 30))

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.staff',
    'apps.catalog',
    'apps.locations',
    'apps.deliveries',
    'apps.readers',
    'apps.organizations',
    'apps.public',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.library_settings',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('uz', "O'zbekcha"),
]
LOCALE_PATHS = [BASE_DIR / 'locale']
TIME_ZONE = 'Asia/Tashkent'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Адрес сайта: по нему строятся QR-коды библиопунктов.
SITE_URL = os.getenv('SITE_URL', 'http://127.0.0.1:8000').rstrip('/')

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/my/'

# Django's SecurityMiddleware default ('same-origin') strips the Referer header
# on requests to OpenStreetMap tile servers, which then reject them as
# policy-violating ("App is not following the tile usage policy"). Send only
# the origin cross-site — enough to identify the app to OSM, without leaking
# full page paths.
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# Ошибки сервера попадают в журнал: journalctl -u library
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
