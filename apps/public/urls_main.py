from django.urls import path
from django.http import HttpResponse
from django.shortcuts import redirect

app_name = 'main'


def home(request):
    return redirect('/catalog/')


def login_placeholder(request):
    return HttpResponse('<h1>Вход — скоро</h1>')


def my_placeholder(request):
    return HttpResponse('<h1>Личный кабинет — скоро</h1>')


urlpatterns = [
    path('', home, name='home'),
    path('login/', login_placeholder, name='login'),
    path('my/', my_placeholder, name='my'),
]
