from django.urls import path
from django.http import HttpResponse

app_name = 'readers_auth'

def placeholder(request):
    return HttpResponse('<h1>Регистрация — скоро</h1>')

urlpatterns = [
    path('', placeholder, name='register'),
]
