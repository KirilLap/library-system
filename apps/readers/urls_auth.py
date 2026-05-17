from django.urls import path
from . import views

app_name = 'readers_auth'

urlpatterns = [
    path('', views.register, name='register'),
]
