"""Сброс пароля читателя через администратора."""
import secrets

from django.utils import timezone

# Без похожих символов (0/O, 1/l/I), чтобы временный пароль было легко продиктовать
ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789'
TEMP_PASSWORD_LENGTH = 10


def generate_temp_password():
    return ''.join(secrets.choice(ALPHABET) for _ in range(TEMP_PASSWORD_LENGTH))


def pending_count():
    from .models import PasswordResetRequest
    return PasswordResetRequest.objects.filter(status=PasswordResetRequest.STATUS_NEW).count()


def open_request(reader, source, requested_by=None):
    """Создаёт запрос на сброс, если для читателя нет ожидающего. Возвращает (запрос, создан_ли)."""
    from .models import PasswordResetRequest
    existing = PasswordResetRequest.objects.filter(reader=reader, status=PasswordResetRequest.STATUS_NEW).first()
    if existing:
        return existing, False
    return PasswordResetRequest.objects.create(reader=reader, source=source, requested_by=requested_by), True


def issue_temp_password(reader, admin_user):
    """Задаёт читателю временный пароль (читатель обязан сменить его при входе) и закрывает его запросы.
    Возвращает сам пароль: его показывают администратору один раз, в базе он хранится только в виде хеша."""
    from .models import PasswordResetRequest
    password = generate_temp_password()
    user = reader.user
    user.set_password(password)
    user.save(update_fields=['password'])
    reader.must_change_password = True
    reader.save(update_fields=['must_change_password'])
    PasswordResetRequest.objects.filter(reader=reader, status=PasswordResetRequest.STATUS_NEW).update(
        status=PasswordResetRequest.STATUS_DONE, handled_by=admin_user, handled_at=timezone.now())
    return password
