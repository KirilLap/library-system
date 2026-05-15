from django.urls import path
from django.http import HttpResponse

app_name = 'readers_admin'

def placeholder(request):
    return HttpResponse('<h1>Читатели — скоро</h1>')

urlpatterns = [
    path('readers/', placeholder, name='index'),
]
