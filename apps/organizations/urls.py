from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    path('', views.org_dashboard, name='index'),
    path('login/', views.org_login, name='login'),
    path('logout/', views.org_logout, name='logout'),
    path('dashboard/', views.org_dashboard, name='dashboard'),
    # Admin: manage org accounts (called from location detail)
    path('account/create/<int:location_pk>/', views.org_account_create, name='account_create'),
    path('account/delete/<int:location_pk>/', views.org_account_delete, name='account_delete'),
]
