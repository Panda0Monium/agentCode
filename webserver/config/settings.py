import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-agentcode-dev-key-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'true').lower() != 'false'

ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',')

SITE_THEME = os.environ.get('DJANGO_THEME', 'light')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # third-party
    'rest_framework',
    'corsheaders',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.github',
    'huggingface_provider',
    'django_q',
    # local
    'users',
    'problems',
    'runs',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
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
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.theme',
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

AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

# allauth
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

SOCIALACCOUNT_STORE_TOKENS = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

SOCIALACCOUNT_PROVIDERS = {
    'huggingface': {
        'APP': {
            'client_id': os.environ.get('HF_CLIENT_ID', ''),
            'secret':    os.environ.get('HF_CLIENT_SECRET', ''),
        },
        'SCOPE': ['openid', 'profile', 'email', 'inference-api'],
    },
    'github': {
        'APP': {
            'client_id': os.environ.get('GITHUB_CLIENT_ID', ''),
            'secret':    os.environ.get('GITHUB_CLIENT_SECRET', ''),
        },
        'SCOPE': ['read:user', 'user:email'],
    },
}

# Ceiling on the per-run token budget a user may request. Multi-round
# architectures (reflexion, critic-actor) can spend several times what a single
# ReAct pass does, and runs are billed against user-supplied API keys.
AGENTCODE_MAX_TOKEN_BUDGET = int(os.environ.get('AGENTCODE_MAX_TOKEN_BUDGET', 400_000))

# Django Q — uses SQLite as broker, no Redis needed
Q_CLUSTER = {
    'name': 'AgentCode',
    'workers': 2,
    # Multi-round architectures (reflexion, tdd, critic_actor) scale the task
    # timeout by their time_multiplier, so an episode can legitimately run well
    # past the old 600s. If this is too low the cluster kills and re-queues a
    # run mid-episode.
    'timeout': 1800,
    'retry': 1900,  # must be > timeout to avoid re-triggering mid-run tasks
    'orm': 'default',
}

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CORS_ALLOWED_ORIGINS = ['http://localhost:5173']

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'DJANGO_CSRF_TRUSTED_ORIGINS',
    'https://agentcode.duckdns.org'
).split(',')

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'runs_file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'runs.log',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'runs': {
            'handlers': ['runs_file'],
            'level': 'ERROR',
            'propagate': False,
        },
    },
}


