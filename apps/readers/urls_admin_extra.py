from django.urls import path
from . import views

app_name = 'readers_admin_extra'

urlpatterns = [
    path('requests/', views.request_list, name='requests'),
    path('requests/<int:pk>/', views.request_detail, name='request_detail'),
]
