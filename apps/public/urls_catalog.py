from django.urls import path
from django.http import HttpResponse

app_name = 'catalog'

def placeholder(request):
    return HttpResponse('<h1>Публичный каталог — скоро</h1>')

urlpatterns = [
    path('', placeholder, name='index'),
]
