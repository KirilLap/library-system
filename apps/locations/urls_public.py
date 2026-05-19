from django.urls import path
from . import views

app_name = 'locations_public'

urlpatterns = [
    path('map/', views.points_map, name='map'),
    path('<slug:slug>/', views.point_public, name='point'),
]
