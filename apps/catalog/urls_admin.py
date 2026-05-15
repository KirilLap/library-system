from django.urls import path
from . import views

app_name = 'catalog_admin'

urlpatterns = [
    path('', views.book_list, name='index'),
    path('catalog/add/', views.book_create, name='book_create'),
    path('catalog/<int:pk>/edit/', views.book_update, name='book_update'),
    path('catalog/<int:pk>/delete/', views.book_delete, name='book_delete'),
    path('catalog/import/', views.marc_import, name='marc_import'),
    path('catalog/import/confirm/', views.marc_confirm, name='marc_confirm'),
]
