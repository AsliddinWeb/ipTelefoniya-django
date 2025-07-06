# apps/users/urls.py
from django.urls import path
from .views import (
    login_view, logout_view, dashboard, profile_view,
    create_profile, edit_profile, dashboard_data_api,
    get_cdr_ajax, call_statistics_ajax,
    calls_list_view, calls_export_view, call_detail_view,
    # Client calls views
    client_calls_list_view, client_calls_export_view,
    client_call_detail_view, client_calls_statistics_ajax
)

# Operator management views import
from .views import (
    operators_list, active_operators_list, add_operator,
    edit_operator, toggle_operator_status, delete_operator,
    bulk_operator_actions, operator_detail
)

# Monitoring
from .views import (
    client_detail_view, client_chart_data_api
)

urlpatterns = [
    # Auth URLs
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    # Dashboard URLs
    path('dashboard/', dashboard, name='dashboard'),
    path('api/dashboard-data/', dashboard_data_api, name='dashboard_data_api'),
    path('api/cdr/', get_cdr_ajax, name='get_cdr_ajax'),
    path('api/statistics/', call_statistics_ajax, name='call_statistics_ajax'),

    # Client Dashboard Calls URLs
    path('dashboard/calls/', client_calls_list_view, name='client_calls_list'),
    path('dashboard/calls/export/', client_calls_export_view, name='client_calls_export'),
    path('dashboard/calls/detail/<str:call_id>/', client_call_detail_view, name='client_call_detail'),
    path('dashboard/calls/statistics/', client_calls_statistics_ajax, name='client_calls_statistics'),

    # Profile URLs
    path('profile/', profile_view, name='profile'),
    path('profile/create/', create_profile, name='create_profile'),
    path('profile/edit/', edit_profile, name='edit_profile'),

    # Operator Management URLs (Client role uchun)
    path('dashboard/operators/', operators_list, name='operators_list'),
    path('dashboard/operators/active/', active_operators_list, name='active_operators_list'),
    path('dashboard/operators/add/', add_operator, name='add_operator'),
    path('dashboard/operators/<int:operator_id>/', operator_detail, name='operator_detail'),
    path('dashboard/operators/<int:operator_id>/edit/', edit_operator, name='edit_operator'),
    path('dashboard/operators/<int:operator_id>/toggle-status/', toggle_operator_status, name='toggle_operator_status'),
    path('dashboard/operators/<int:operator_id>/delete/', delete_operator, name='delete_operator'),

    # Bulk operator actions
    path('operators/bulk-actions/', bulk_operator_actions, name='bulk_operator_actions'),

    # Monitoring
    path('dashboard/client/<int:client_id>/', client_detail_view, name='client_detail'),
    path('dashboard/client/<int:client_id>/chart-data/', client_chart_data_api, name='client_chart_data'),
]