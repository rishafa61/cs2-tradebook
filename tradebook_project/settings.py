import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent



SECRET_KEY = 'django-insecure-bc9zh(pqooa8c^@yl-2&(8_)yty1rnnv(a07$#_v!%(%j_%5+b'


DEBUG = os.environ.get('DEBUG', '') == '1'

ALLOWED_HOSTS = ['.vercel.app', '127.0.0.1', 'localhost']


INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = 'tradebook_project.urls'

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

WSGI_APPLICATION = 'tradebook_project.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

IS_VERCEL = os.environ.get('VERCEL') == '1'

# Vercel's serverless functions run on a read-only filesystem (except /tmp,
# which is wiped between invocations), so SQLite can't be used there — any
# data written would vanish as soon as the function's container recycled.
# DATABASE_URL must point at a real hosted database (e.g. Vercel Postgres,
# Neon, Supabase) whenever this runs on Vercel. Locally, with no
# DATABASE_URL set, it falls back to a SQLite file for convenience.
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
elif IS_VERCEL:
    # Fail loudly instead of silently falling back to a database that will
    # lose all data on the next cold start.
    raise ImproperlyConfigured(
        'DATABASE_URL is not set. On Vercel, a persistent database '
        '(e.g. Vercel Postgres or Neon) is required — SQLite cannot be '
        'used because the filesystem is read-only/ephemeral. Add '
        'DATABASE_URL to your Vercel project environment variables.'
    )
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = '/static/'
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
