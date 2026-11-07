from shared.settings import *
ROOT_URLCONF = 'backend.urls'
# GPU API 是服务间协议，通过实例认证及控制租约保护；浏览器 HTTP CSRF 在 Web 网关检查。
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware']
