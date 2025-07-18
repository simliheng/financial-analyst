# backend/users/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    is_admin = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        permissions = [
            ("view_admin_dashboard", "Can view admin dashboard"),
            ("manage_categories", "Can manage financial categories"),
            ("view_user_statistics", "Can view user statistics and analytics"),
            ("manage_own_finances", "Can manage own financial data"),
        ]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        # Set admin status based on superuser
        if self.is_superuser:
            self.is_admin = True
            self.is_staff = True
        
        # Set default permissions for regular users
        creating = not self.pk  # Check if this is a new user
        super().save(*args, **kwargs)
        
        if creating:
            from django.contrib.auth.models import Permission
            from django.contrib.contenttypes.models import ContentType
            
            # If admin, grant admin permissions
            if self.is_admin:
                admin_permissions = Permission.objects.filter(
                    codename__in=['view_admin_dashboard', 'manage_categories', 'view_user_statistics']
                )
                self.user_permissions.add(*admin_permissions)
            
            # Grant basic user permissions
            content_type = ContentType.objects.get_for_model(CustomUser)
            basic_permission = Permission.objects.get(
                codename='manage_own_finances',
                content_type=content_type,
            )
            self.user_permissions.add(basic_permission)

    @property
    def is_staff_admin(self):
        return self.is_staff and self.is_admin