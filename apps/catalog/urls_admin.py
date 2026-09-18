from django.urls import path
from . import views

app_name = 'catalog_admin'

urlpatterns = [
    path('catalog/', views.book_list, name='index'),
    path('catalog/add/', views.book_create, name='book_create'),
    path('catalog/<int:pk>/edit/', views.book_update, name='book_update'),
    path('catalog/<int:pk>/delete/', views.book_delete, name='book_delete'),
    path('catalog/bulk-delete/', views.book_bulk_delete, name='book_bulk_delete'),
    path('catalog/import/', views.marc_import, name='marc_import'),
    path('catalog/import/confirm/', views.marc_confirm, name='marc_confirm'),
    path('catalog/<int:pk>/label/', views.book_label, name='book_label'),
    path('catalog/labels/', views.book_labels_batch, name='book_labels_batch'),
    path('catalog/import/excel/', views.excel_import, name='excel_import'),
    path('catalog/import/excel/confirm/', views.excel_confirm, name='excel_confirm'),
    path('catalog/import/excel/template/', views.excel_template_download, name='excel_template'),
    path('catalog/genres/', views.genre_list, name='genre_list'),
    path('catalog/genres/<int:pk>/delete/', views.genre_delete, name='genre_delete'),
    path('catalog/languages/', views.language_list, name='language_list'),
    path('catalog/languages/<int:pk>/delete/', views.language_delete, name='language_delete'),
]
