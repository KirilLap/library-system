from django.urls import path
from . import views

app_name = 'readers_admin'

urlpatterns = [
    path('', views.reader_list, name='index'),
    path('add/', views.reader_create, name='create'),
    path('loan-settings/', views.loan_settings, name='loan_settings'),
    path('reset-requests/', views.reset_requests, name='reset_requests'),
    path('reset-requests/<int:pk>/issue/', views.reset_issue, name='reset_issue'),
    path('reset-requests/<int:pk>/reject/', views.reset_reject, name='reset_reject'),
    path('<int:pk>/reset-password/', views.reader_reset_password, name='reader_reset_password'),
    path('<int:pk>/request-reset/', views.reader_request_reset, name='reader_request_reset'),
    path('<int:pk>/temp-password/', views.temp_password_show, name='temp_password'),
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
