from django.urls import path
from backend import views

urlpatterns = [path('health/', views.health), path('api/<path:route>', views.api), path('media/<path:route>', views.media)]
