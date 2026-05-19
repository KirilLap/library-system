from functools import wraps

from django.shortcuts import redirect

STAFF_LOGIN_URL = '/admin-panel/login/'
STAFF_INIT_URL = '/admin-panel/init/'


def _get_staff_profile(user):
    try:
        return user.staff_profile
    except Exception:
        return None


def staff_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        from .models import StaffProfile
        if not StaffProfile.objects.filter(role=StaffProfile.ROLE_ADMIN).exists():
            return redirect(STAFF_INIT_URL)
        if not request.user.is_authenticated:
            return redirect(f'{STAFF_LOGIN_URL}?next={request.path}')
        profile = _get_staff_profile(request.user)
        if profile is None or not profile.is_active:
            return redirect(STAFF_LOGIN_URL)
        return func(request, *args, **kwargs)
    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        from .models import StaffProfile
        if not StaffProfile.objects.filter(role=StaffProfile.ROLE_ADMIN).exists():
            return redirect(STAFF_INIT_URL)
        if not request.user.is_authenticated:
            return redirect(f'{STAFF_LOGIN_URL}?next={request.path}')
        profile = _get_staff_profile(request.user)
        if profile is None or not profile.is_active:
            return redirect(STAFF_LOGIN_URL)
        if not profile.is_admin:
            return redirect('/admin-panel/')
        return func(request, *args, **kwargs)
    return wrapper


# Алиас для обратной совместимости — используется во всех существующих views
librarian_required = staff_required
