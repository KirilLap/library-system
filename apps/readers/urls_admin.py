from django.urls import path
from . import views

app_name = 'readers_admin'

urlpatterns = [
    path('', views.reader_list, name='index'),
    path('<int:pk>/', views.reader_detail, name='detail'),
    path('<int:pk>/block/', views.reader_toggle_block, name='toggle_block'),
    path('<int:pk>/delete/', views.reader_delete, name='delete'),
]
