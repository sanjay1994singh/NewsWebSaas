from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class PlatformRole(models.TextChoices):
        NONE = 'none', 'No Platform Role'
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        SUPPORT_ADMIN = 'support_admin', 'Support Admin'

    platform_role = models.CharField(
        max_length=32,
        choices=PlatformRole.choices,
        default=PlatformRole.NONE,
        db_index=True,
    )

    @property
    def is_super_admin(self):
        return self.platform_role == self.PlatformRole.SUPER_ADMIN

    @property
    def is_support_admin(self):
        return self.platform_role == self.PlatformRole.SUPPORT_ADMIN
