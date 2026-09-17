from django.urls import path

from . import views

app_name = 'staff'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('init/', views.init_view, name='init'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('staff/', views.staff_list, name='list'),
    path('staff/create/', views.staff_create, name='create'),
    path('staff/<int:pk>/edit/', views.staff_edit, name='edit'),
    path('staff/<int:pk>/toggle/', views.staff_toggle_active, name='toggle'),
]
