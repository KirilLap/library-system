from django.urls import path
from . import views

app_name = 'readers_admin'

urlpatterns = [
    path('', views.reader_list, name='index'),
    path('add/', views.reader_create, name='create'),
    path('loan-settings/', views.loan_settings, name='loan_settings'),
    path('stats/', views.reader_stats, name='stats'),
    path('stats/settings/', views.reader_stats_settings, name='stats_settings'),
    path('stats/readers/', views.reader_stats_readers, name='stats_readers'),
    path('stats/unreturned/', views.reader_stats_unreturned, name='stats_unreturned'),
    path('stats/export/', views.reader_stats_export, name='stats_export'),
    path('loans/<int:pk>/return/', views.loan_return_staff, name='loan_return'),
    path('loans/<int:pk>/lost/', views.loan_lost_staff, name='loan_lost'),
    path('<int:pk>/', views.reader_detail, name='detail'),
    path('<int:pk>/block/', views.reader_toggle_block, name='toggle_block'),
    path('<int:pk>/delete/', views.reader_delete, name='delete'),
]
