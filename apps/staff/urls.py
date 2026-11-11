from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('stats/', views.stats_view, name='stats'),
    path('stats/export/', views.stats_export, name='stats_export'),
    path('stats/points/', views.stats_points, name='stats_points'),
    path('stats/points/export/', views.stats_points_export, name='stats_points_export'),
    path('log/', views.action_log_view, name='action_log'),
    path('init/', views.init_view, name='init'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('set-language/', views.set_language, name='set_language'),
    path('staff/', views.staff_list, name='list'),
    path('staff/create/', views.staff_create, name='create'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='edit'),
    path('staff/<int:pk>/toggle/', views.staff_toggle_active, name='toggle'),
    path('staff/<int:pk>/delete/', views.staff_delete, name='delete'),
]
