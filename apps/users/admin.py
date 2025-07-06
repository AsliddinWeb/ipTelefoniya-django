# apps/users/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, AdminProfile, MonitoringProfile, ClientProfile, OperatorProfile


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'role', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    fieldsets = UserAdmin.fieldsets + (
        ('Role Information', {'fields': ('role',)}),
    )


@admin.register(AdminProfile)
class AdminProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'created_at']
    search_fields = ['user__username', 'full_name']
    list_filter = ['created_at']


@admin.register(MonitoringProfile)
class MonitoringProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'created_at']
    search_fields = ['user__username', 'full_name']
    list_filter = ['created_at']


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'company_name', 'subscription_type', 'is_active_subscription', 'created_at']
    search_fields = ['user__username', 'full_name', 'company_name']
    list_filter = ['subscription_type', 'is_active_subscription', 'created_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'full_name')
        }),
        ('Company Information', {
            'fields': ('company_name', 'contact_person', 'phone', 'address')
        }),
        ('Subscription Information', {
            'fields': ('subscription_type', 'subscription_start', 'subscription_end', 'is_active_subscription')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(OperatorProfile)
class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'full_name', 'operator_id', 'get_client_name', 'department', 'is_active', 'created_at']
    search_fields = ['user__username', 'full_name', 'operator_id', 'client__company_name']
    list_filter = ['client', 'department', 'is_active', 'created_at']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('User Information', {
            'fields': ('user', 'full_name')
        }),
        ('Operator Information', {
            'fields': ('operator_id', 'client', 'domen', 'phone')
        }),
        ('Work Information', {
            'fields': ('department', 'position', 'is_active')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def get_client_name(self, obj):
        return obj.get_client_name()

    get_client_name.short_description = 'Client'


# Inline admin for operators in client admin
class OperatorInline(admin.TabularInline):
    model = OperatorProfile
    extra = 0
    fields = ['user', 'full_name', 'operator_id', 'department', 'is_active']
    readonly_fields = ['user']