from django.urls import path
from django.http import HttpResponse

app_name = 'organizations'

def placeholder(request):
    return HttpResponse('<h1>Кабинет организации — скоро (Фаза 6)</h1>')

urlpatterns = [
    path('', placeholder, name='index'),
]
