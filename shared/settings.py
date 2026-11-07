"""两角色通用 Django 基础；无数据库、auth/admin/session，不需要 migrate。"""
import os
from shared.config import ROOT

SECRET_KEY = os.environ.get('CAMPUS_SECRET_KEY', 'local-teaching-demo-change-before-network-exposure')
DEBUG = False
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', '[::1]', 'testserver']
INSTALLED_APPS = ['django.contrib.staticfiles']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.middleware.csrf.CsrfViewMiddleware']
DATABASES = {}
TIME_ZONE = 'Asia/Shanghai'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
STATIC_URL = '/static/'
STATICFILES_DIRS = [ROOT / 'static']
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [ROOT / 'templates'], 'APP_DIRS': False}]
DATA_UPLOAD_MAX_MEMORY_SIZE = 105 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
LOGGING = {'version': 1, 'disable_existing_loggers': False,
           'handlers': {'console': {'class': 'logging.StreamHandler'}},
           'loggers': {'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False}}}
