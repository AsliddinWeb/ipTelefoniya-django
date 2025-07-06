# apps/users/views/profile_views.py
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from ..models import AdminProfile, MonitoringProfile, ClientProfile, OperatorProfile


@login_required
def profile_view(request):
    """Profil sahifasi - role ga qarab"""
    user = request.user
    role_profile = user.get_role_profile()

    if not role_profile:
        return redirect('create_profile')

    # Role ga qarab template tanlash
    template_mapping = {
        'admin': 'profiles/admin_profile.html',
        'monitoring': 'profiles/monitoring_profile.html',
        'operator': 'profiles/operator_profile.html',
        'client': 'profiles/client_profile.html',
    }

    template_name = template_mapping.get(user.role, 'profiles/default_profile.html')

    context = {
        'user': user,
        'role_profile': role_profile,
    }

    # Client role uchun qo'shimcha ma'lumotlar
    if user.role == 'client':
        operators = role_profile.operators.all()
        active_operators = operators.filter(user__is_active=True)
        inactive_operators = operators.filter(user__is_active=False)

        context.update({
            'active_operators_count': active_operators.count(),
            'inactive_operators_count': inactive_operators.count(),
            'total_operators_count': operators.count(),
        })

    return render(request, template_name, context)


@login_required
def create_profile(request):
    """Role profile yaratish"""
    user = request.user

    # Agar profile allaqachon mavjud bo'lsa, redirect
    if user.get_role_profile():
        return redirect('profile')

    if request.method == 'POST':
        try:
            if user.role == 'admin':
                AdminProfile.objects.create(
                    user=user,
                    full_name=request.POST.get('full_name', '').strip()
                )
            elif user.role == 'monitoring':
                MonitoringProfile.objects.create(
                    user=user,
                    full_name=request.POST.get('full_name', '').strip()
                )
            elif user.role == 'operator':
                OperatorProfile.objects.create(
                    user=user,
                    full_name=request.POST.get('full_name', '').strip(),
                    domen=request.POST.get('domen', '').strip(),
                    operator_id=request.POST.get('operator_id', '').strip(),
                    phone=request.POST.get('phone', '').strip()
                )
            elif user.role == 'client':
                ClientProfile.objects.create(
                    user=user,
                    full_name=request.POST.get('full_name', '').strip(),
                    company_name=request.POST.get('company_name', '').strip(),
                    contact_person=request.POST.get('contact_person', '').strip(),
                    phone=request.POST.get('phone', '').strip(),
                    address=request.POST.get('address', '').strip(),
                    subscription_type=request.POST.get('subscription_type', 'basic'),
                    subscription_start=request.POST.get('subscription_start') or timezone.now().date(),
                    subscription_end=request.POST.get('subscription_end') or None,
                    is_active_subscription=request.POST.get('is_active_subscription') == 'on',
                )

            messages.success(request, 'Profile muvaffaqiyatli yaratildi!')
            return redirect('dashboard')

        except Exception as e:
            messages.error(request, f'Xatolik yuz berdi: {str(e)}')

    return render(request, 'profiles/create_profile.html', {'user': user})


@login_required
def edit_profile(request):
    """Profile tahrirlash"""
    user = request.user
    role_profile = user.get_role_profile()

    if not role_profile:
        return redirect('create_profile')

    if request.method == 'POST':
        try:
            # Common fields
            if hasattr(role_profile, 'full_name'):
                role_profile.full_name = request.POST.get('full_name', '').strip()

            # Role-specific fields
            if user.role == 'client':
                role_profile.company_name = request.POST.get('company_name', '').strip()
                role_profile.contact_person = request.POST.get('contact_person', '').strip()
                role_profile.phone = request.POST.get('phone', '').strip()
                role_profile.address = request.POST.get('address', '').strip()

            elif user.role == 'operator':
                role_profile.domen = request.POST.get('domen', '').strip()
                role_profile.operator_id = request.POST.get('operator_id', '').strip()
                role_profile.phone = request.POST.get('phone', '').strip()

            role_profile.save()
            messages.success(request, 'Profile muvaffaqiyatli yangilandi!')
            return redirect('profile')

        except Exception as e:
            messages.error(request, f'Xatolik yuz berdi: {str(e)}')

    template_mapping = {
        'admin': 'users/profiles/edit_admin.html',
        'monitoring': 'users/profiles/edit_monitoring.html',
        'operator': 'users/profiles/edit_operator.html',
        'client': 'users/profiles/edit_client.html',
    }

    template_name = template_mapping.get(user.role, 'users/profiles/edit_default.html')

    context = {
        'user': user,
        'role_profile': role_profile,
    }

    return render(request, template_name, context)
