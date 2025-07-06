# apps/users/models.py
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        MONITORING = 'monitoring', 'Monitoring'
        CLIENT = 'client', 'Client'
        OPERATOR = 'operator', 'Operator'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CLIENT
    )

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    def get_role_profile(self):
        """Role ga qarab profile obyektini qaytaradi"""
        if self.role == 'admin':
            return getattr(self, 'admin_profile', None)
        elif self.role == 'monitoring':
            return getattr(self, 'monitoring_profile', None)
        elif self.role == 'client':
            return getattr(self, 'client_profile', None)
        elif self.role == 'operator':
            return getattr(self, 'operator_profile', None)
        return None


class AdminProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='admin_profile')
    full_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="To'liq ism familiya")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Admin: {self.full_name}"

    class Meta:
        verbose_name = "Admin Profile"
        verbose_name_plural = "Admin Profiles"


class MonitoringProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='monitoring_profile')
    full_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="To'liq ism familiya")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Monitoring: {self.full_name}"

    class Meta:
        verbose_name = "Monitoring Profile"
        verbose_name_plural = "Monitoring Profiles"


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='client_profile')
    full_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="To'liq ism familiya")
    company_name = models.CharField(max_length=200, verbose_name="Kompaniya nomi")

    contact_person = models.CharField(max_length=100, verbose_name="Aloqa shaxsi")
    phone = models.CharField(max_length=20, verbose_name="Telefon raqami")
    address = models.TextField(verbose_name="Manzil")

    subscription_type = models.CharField(
        max_length=20,
        choices=[
            ('basic', "Boshlang'ich"),
            ('standard', 'Standart'),
            ('premium', 'Premium'),
            ('enterprise', 'Korporativ'),
        ],
        default='basic',
        null=True,
        blank=True,
        verbose_name="Obuna turi"
    )
    subscription_start = models.DateField(verbose_name="Obuna boshlanishi", null=True, blank=True)
    subscription_end = models.DateField(verbose_name="Obuna tugashi", null=True, blank=True)
    is_active_subscription = models.BooleanField(default=True, verbose_name="Faol obuna")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Client: {self.full_name} - {self.company_name}"

    def get_operators(self):
        """Bu clientga tegishli operatorlar"""
        return self.operators.all()

    def get_active_operators(self):
        """Bu clientga tegishli faol operatorlar"""
        return self.operators.filter(user__is_active=True)

    class Meta:
        verbose_name = "Client Profile"
        verbose_name_plural = "Client Profiles"


class OperatorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='operator_profile')
    full_name = models.CharField(max_length=100, blank=True, null=True, verbose_name="To'liq ism familiya")

    # Client bilan bog'lanish (operator clientning xodimi)
    client = models.ForeignKey(
        ClientProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operators',
        verbose_name="Tegishli client"
    )

    domen = models.CharField(max_length=100, blank=True, null=True, verbose_name="Domen")
    operator_id = models.CharField(max_length=20, unique=True, verbose_name="Operator ID")
    phone = models.CharField(max_length=20, blank=True, null=True, verbose_name="Telefon")

    # Qo'shimcha ma'lumotlar
    department = models.CharField(max_length=100, blank=True, null=True, verbose_name="Bo'lim")
    position = models.CharField(max_length=100, blank=True, null=True, verbose_name="Lavozim")
    is_active = models.BooleanField(default=True, verbose_name="Faol")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        client_name = self.client.company_name if self.client else "Mustaqil"
        return f"Operator: {self.full_name} - {self.operator_id} ({client_name})"

    def get_client_name(self):
        """Operator tegishli client nomini qaytaradi"""
        return self.client.company_name if self.client else "Mustaqil operator"

    def get_extensions(self):
        """Bu operatorga tegishli ichki raqamlar ro'yxati"""
        # Bu yerda PBX service dan operator_id bo'yicha extensions olish mumkin
        # Hozircha static qiymat qaytaramiz
        return [self.operator_id, f"{self.operator_id}01"] if self.operator_id else []

    def is_independent(self):
        """Mustaqil operator ekanligini tekshiradi"""
        return self.client is None

    class Meta:
        verbose_name = "Operator Profile"
        verbose_name_plural = "Operator Profiles"
        ordering = ['client__company_name', 'full_name']