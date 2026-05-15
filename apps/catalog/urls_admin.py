from django.urls import path
from django.http import HttpResponse

app_name = 'catalog_admin'

def placeholder(request):
    return HttpResponse('<h1>Кабинет библиотекаря — скоро здесь появится каталог</h1>')

urlpatterns = [
    path('', placeholder, name='index'),
]
