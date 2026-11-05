from django.urls import path
from . import views

app_name = 'locations_admin'

urlpatterns = [
    path('', views.location_list, name='index'),
    path('add/', views.location_create, name='create'),
    path('<int:pk>/', views.location_detail, name='detail'),
    path('<int:pk>/edit/', views.location_update, name='update'),
    path('<int:pk>/delete/', views.location_delete, name='delete'),
    path('<int:pk>/qr/', views.location_qr_download, name='qr_download'),
    path('map-settings/', views.map_settings, name='map_settings'),
    path('types/', views.location_type_list, name='type_list'),
    path('types/<int:pk>/edit/', views.location_type_update, name='type_update'),
    path('types/<int:pk>/delete/', views.location_type_delete, name='type_delete'),
]
