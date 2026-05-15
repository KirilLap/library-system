from django.urls import path
from django.http import HttpResponse

app_name = 'deliveries_admin'

def placeholder(request):
    return HttpResponse('<h1>Партии — скоро</h1>')

urlpatterns = [
    path('', placeholder, name='index'),
]
