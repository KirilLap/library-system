from django.urls import path
from django.http import HttpResponse

app_name = 'locations_public'

def placeholder(request, slug):
    return HttpResponse(f'<h1>Точка: {slug}</h1>')

urlpatterns = [
    path('<slug:slug>/', placeholder, name='point'),
]
