from django.urls import path
from web import views

urlpatterns = [path('', views.home), path('health/', views.health), path('api/<path:route>', views.proxy), path('media/<path:route>', views.media)]
