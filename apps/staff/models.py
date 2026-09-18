from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class StaffProfile(models.Model):
    ROLE_ADMIN = 'ADMIN'
    ROLE_LIBRARIAN = 'LIBRARIAN'
    ROLE_CHOICES = [
        (ROLE_ADMIN, _('Администратор')),
        (ROLE_LIBRARIAN, _('Библиотекарь')),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    language = models.CharField(
        max_length=10, blank=True, verbose_name='Язык интерфейса',
        help_text='Запоминается при переключении языка и применяется при следующем входе.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Сотрудник'
        verbose_name_plural = 'Сотрудники'
        ordering = ['role', 'user__last_name']

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.get_role_display()})'

    @property
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username


class ActionLog(models.Model):
    """Журнал действий сотрудников — кто и что изменил."""

    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='action_logs', verbose_name='Сотрудник',
    )
    action = models.CharField(max_length=500, verbose_name='Действие')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Когда')

    class Meta:
        verbose_name = 'Запись журнала'
        verbose_name_plural = 'Журнал действий'
        ordering = ['-created_at']

    def __str__(self):
        who = self.actor.get_full_name() or self.actor.username if self.actor else 'Система'
        return f'{who}: {self.action}'

    @staticmethod
    def log(user, action):
        """Записать действие сотрудника. Не бросает исключений — журнал не
        должен ронять основную операцию, если вдруг что-то пойдёт не так."""
        try:
            ActionLog.objects.create(
                actor=user if getattr(user, 'is_authenticated', False) else None,
                action=action,
            )
        except Exception:
            pass
