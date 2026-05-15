from django.conf import settings


def library_settings(request):
    return {
        'LIBRARY_NAME': settings.LIBRARY_NAME,
        'LIBRARY_PHONE': settings.LIBRARY_PHONE,
    }
