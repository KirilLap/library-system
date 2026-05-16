from django.urls import path
from . import views

app_name = 'locations_admin'

urlpatterns = [
    path('', views.location_list, name='index'),
    path('add/', views.location_create, name='create'),
    path('<int:pk>/', views.location_detail, name='detail'),
    path('<int:pk>/edit/', views.location_update, name='update'),
    path('<int:pk>/qr/', views.location_qr_download, name='qr_download'),
]
