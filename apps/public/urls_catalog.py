from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    path('', views.book_list, name='index'),
    path('<int:pk>/', views.book_detail, name='detail'),
    path('<int:pk>/request/', views.book_request, name='request'),
    path('request/free/', views.free_book_request, name='free_request'),
    path('<int:pk>/queue/join/', views.book_queue_join, name='queue_join'),
    path('<int:pk>/queue/leave/', views.book_queue_leave, name='queue_leave'),
]
