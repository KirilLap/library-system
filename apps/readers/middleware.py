from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """Читатель, которого зарегистрировал сотрудник, не может пользоваться
    сайтом, пока не сменит временный пароль."""

    ALLOWED_PREFIXES = ('/my/password/', '/logout/', '/i18n/', '/set-language/', '/static/', '/media/')

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated and not request.path.startswith(self.ALLOWED_PREFIXES):
            try:
                must_change = user.reader_profile.must_change_password
            except Exception:
                must_change = False
            if must_change:
                return redirect(reverse('main:change_password'))
        return self.get_response(request)


class LoanPeriodMemoMiddleware:
    """На время запроса запоминает срок возврата, чтобы не спрашивать базу для каждой книги в списке."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from .models import _loan_memo
        _loan_memo.active = True
        if hasattr(_loan_memo, 'value'):
            del _loan_memo.value
        try:
            return self.get_response(request)
        finally:
            _loan_memo.active = False
            if hasattr(_loan_memo, 'value'):
                del _loan_memo.value
