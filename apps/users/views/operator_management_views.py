# apps/users/views/operator_management_views.py
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from datetime import timedelta
import json

from ..models import OperatorProfile, ClientProfile, User
from ..services.pbx_service import pbx_service
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


def client_required(view_func):
    """Client role'i talab qiladigan decorator"""

    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')

        if request.user.role != 'client':
            messages.error(request, "Bu sahifa faqat client'lar uchun")
            return redirect('dashboard')

        client_profile = request.user.get_role_profile()
        if not client_profile:
            messages.error(request, "Client profil topilmadi")
            return redirect('create_profile')

        return view_func(request, *args, **kwargs)

    return _wrapped_view


@login_required
@client_required
def operators_list(request):
    """Barcha operatorlar ro'yxati (faqat client'ning operatorlari)"""
    client_profile = request.user.get_role_profile()

    # Filter parametrlar
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    department_filter = request.GET.get('department', '')
    per_page = int(request.GET.get('per_page', 25))

    # Client'ga tegishli operatorlar
    operators = client_profile.operators.select_related('user').all()

    # Search
    if search_query:
        operators = operators.filter(
            Q(full_name__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(operator_id__icontains=search_query) |
            Q(phone__icontains=search_query)
        )

    # Status filter
    if status_filter == 'active':
        operators = operators.filter(user__is_active=True)
    elif status_filter == 'inactive':
        operators = operators.filter(user__is_active=False)

    # Department filter
    if department_filter:
        operators = operators.filter(department__icontains=department_filter)

    # Ordering
    operators = operators.order_by('-created_at')

    # Pagination
    paginator = Paginator(operators, per_page)
    page = request.GET.get('page', 1)

    try:
        operators_page = paginator.page(page)
    except PageNotAnInteger:
        operators_page = paginator.page(1)
    except EmptyPage:
        operators_page = paginator.page(paginator.num_pages)

    # Har bir operator uchun qo'shimcha ma'lumotlar
    for operator in operators_page:
        # Bugungi qo'ng'iroqlar soni
        try:
            today = timezone.now().date()
            operator_calls_response = pbx_service.get_cdr_data(
                start_date=today.strftime('%Y-%m-%d'),
                end_date=today.strftime('%Y-%m-%d'),
                src=operator.operator_id
            )
            operator_calls_data = pbx_service.process_cdr_data(operator_calls_response)

            if operator_calls_data['success']:
                operator.today_calls_count = operator_calls_data['statistics'].get('total_calls', 0)
                operator.success_rate = operator_calls_data['statistics'].get('answer_rate', 0)
            else:
                operator.today_calls_count = 0
                operator.success_rate = 0
        except Exception as e:
            logger.warning(f"Could not get calls for operator {operator.operator_id}: {str(e)}")
            operator.today_calls_count = 0
            operator.success_rate = 0

    # Statistics
    total_operators = client_profile.operators.count()
    active_operators = client_profile.operators.filter(user__is_active=True).count()
    inactive_operators = total_operators - active_operators

    # Departments list for filter
    departments = client_profile.operators.exclude(
        department__isnull=True
    ).exclude(
        department__exact=''
    ).values_list('department', flat=True).distinct()

    context = {
        'title': 'Operatorlar',
        'operators': operators_page,
        'search_query': search_query,
        'status_filter': status_filter,
        'department_filter': department_filter,
        'per_page': per_page,
        'stats': {
            'total': total_operators,
            'active': active_operators,
            'inactive': inactive_operators,
        },
        'departments': departments,
        'status_choices': [
            ('', 'Barcha holat'),
            ('active', 'Faol'),
            ('inactive', 'Nofaol'),
        ],
        'per_page_choices': [10, 25, 50, 100],
    }

    return render(request, 'dashboards/client/operators/operators_list.html', context)


@login_required
@client_required
def active_operators_list(request):
    """Faol operatorlar ro'yxati"""
    # operators_list view'ini ishlatamiz, lekin status filter bilan
    request.GET = request.GET.copy()
    request.GET['status'] = 'active'

    return operators_list(request)


@login_required
@client_required
def add_operator(request):
    """Yangi operator qo'shish"""
    client_profile = request.user.get_role_profile()

    if request.method == 'POST':
        try:
            # Form ma'lumotlarini olish
            username = request.POST.get('username', '').strip()
            email = request.POST.get('email', '').strip()
            password = request.POST.get('password', '').strip()
            full_name = request.POST.get('full_name', '').strip()
            operator_id = request.POST.get('operator_id', '').strip()
            phone = request.POST.get('phone', '').strip()
            position = request.POST.get('position', '').strip() or 'Operator'
            department = request.POST.get('department', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            # Validation
            if not all([username, email, password, full_name, operator_id]):
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({'success': False, 'error': 'Majburiy maydonlarni to\'ldiring'})
                messages.error(request, 'Majburiy maydonlarni to\'ldiring')
                return render(request, 'dashboards/client/operators/add_operator.html', {'client_profile': client_profile})

            # Username noyobligini tekshirish
            if User.objects.filter(username=username).exists():
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({'success': False, 'error': f'Username "{username}" band'})
                messages.error(request, f'Username "{username}" allaqachon band')
                return render(request, 'dashboards/client/operators/add_operator.html', {'client_profile': client_profile})

            # Email noyobligini tekshirish
            if User.objects.filter(email=email).exists():
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({'success': False, 'error': f'Email "{email}" band'})
                messages.error(request, f'Email "{email}" allaqachon ro\'yxatda')
                return render(request, 'dashboards/client/operators/add_operator.html', {'client_profile': client_profile})

            # Operator ID noyobligini tekshirish
            if OperatorProfile.objects.filter(operator_id=operator_id).exists():
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({'success': False, 'error': f'Operator ID "{operator_id}" band'})
                messages.error(request, f'Operator ID "{operator_id}" allaqachon mavjud')
                return render(request, 'dashboards/client/operators/add_operator.html', {'client_profile': client_profile})

            # Password validation
            if len(password) < 8:
                if request.headers.get('Content-Type') == 'application/json':
                    return JsonResponse({'success': False, 'error': 'Parol kamida 8 belgidan iborat bo\'lishi kerak'})
                messages.error(request, 'Parol kamida 8 belgidan iborat bo\'lishi kerak')
                return render(request, 'dashboards/client/operators/add_operator.html', {'client_profile': client_profile})

            # Transaction ichida user va operator yaratish
            with transaction.atomic():
                # User yaratish
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role='operator',
                    is_active=is_active
                )

                # Operator profile yaratish
                operator_profile = OperatorProfile.objects.create(
                    user=user,
                    client=client_profile,
                    full_name=full_name,
                    operator_id=operator_id,
                    phone=phone,
                    position=position,
                    department=department,
                    is_active=is_active
                )

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': f'Operator "{full_name}" muvaffaqiyatli qo\'shildi',
                    'operator_id': operator_profile.id
                })

            messages.success(request, f'Operator "{full_name}" muvaffaqiyatli qo\'shildi')
            return redirect('operators_list')

        except Exception as e:
            logger.error(f"Error creating operator: {str(e)}")
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({'success': False, 'error': f'Xatolik yuz berdi: {str(e)}'})
            messages.error(request, f'Xatolik yuz berdi: {str(e)}')

    context = {
        'title': 'Yangi operator qo\'shish',
        'client_profile': client_profile,
    }

    return render(request, 'dashboards/client/operators/add_operator.html', context)


@login_required
@client_required
def edit_operator(request, operator_id):
    """Operator tahrirlash"""
    client_profile = request.user.get_role_profile()

    # Faqat client'ga tegishli operatorni olish
    operator = get_object_or_404(
        OperatorProfile,
        id=operator_id,
        client=client_profile
    )

    if request.method == 'POST':
        try:
            # Form ma'lumotlarini olish
            full_name = request.POST.get('full_name', '').strip()
            email = request.POST.get('email', '').strip()
            phone = request.POST.get('phone', '').strip()
            position = request.POST.get('position', '').strip()
            department = request.POST.get('department', '').strip()
            is_active = request.POST.get('is_active') == 'on'

            # Validation
            if not all([full_name, email]):
                messages.error(request, 'Majburiy maydonlarni to\'ldiring')
                return render(request, 'dashboards/client/operators/edit_operator.html', {'operator': operator})

            # Email noyobligini tekshirish (o'zidan boshqa)
            if User.objects.filter(email=email).exclude(id=operator.user.id).exists():
                messages.error(request, f'Email "{email}" allaqachon ro\'yxatda')
                return render(request, 'dashboards/client/operators/edit_operator.html', {'operator': operator})

            # Ma'lumotlarni yangilash
            with transaction.atomic():
                # User ma'lumotlarini yangilash
                operator.user.email = email
                operator.user.is_active = is_active
                operator.user.save()

                # Operator profile yangilash
                operator.full_name = full_name
                operator.phone = phone
                operator.position = position
                operator.department = department
                operator.is_active = is_active
                operator.save()

            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({
                    'success': True,
                    'message': f'Operator "{full_name}" ma\'lumotlari yangilandi'
                })

            messages.success(request, f'Operator "{full_name}" ma\'lumotlari yangilandi')
            return redirect('operators_list')

        except Exception as e:
            logger.error(f"Error updating operator: {str(e)}")
            if request.headers.get('Content-Type') == 'application/json':
                return JsonResponse({'success': False, 'error': f'Xatolik yuz berdi: {str(e)}'})
            messages.error(request, f'Xatolik yuz berdi: {str(e)}')

    context = {
        'title': 'Operator tahrirlash',
        'operator': operator,
        'client_profile': client_profile,
    }

    return render(request, 'dashboards/client/operators/edit_operator.html', context)


@login_required
@client_required
def toggle_operator_status(request, operator_id):
    """Operator holatini o'zgartirish (faol/nofaol)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})

    client_profile = request.user.get_role_profile()

    try:
        # Faqat client'ga tegishli operatorni olish
        operator = get_object_or_404(
            OperatorProfile,
            id=operator_id,
            client=client_profile
        )

        # JSON data olish
        try:
            data = json.loads(request.body)
            action = data.get('action')
        except:
            action = request.POST.get('action')

        # Holatni o'zgartirish
        if action == 'activate':
            operator.user.is_active = True
            operator.is_active = True
            status_text = 'faollashtirildi'
        elif action == 'deactivate':
            operator.user.is_active = False
            operator.is_active = False
            status_text = 'faolsizlashtirildi'
        else:
            return JsonResponse({'success': False, 'error': 'Noto\'g\'ri action'})

        # Saqlash
        with transaction.atomic():
            operator.user.save()
            operator.save()

        return JsonResponse({
            'success': True,
            'message': f'Operator "{operator.full_name}" {status_text}',
            'new_status': operator.user.is_active
        })

    except Exception as e:
        logger.error(f"Error toggling operator status: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Xatolik yuz berdi: {str(e)}'})


@login_required
@client_required
def delete_operator(request, operator_id):
    """Operator o'chirish"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})

    client_profile = request.user.get_role_profile()

    try:
        # Faqat client'ga tegishli operatorni olish
        operator = get_object_or_404(
            OperatorProfile,
            id=operator_id,
            client=client_profile
        )

        operator_name = operator.full_name or operator.user.username

        # Operator va uning user'ini o'chirish
        with transaction.atomic():
            user = operator.user
            operator.delete()
            user.delete()

        return JsonResponse({
            'success': True,
            'message': f'Operator "{operator_name}" muvaffaqiyatli o\'chirildi'
        })

    except Exception as e:
        logger.error(f"Error deleting operator: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Xatolik yuz berdi: {str(e)}'})


@login_required
@client_required
def bulk_operator_actions(request):
    """Operator'lar uchun bulk amallar"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST method required'})

    client_profile = request.user.get_role_profile()

    try:
        data = json.loads(request.body)
        action = data.get('action')
        operator_ids = data.get('operator_ids', [])

        if not operator_ids:
            return JsonResponse({'success': False, 'error': 'Operator tanlanmagan'})

        # Faqat client'ga tegishli operator'larni olish
        operators = OperatorProfile.objects.filter(
            id__in=operator_ids,
            client=client_profile
        )

        if not operators.exists():
            return JsonResponse({'success': False, 'error': 'Operator topilmadi'})

        updated_count = 0

        with transaction.atomic():
            if action == 'activate':
                for operator in operators:
                    operator.user.is_active = True
                    operator.is_active = True
                    operator.user.save()
                    operator.save()
                    updated_count += 1
                message = f'{updated_count} ta operator faollashtirildi'

            elif action == 'deactivate':
                for operator in operators:
                    operator.user.is_active = False
                    operator.is_active = False
                    operator.user.save()
                    operator.save()
                    updated_count += 1
                message = f'{updated_count} ta operator faolsizlashtirildi'

            elif action == 'delete':
                operator_names = [op.full_name or op.user.username for op in operators]
                for operator in operators:
                    user = operator.user
                    operator.delete()
                    user.delete()
                    updated_count += 1
                message = f'{updated_count} ta operator o\'chirildi'

            else:
                return JsonResponse({'success': False, 'error': 'Noto\'g\'ri action'})

        return JsonResponse({
            'success': True,
            'message': message,
            'updated_count': updated_count
        })

    except Exception as e:
        logger.error(f"Error in bulk operator actions: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Xatolik yuz berdi: {str(e)}'})


@login_required
@client_required
def operator_detail(request, operator_id):
    """Operator tafsilotlari"""
    client_profile = request.user.get_role_profile()

    # Faqat client'ga tegishli operatorni olish
    operator = get_object_or_404(
        OperatorProfile,
        id=operator_id,
        client=client_profile
    )

    # Operator statistikalari
    try:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        # Bugungi qo'ng'iroqlar
        today_calls_response = pbx_service.get_cdr_data(
            start_date=today.strftime('%Y-%m-%d'),
            end_date=today.strftime('%Y-%m-%d'),
            src=operator.operator_id
        )
        today_calls_data = pbx_service.process_cdr_data(today_calls_response)

        # Haftalik qo'ng'iroqlar
        week_calls_response = pbx_service.get_cdr_data(
            start_date=week_ago.strftime('%Y-%m-%d'),
            end_date=today.strftime('%Y-%m-%d'),
            src=operator.operator_id
        )
        week_calls_data = pbx_service.process_cdr_data(week_calls_response)

        statistics = {
            'today': today_calls_data.get('statistics', {}) if today_calls_data['success'] else {},
            'week': week_calls_data.get('statistics', {}) if week_calls_data['success'] else {},
            'recent_calls': today_calls_data.get('calls', [])[-10:] if today_calls_data['success'] else []
        }

    except Exception as e:
        logger.error(f"Error getting operator statistics: {str(e)}")
        statistics = {
            'today': {},
            'week': {},
            'recent_calls': []
        }

    context = {
        'title': f'Operator: {operator.full_name or operator.user.username}',
        'operator': operator,
        'statistics': statistics,
        'client_profile': client_profile,
    }

    return render(request, 'dashboards/client/operators/operator_detail.html', context)