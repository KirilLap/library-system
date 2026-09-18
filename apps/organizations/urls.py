from django.urls import path
from . import views

app_name = 'organizations'

urlpatterns = [
    # Shared org account
    path('', views.org_dashboard, name='index'),
    path('login/', views.org_login, name='login'),
    path('logout/', views.org_logout, name='logout'),
    path('set-language/', views.set_language, name='set_language'),
    path('dashboard/', views.org_dashboard, name='dashboard'),

    # Worker cabinet (personal, login via /login/)
    path('worker/', views.worker_cabinet, name='worker_cabinet'),
    path('worker/issue/', views.worker_issue, name='worker_issue'),
    path('worker/return/', views.worker_return, name='worker_return'),
    path('worker/readers/', views.worker_readers, name='worker_readers'),
    path('worker/readers/register/', views.worker_register_reader, name='worker_register_reader'),

    # Admin: manage org accounts & workers (called from location detail)
    path('account/create/<int:location_pk>/', views.org_account_create, name='account_create'),
    path('account/delete/<int:location_pk>/', views.org_account_delete, name='account_delete'),
    path('worker/add/<int:location_pk>/', views.worker_add, name='worker_add'),
    path('worker/toggle/<int:worker_pk>/', views.worker_toggle, name='worker_toggle'),
]
