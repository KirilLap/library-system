from django.urls import path
from . import views

app_name = 'deliveries_admin'

urlpatterns = [
    path('', views.batch_list, name='index'),
    path('create/', views.batch_create, name='create'),
    path('<int:pk>/', views.batch_detail, name='detail'),
    path('<int:pk>/remove/<int:item_pk>/', views.batch_remove_item, name='remove_item'),
    path('<int:pk>/return/', views.batch_return, name='return'),
    path('<int:pk>/pdf/', views.batch_pdf, name='pdf'),
]
