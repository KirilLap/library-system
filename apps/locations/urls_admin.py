from django.urls import path
from django.http import HttpResponse

app_name = 'locations_admin'

def placeholder(request):
    return HttpResponse('<h1>Точки доставки — скоро</h1>')

urlpatterns = [
    path('', placeholder, name='index'),
]
