from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('admin-panel/', include('apps.catalog.urls_admin', namespace='catalog_admin')),
    path('admin-panel/locations/', include('apps.locations.urls_admin', namespace='locations_admin')),
    path('admin-panel/deliveries/', include('apps.deliveries.urls_admin', namespace='deliveries_admin')),
    path('admin-panel/readers/', include('apps.readers.urls_admin', namespace='readers_admin')),
    path('admin-panel/', include('apps.readers.urls_admin_extra', namespace='readers_admin_extra')),
    path('catalog/', include('apps.public.urls_catalog', namespace='catalog')),
    path('p/', include('apps.locations.urls_public', namespace='locations_public')),
    path('', include('apps.public.urls_main', namespace='main')),
    path('register/', include('apps.readers.urls_auth', namespace='readers_auth')),
    path('org/', include('apps.organizations.urls', namespace='organizations')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
