from django.contrib.auth.models import User
from django.db import models


class OrgAccount(models.Model):
    """Login account for an organization / delivery point."""

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
