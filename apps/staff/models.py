from django.contrib.auth.models import User
from django.db import models


class StaffProfile(models.Model):
    ROLE_ADMIN = 'ADMIN'
    ROLE_LIBRARIAN = 'LIBRARIAN'
    ROLE_CHOICES = [
        (ROLE_ADMIN, 'Администратор'),
        (ROLE_LIBRARIAN, 'Библиотекарь'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='staff_profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    is_active = models.BooleanField(default=True, verbose_name='Активен')
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
