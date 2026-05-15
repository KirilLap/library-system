from django.urls import path
from django.http import HttpResponse

app_name = 'readers_admin_extra'

def placeholder(request):
    return HttpResponse('<h1>Заявки — скоро</h1>')

urlpatterns = [
    path('requests/', placeholder, name='requests'),
]
