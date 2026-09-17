from django.urls import path
from . import views

app_name = 'readers_admin_extra'

urlpatterns = [
    path('requests/', views.request_list, name='requests'),
    path('requests/<int:pk>/', views.request_detail, name='request_detail'),
    path('requests/<int:pk>/approve/', views.request_approve, name='request_approve'),
    path('requests/<int:pk>/reject/', views.request_reject, name='request_reject'),
    path('requests/<int:pk>/purchasing/', views.request_purchasing, name='request_purchasing'),
    path('requests/<int:pk>/fulfill/', views.request_fulfill, name='request_fulfill'),
    path('requests/<int:pk>/fulfill-book/', views.request_fulfill_with_book, name='request_fulfill_with_book'),
]
