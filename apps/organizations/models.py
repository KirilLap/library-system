from django.contrib.auth.models import User
from django.db import models


class OrgAccount(models.Model):
    """Shared anonymous login account for an organization / delivery point."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='org_account')
    location = models.OneToOneField(
        'locations.Location',
        on_delete=models.CASCADE,
        related_name='org_account',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Аккаунт организации'
        verbose_name_plural = 'Аккаунты организаций'

    def __str__(self):
        return f'{self.location.name} ({self.user.username})'


class LocationWorker(models.Model):
    """Personal worker account tied to a delivery point."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='worker_profile')
    location = models.ForeignKey(
        'locations.Location', on_delete=models.CASCADE,
        related_name='workers', verbose_name='Библиопункт'
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Работник библиопункта'
        verbose_name_plural = 'Работники библиопунктов'

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username} ({self.location.name})'

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username
