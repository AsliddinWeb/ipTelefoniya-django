# apps/users/views/dashboard_views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.db.models import Count, Q
from datetime import timedelta
from ..models import User, AdminProfile, MonitoringProfile, ClientProfile, OperatorProfile
from ..services.pbx_service import pbx_service
import logging

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
import csv

logger = logging.getLogger(__name__)

def home_view(request):
    return redirect('dashboard')

@login_required
def dashboard(request):
    """Role ga qarab dashboard render qilish"""
    user = request.user
    role_profile = user.get_role_profile()

    # Agar profile mavjud bo'lmasa, yaratishga yo'naltirish
    if not role_profile:
        return redirect('create_profile')

    # Role ga qarab template va context tanlash
    if user.role == 'admin':
        return admin_dashboard_view(request, user, role_profile)
    elif user.role == 'monitoring':
        return monitoring_dashboard_view(request, user, role_profile)
    elif user.role == 'operator':
        return operator_dashboard_view(request, user, role_profile)
    elif user.role == 'client':
        return client_dashboard_view(request, user, role_profile)
    else:
        return render(request, 'users/dashboards/default_dashboard.html', {
            'title': 'Dashboard',
            'user': user,
        })


def admin_dashboard_view(request, user, admin_profile):
    """Admin dashboard with PBX data"""
    context = {
        'title': 'Admin Dashboard',
        'user': user,
        'admin_profile': admin_profile,
    }

    try:
        # Statistikalar
        total_users = User.objects.count()

        # Role bo'yicha statistika
        role_stats = User.objects.values('role').annotate(count=Count('id'))
        role_counts = {item['role']: item['count'] for item in role_stats}

        # Oxirgi 30 kun ichida ro'yxatdan o'tganlar
        last_30_days = timezone.now() - timedelta(days=30)
        new_users_count = User.objects.filter(date_joined__gte=last_30_days).count()

        # Faol/nofaol foydalanuvchilar
        active_users = User.objects.filter(is_active=True).count()
        inactive_users = User.objects.filter(is_active=False).count()

        # Oxirgi foydalanuvchilar
        recent_users = User.objects.order_by('-date_joined')[:10]

        # Obuna tugash ogohlantirishi (client'lar uchun)
        expiring_soon = ClientProfile.objects.filter(
            subscription_end__lte=timezone.now().date() + timedelta(days=30),
            is_active_subscription=True
        ).count()

        # PBX ma'lumotlari
        today_calls = pbx_service.get_today_calls()
        context['today_calls'] = today_calls

        # So'nggi 10 ta qo'ng'iroq
        recent_cdr = pbx_service.get_cdr_data(limit=10)
        processed_cdr = pbx_service.process_cdr_data(recent_cdr)
        context['recent_calls'] = processed_cdr

        context.update({
            'stats': {
                'total_users': total_users,
                'admin_users': role_counts.get('admin', 0),
                'monitoring_users': role_counts.get('monitoring', 0),
                'operator_users': role_counts.get('operator', 0),
                'client_users': role_counts.get('client', 0),
                'new_users_count': new_users_count,
                'active_users': active_users,
                'inactive_users': inactive_users,
                'expiring_soon': expiring_soon,
            },
            'recent_users': recent_users,
        })

        logger.info(f"Admin dashboard loaded with {len(processed_cdr.get('calls', []))} recent calls")

    except Exception as e:
        logger.error(f"PBX API error in admin dashboard: {str(e)}")
        context['pbx_error'] = str(e)

    return render(request, 'dashboards/admin/dashboard_admin.html', context)


def operator_dashboard_view(request, user, operator_profile):
    """Operator dashboard with PBX data"""
    context = {
        'title': 'Operator Dashboard',
        'user': user,
        'operator_profile': operator_profile,
    }

    try:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        # Bugungi qo'ng'iroqlarni olish (service dan)
        today_calls_data = pbx_service.get_today_calls()

        # Service response formatini tekshirish
        if not today_calls_data.get('success', False):
            raise Exception(f"PBX service error: {today_calls_data.get('error', 'Unknown error')}")

        # Ma'lumotlarni ajratib olish
        today_calls = today_calls_data.get('calls', [])
        today_statistics = today_calls_data.get('statistics', {})

        # Kechagi ma'lumotlar (agar kerak bo'lsa)
        yesterday_str = yesterday.strftime('%Y-%m-%d')
        try:
            yesterday_calls_response = pbx_service.get_cdr_data(
                start_date=yesterday_str,
                end_date=yesterday_str
            )
            yesterday_calls_data = pbx_service.process_cdr_data(yesterday_calls_response)
            yesterday_statistics = yesterday_calls_data.get('statistics', {})
        except:
            yesterday_statistics = {}

        # Growth calculation
        def calculate_growth(today_val, yesterday_val):
            if yesterday_val == 0:
                return 100 if today_val > 0 else 0
            return round(((today_val - yesterday_val) / yesterday_val) * 100, 1)

        # So'nggi qo'ng'iroqlar (15 ta)
        recent_calls = today_calls[-15:] if today_calls else []
        recent_calls.reverse()  # Eng yangilarini birinchi qo'yish

        # Eng faol raqamlarni olish
        def get_most_active_numbers(statistics, limit=10):
            if not statistics:
                return []

            top_callers = statistics.get('top_callers', [])
            most_active = []

            for number, call_count in top_callers[:limit]:
                # Success rate hisoblash (agar ma'lumot bo'lsa)
                success_rate = 75  # Default qiymat

                # Telefon raqam formatini aniqlash
                is_internal = len(str(number)) <= 4 and not str(number).startswith('0')

                most_active.append({
                    'number': number,
                    'name': f"Extension {number}" if is_internal else "",
                    'call_count': call_count,
                    'success_rate': success_rate,
                    'is_internal': is_internal
                })

            return most_active

        most_active_numbers = get_most_active_numbers(today_statistics)

        # Operator'ning bugungi qo'ng'iroqlari
        operator_today_calls = 0
        operator_extensions = [operator_profile.operator_id] if operator_profile.operator_id else []

        if operator_extensions and today_calls:
            operator_calls = [
                call for call in today_calls
                if call.get('src') in operator_extensions or call.get('dst') in operator_extensions
            ]
            operator_today_calls = len(operator_calls)

        # System status
        system_status = True
        try:
            # Test connection bilan system status
            test_response = pbx_service.get_cdr_data(limit=1)
            system_status = test_response.get('status') == 'success'
        except:
            system_status = False

        # Current active calls (hozircha 0, chunki API da yo'q)
        current_active_calls = 0

        context.update({
            'pbx_data': {
                # Asosiy statistikalar (service dan)
                'total_calls': today_statistics.get('total_calls', 0),
                'answered_calls': today_statistics.get('answered_calls', 0),
                'failed_calls': today_statistics.get('missed_calls', 0),  # missed_calls = failed
                'no_answer_calls': today_statistics.get('missed_calls', 0),
                'avg_duration': round(
                    today_statistics.get('total_billsec', 0) / max(today_statistics.get('answered_calls', 1), 1), 1),

                # Growth indicators
                'total_calls_growth': calculate_growth(
                    today_statistics.get('total_calls', 0),
                    yesterday_statistics.get('total_calls', 0)
                ),
                'answered_calls_growth': calculate_growth(
                    today_statistics.get('answered_calls', 0),
                    yesterday_statistics.get('answered_calls', 0)
                ),
                'failed_calls_growth': calculate_growth(
                    today_statistics.get('missed_calls', 0),
                    yesterday_statistics.get('missed_calls', 0)
                ),
                'duration_growth': calculate_growth(
                    today_statistics.get('total_billsec', 0),
                    yesterday_statistics.get('total_billsec', 0)
                ),

                # Recent calls (service dan format qilingan)
                'recent_calls': recent_calls,

                # Active numbers
                'most_active_numbers': most_active_numbers,

                # Success rate (service dan)
                'success_rate': today_statistics.get('answer_rate', 0),

                # Current status
                'current_active_calls': current_active_calls,
                'system_status': system_status,

                # Operator specific
                'operator_today_calls': operator_today_calls,

                # Additional statistics
                'total_duration_formatted': today_statistics.get('total_duration_formatted', '0 soniya'),
                'by_direction': today_statistics.get('by_direction', {}),
                'by_hour': today_statistics.get('by_hour', {}),
            },

            # Operator info
            'operator_info': {
                'operator_id': operator_profile.operator_id,
                'domen': operator_profile.domen,
                'phone': operator_profile.phone,
                'extensions': operator_extensions,
            },

            # Date info
            'date_info': {
                'today': today,
                'yesterday': yesterday,
                'last_week': last_week,
            },

            # Service response ma'lumotlari (debug uchun)
            'service_response': {
                'total_records': today_calls_data.get('total_records', 0),
                'success': today_calls_data.get('success', False),
            }
        })

    except Exception as e:
        logger.error(f"PBX API error in operator dashboard: {str(e)}")
        context['pbx_error'] = str(e)

        # Fallback ma'lumotlar
        context.update({
            'pbx_data': {
                'total_calls': 0,
                'answered_calls': 0,
                'failed_calls': 0,
                'no_answer_calls': 0,
                'avg_duration': 0,
                'total_calls_growth': 0,
                'answered_calls_growth': 0,
                'failed_calls_growth': 0,
                'duration_growth': 0,
                'recent_calls': [],
                'most_active_numbers': [],
                'success_rate': 0,
                'current_active_calls': 0,
                'system_status': False,
                'operator_today_calls': 0,
                'total_duration_formatted': '0 soniya',
                'by_direction': {},
                'by_hour': {},
            },

            'operator_info': {
                'operator_id': operator_profile.operator_id,
                'domen': operator_profile.domen,
                'phone': operator_profile.phone,
                'extensions': [],
            },

            'date_info': {
                'today': timezone.now().date(),
                'yesterday': timezone.now().date() - timedelta(days=1),
                'last_week': timezone.now().date() - timedelta(days=7),
            },

            'service_response': {
                'total_records': 0,
                'success': False,
            }
        })

    return render(request, 'dashboards/operator/dashboard_operator.html', context)


def client_dashboard_view(request, user, client_profile):
    """Client dashboard with operators management and call monitoring"""
    context = {
        'title': 'Client Dashboard',
        'user': user,
        'client_profile': client_profile,
    }

    try:
        today = timezone.now().date()

        # Client'ga tegishli operatorlar
        operators_list = client_profile.operators.all().select_related('user')

        # Operator statistikalari
        total_operators = operators_list.count()
        active_operators = operators_list.filter(user__is_active=True).count()

        # Har bir operator uchun bugungi qo'ng'iroqlar soni
        operators_with_stats = []
        for operator in operators_list:
            # Operator'ning bugungi qo'ng'iroqlari
            try:
                operator_calls_response = pbx_service.get_cdr_data(
                    start_date=today.strftime('%Y-%m-%d'),
                    end_date=today.strftime('%Y-%m-%d'),
                    src=operator.operator_id
                )
                operator_calls_data = pbx_service.process_cdr_data(operator_calls_response)

                if operator_calls_data['success']:
                    operator_stats = operator_calls_data['statistics']
                    today_calls_count = operator_stats.get('total_calls', 0)
                    success_rate = operator_stats.get('answer_rate', 0)
                else:
                    today_calls_count = 0
                    success_rate = 0

            except Exception as e:
                logger.warning(f"Could not get calls for operator {operator.operator_id}: {str(e)}")
                today_calls_count = 0
                success_rate = 0

            # Operator objektiga statistika qo'shish
            operator.today_calls_count = today_calls_count
            operator.success_rate = success_rate
            operators_with_stats.append(operator)

        # Kompaniya umumiy qo'ng'iroqlari (barcha operatorlar)
        company_total_calls = 0
        company_answered_calls = 0
        recent_calls = []

        try:
            # Barcha operatorlarning ID lari
            operator_ids = [op.operator_id for op in operators_list if op.operator_id]

            if operator_ids:
                # Bugungi barcha qo'ng'iroqlar
                company_calls_response = pbx_service.get_cdr_data(
                    start_date=today.strftime('%Y-%m-%d'),
                    end_date=today.strftime('%Y-%m-%d')
                )
                company_calls_data = pbx_service.process_cdr_data(company_calls_response)

                if company_calls_data['success']:
                    all_calls = company_calls_data['calls']

                    # Faqat kompaniya operatorlariga tegishli qo'ng'iroqlarni filter qilish
                    company_calls = [
                        call for call in all_calls
                        if call.get('src') in operator_ids or call.get('dst') in operator_ids
                    ]

                    company_total_calls = len(company_calls)
                    company_answered_calls = len([c for c in company_calls if c.get('disposition') == 'ANSWERED'])

                    # So'nggi 10 ta qo'ng'iroq
                    recent_calls = company_calls[-10:] if company_calls else []
                    recent_calls.reverse()

        except Exception as e:
            logger.error(f"Error getting company calls: {str(e)}")

        # Success rate hisoblash
        company_success_rate = 0
        if company_total_calls > 0:
            company_success_rate = round((company_answered_calls / company_total_calls) * 100, 1)

        # Obuna ma'lumotlari
        subscription_info = {
            'type': client_profile.get_subscription_type_display() if client_profile.subscription_type else 'Noma\'lum',
            'start': client_profile.subscription_start,
            'end': client_profile.subscription_end,
            'is_active': client_profile.is_active_subscription,
            'days_left': None
        }

        if client_profile.subscription_end:
            days_left = (client_profile.subscription_end - today).days
            subscription_info['days_left'] = days_left if days_left > 0 else 0

        context.update({
            # Operator statistics
            'operators_stats': {
                'total': total_operators,
                'active': active_operators,
                'inactive': total_operators - active_operators,
            },

            # Operators list with stats
            'operators_list': operators_with_stats,

            # Company calls statistics
            'company_calls': {
                'total_today': company_total_calls,
                'answered_today': company_answered_calls,
                'success_rate': company_success_rate,
                'recent_calls': recent_calls,
            },

            # Subscription info
            'subscription_info': subscription_info,

            # Date info
            'date_info': {
                'today': today,
            }
        })

    except Exception as e:
        logger.error(f"Error in client dashboard: {str(e)}")
        context['error'] = str(e)

        # Fallback ma'lumotlar
        context.update({
            'operators_stats': {
                'total': 0,
                'active': 0,
                'inactive': 0,
            },
            'operators_list': [],
            'company_calls': {
                'total_today': 0,
                'answered_today': 0,
                'success_rate': 0,
                'recent_calls': [],
            },
            'subscription_info': {
                'type': 'Noma\'lum',
                'start': None,
                'end': None,
                'is_active': False,
                'days_left': None
            },
            'date_info': {
                'today': timezone.now().date(),
            }
        })

    return render(request, 'dashboards/client/dashboard_client.html', context)


@login_required
def get_cdr_ajax(request):
    """AJAX orqali CDR ma'lumotlarini olish"""
    try:
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        limit = request.GET.get('limit', 50)
        extension = request.GET.get('extension')

        cdr_response = pbx_service.get_cdr_data(
            start_date=start_date,
            end_date=end_date,
            limit=int(limit),
            src=extension
        )

        processed_data = pbx_service.process_cdr_data(cdr_response)

        return JsonResponse({
            'success': True,
            'data': processed_data
        })

    except Exception as e:
        logger.error(f"CDR AJAX error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def call_statistics_ajax(request):
    """Qo'ng'iroq statistikasi uchun AJAX"""
    try:
        period = request.GET.get('period', 'today')

        if period == 'today':
            stats = pbx_service.get_today_calls()
        else:
            # Boshqa davrlar uchun
            days = {'week': 7, 'month': 30}.get(period, 1)
            start_date = (timezone.now() - timedelta(days=days)).strftime('%Y-%m-%d')
            end_date = timezone.now().strftime('%Y-%m-%d')

            cdr_response = pbx_service.get_cdr_data(start_date=start_date, end_date=end_date)
            stats = pbx_service.process_cdr_data(cdr_response)

        return JsonResponse({
            'success': True,
            'statistics': stats.get('statistics', {}),
            'total_calls': len(stats.get('calls', []))
        })

    except Exception as e:
        logger.error(f"Statistics AJAX error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
def dashboard_data_api(request):
    """Dashboard uchun JSON data (AJAX so'rovlar uchun)"""
    try:
        data = {}

        if request.user.role == 'admin':
            data = {
                'total_users': User.objects.count(),
                'active_users': User.objects.filter(is_active=True).count(),
                'new_users_today': User.objects.filter(
                    date_joined__date=timezone.now().date()
                ).count(),
            }
        elif request.user.role == 'monitoring':
            data = {
                'active_sessions': User.objects.filter(
                    last_login__gte=timezone.now() - timedelta(hours=1)
                ).count(),
            }

        return JsonResponse(data)

    except Exception as e:
        logger.error(f"Dashboard API error: {str(e)}")
        return JsonResponse({
            'error': str(e)
        }, status=500)


@login_required
def calls_list_view(request):
    """Qo'ng'iroqlar ro'yxati sahifasi"""
    context = {
        'title': 'Qo\'ng\'iroqlar tarixi',
        'user': request.user,
    }

    try:
        # Filter parametrlarini olish
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        src_filter = request.GET.get('src', '').strip()
        dst_filter = request.GET.get('dst', '').strip()
        disposition_filter = request.GET.get('disposition', '').strip()
        direction_filter = request.GET.get('direction', '').strip()
        search_query = request.GET.get('search', '').strip()
        page = request.GET.get('page', 1)
        per_page = int(request.GET.get('per_page', 25))

        # Default sanalar (agar berilmagan bo'lsa)
        if not start_date:
            start_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = timezone.now().strftime('%Y-%m-%d')

        # PBX service dan ma'lumotlarni olish
        cdr_params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        if src_filter:
            cdr_params['src'] = src_filter
        if dst_filter:
            cdr_params['dst'] = dst_filter

        # CDR ma'lumotlarini olish
        cdr_response = pbx_service.get_cdr_data(**cdr_params)
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            raise Exception(calls_data.get('error', 'Ma\'lumot olishda xatolik'))

        all_calls = calls_data['calls']
        statistics = calls_data['statistics']

        # Additional filtering (local)
        filtered_calls = all_calls

        # Disposition filter
        if disposition_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('disposition', '').upper() == disposition_filter.upper()]

        # Direction filter
        if direction_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('call_direction') == direction_filter]

        # Search filter
        if search_query:
            search_lower = search_query.lower()
            filtered_calls = [call for call in filtered_calls
                              if (search_lower in call.get('src', '').lower() or
                                  search_lower in call.get('dst', '').lower() or
                                  search_lower in call.get('caller_name', '').lower() or
                                  search_lower in call.get('caller_id', '').lower())]

        # Pagination
        paginator = Paginator(filtered_calls, per_page)

        try:
            calls = paginator.page(page)
        except PageNotAnInteger:
            calls = paginator.page(1)
        except EmptyPage:
            calls = paginator.page(paginator.num_pages)

        # Filter options
        disposition_choices = [
            ('', 'Barchasi'),
            ('ANSWERED', 'Javob berildi'),
            ('NO ANSWER', 'Javob berilmadi'),
            ('BUSY', 'Band'),
            ('FAILED', 'Muvaffaqiyatsiz'),
            ('CONGESTION', 'Tarmoq yuklanishi'),
        ]

        direction_choices = [
            ('', 'Barchasi'),
            ('incoming', 'Kiruvchi'),
            ('outgoing', 'Chiquvchi'),
            ('internal', 'Ichki'),
        ]

        per_page_choices = [10, 25, 50, 100]

        # Filtered statistics
        filtered_stats = pbx_service._calculate_call_statistics(filtered_calls)

        context.update({
            'calls': calls,
            'statistics': statistics,
            'filtered_stats': filtered_stats,
            'total_calls': len(all_calls),
            'filtered_total': len(filtered_calls),

            # Filter values
            'current_filters': {
                'start_date': start_date,
                'end_date': end_date,
                'src': src_filter,
                'dst': dst_filter,
                'disposition': disposition_filter,
                'direction': direction_filter,
                'search': search_query,
                'per_page': per_page,
            },

            # Filter choices
            'disposition_choices': disposition_choices,
            'direction_choices': direction_choices,
            'per_page_choices': per_page_choices,

            # Export URL
            'export_url': request.get_full_path().replace('/calls/', '/calls/export/'),
        })

    except Exception as e:
        logger.error(f"Calls list error: {str(e)}")
        messages.error(request, f'Ma\'lumotlarni yuklashda xatolik: {str(e)}')

        context.update({
            'calls': None,
            'statistics': {},
            'filtered_stats': {},
            'total_calls': 0,
            'filtered_total': 0,
            'current_filters': {
                'start_date': (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'end_date': timezone.now().strftime('%Y-%m-%d'),
                'src': '',
                'dst': '',
                'disposition': '',
                'direction': '',
                'search': '',
                'per_page': 25,
            },
            'disposition_choices': [],
            'direction_choices': [],
            'per_page_choices': [10, 25, 50, 100],
        })

    return render(request, 'dashboards/operator/calls_list.html', context)


@login_required
def calls_export_view(request):
    """Qo'ng'iroqlarni CSV formatida eksport qilish"""
    try:
        # Same filtering logic as list view
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        src_filter = request.GET.get('src', '').strip()
        dst_filter = request.GET.get('dst', '').strip()
        disposition_filter = request.GET.get('disposition', '').strip()
        direction_filter = request.GET.get('direction', '').strip()
        search_query = request.GET.get('search', '').strip()

        if not start_date:
            start_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = timezone.now().strftime('%Y-%m-%d')

        # Get data
        cdr_params = {
            'start_date': start_date,
            'end_date': end_date,
        }

        if src_filter:
            cdr_params['src'] = src_filter
        if dst_filter:
            cdr_params['dst'] = dst_filter

        cdr_response = pbx_service.get_cdr_data(**cdr_params)
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            messages.error(request, 'Eksport qilishda xatolik yuz berdi')
            return redirect('calls_list')

        all_calls = calls_data['calls']

        # Apply filters
        filtered_calls = all_calls

        if disposition_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('disposition', '').upper() == disposition_filter.upper()]

        if direction_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('call_direction') == direction_filter]

        if search_query:
            search_lower = search_query.lower()
            filtered_calls = [call for call in filtered_calls
                              if (search_lower in call.get('src', '').lower() or
                                  search_lower in call.get('dst', '').lower() or
                                  search_lower in call.get('caller_name', '').lower())]

        # Create CSV response
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="calls_{start_date}_to_{end_date}.csv"'

        writer = csv.writer(response)

        # CSV headers
        writer.writerow([
            'Sana', 'Vaqt', 'Qo\'ng\'iroq qiluvchi', 'Qabul qiluvchi',
            'Davomiyligi', 'Hisoblangan vaqt', 'Holati', 'Yo\'nalishi', 'Kanal'
        ])

        # CSV data
        for call in filtered_calls:
            writer.writerow([
                call.get('date', ''),
                call.get('time', ''),
                f"{call.get('caller_name', call.get('src', ''))} ({call.get('src', '')})",
                call.get('dst', ''),
                call.get('duration_formatted', ''),
                call.get('billsec_formatted', ''),
                call.get('disposition_uz', ''),
                call.get('call_direction_uz', ''),
                call.get('channel', ''),
            ])

        return response

    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        messages.error(request, f'Eksport qilishda xatolik: {str(e)}')
        return redirect('calls_list')


@login_required
def call_detail_view(request, call_id):
    """Qo'ng'iroq tafsilotlari"""
    context = {
        'title': 'Qo\'ng\'iroq tafsilotlari',
        'user': request.user,
    }

    try:
        # PBX service dan ma'lumotlarni olish
        # Hozircha barcha qo'ng'iroqlardan qidiramiz
        today = timezone.now().date()
        yesterday = today - timedelta(days=30)  # 30 kun ichida qidirish

        cdr_response = pbx_service.get_cdr_data(
            start_date=yesterday.strftime('%Y-%m-%d'),
            end_date=today.strftime('%Y-%m-%d')
        )
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            raise Exception('Ma\'lumot olishda xatolik')

        # Call ID bo'yicha qidirish
        call_detail = None
        for call in calls_data['calls']:
            if str(call.get('id')) == str(call_id) or str(call.get('uniqueid')) == str(call_id):
                call_detail = call
                break

        if not call_detail:
            # Agar topilmasa, dummy data bilan to'ldirish
            call_detail = {
                'id': call_id,
                'uniqueid': call_id,
                'calldate': '2025-02-10 15:30:45',
                'date': '10.02.2025',
                'time': '15:30:45',
                'caller_id': '""Khalilov Abbos"" <201>',
                'caller_name': 'Khalilov Abbos',
                'src': '201',
                'dst': '916411414',
                'context': 'from-internal',
                'channel': 'SIP/201-00000000',
                'dst_channel': 'SIP/tr752200122-00000000',
                'duration': 125,
                'billsec': 85,
                'duration_formatted': '2m 5s',
                'billsec_formatted': '1m 25s',
                'disposition': 'ANSWERED',
                'disposition_uz': 'Javob berildi',
                'recording_file': '',
                'call_direction': 'outgoing',
                'call_direction_uz': 'Chiquvchi',
                'is_answered': True,
                'raw_data': {
                    'calldate': '2025-02-10 15:30:45',
                    'clid': '""Khalilov Abbos"" <201>',
                    'src': '201',
                    'dst': '916411414',
                    'dcontext': 'from-internal',
                    'channel': 'SIP/201-00000000',
                    'dstchannel': 'SIP/tr752200122-00000000',
                    'duration': '125',
                    'billsec': '85',
                    'disposition': 'ANSWERED',
                    'uniqueid': call_id,
                }
            }

        # Ma'lumotlarni to'ldirish (agar ba'zi fieldlar bo'lmasa)
        def ensure_field(data, field, default=''):
            if field not in data or data[field] is None:
                data[field] = default
            return data[field]

        # Majburiy fieldlarni tekshirish va to'ldirish
        ensure_field(call_detail, 'billsec', 0)
        ensure_field(call_detail, 'billsec_formatted', f"{call_detail.get('billsec', 0)}s")
        ensure_field(call_detail, 'duration_formatted', f"{call_detail.get('duration', 0)}s")
        ensure_field(call_detail, 'disposition_uz', call_detail.get('disposition', 'Noma\'lum'))
        ensure_field(call_detail, 'call_direction', 'internal')
        ensure_field(call_detail, 'call_direction_uz', 'Ichki')
        ensure_field(call_detail, 'caller_name', call_detail.get('src', ''))
        ensure_field(call_detail, 'recording_file', '')
        ensure_field(call_detail, 'context', '')
        ensure_field(call_detail, 'dst_channel', '')
        ensure_field(call_detail, 'raw_data', {})

        context['call'] = call_detail

    except Exception as e:
        logger.error(f"Call detail error: {str(e)}")
        messages.error(request, f'Qo\'ng\'iroq ma\'lumotini olishda xatolik: {str(e)}')

        # Fallback ma'lumot
        context['call'] = {
            'id': call_id,
            'uniqueid': call_id,
            'calldate': 'Noma\'lum',
            'date': 'Noma\'lum',
            'time': 'Noma\'lum',
            'caller_id': '',
            'caller_name': 'Noma\'lum',
            'src': 'Noma\'lum',
            'dst': 'Noma\'lum',
            'context': '',
            'channel': '',
            'dst_channel': '',
            'duration': 0,
            'billsec': 0,
            'duration_formatted': '0s',
            'billsec_formatted': '0s',
            'disposition': 'UNKNOWN',
            'disposition_uz': 'Noma\'lum',
            'recording_file': '',
            'call_direction': 'internal',
            'call_direction_uz': 'Noma\'lum',
            'is_answered': False,
            'raw_data': {},
        }

    return render(request, 'dashboards/operator/call_detail.html', context)


# apps/users/views/dashboard_views.py ga qo'shiladigan qism

@login_required
def client_calls_list_view(request):
    """Client uchun qo'ng'iroqlar ro'yxati (faqat o'z operatorlariga tegishli)"""
    # if request.user.role != 'client':
    #     messages.error(request, "Bu sahifaga faqat client'lar kirishi mumkin")
    #     return redirect('dashboard')

    client_profile = request.user.client_profile
    # if not client_profile:
    #     messages.error(request, "Client profile topilmadi")
    #     return redirect('dashboard')

    context = {
        'title': 'Kompaniya qo\'ng\'iroqlari',
        'user': request.user,
        'client_profile': client_profile,
    }

    try:
        # Client'ga tegishli operatorlar ID lari
        operator_ids = list(client_profile.operators.values_list('operator_id', flat=True))

        if not operator_ids:
            context.update({
                'calls': None,
                'statistics': {},
                'filtered_stats': {},
                'total_calls': 0,
                'filtered_total': 0,
                'error_message': 'Sizning kompaniyangizda hozircha operatorlar mavjud emas',
                'current_filters': {
                    'start_date': (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                    'end_date': timezone.now().strftime('%Y-%m-%d'),
                    'operator': '',
                    'dst': '',
                    'disposition': '',
                    'direction': '',
                    'search': '',
                    'per_page': 25,
                },
                'disposition_choices': [],
                'direction_choices': [],
                'operator_choices': [],
                'per_page_choices': [10, 25, 50, 100],
            })
            return render(request, 'dashboards/client/calls_list.html', context)

        # Filter parametrlarini olish
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        operator_filter = request.GET.get('operator', '').strip()
        dst_filter = request.GET.get('dst', '').strip()
        disposition_filter = request.GET.get('disposition', '').strip()
        direction_filter = request.GET.get('direction', '').strip()
        search_query = request.GET.get('search', '').strip()
        page = request.GET.get('page', 1)
        per_page = int(request.GET.get('per_page', 25))

        # Default sanalar
        if not start_date:
            start_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = timezone.now().strftime('%Y-%m-%d')

        # PBX service dan ma'lumotlarni olish
        cdr_response = pbx_service.get_cdr_data(
            start_date=start_date,
            end_date=end_date
        )
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            raise Exception(calls_data.get('error', 'Ma\'lumot olishda xatolik'))

        all_calls = calls_data['calls']

        # Faqat client operatorlariga tegishli qo'ng'iroqlarni filter qilish
        client_calls = []
        for call in all_calls:
            src = call.get('src', '')
            dst = call.get('dst', '')

            # Agar src yoki dst client operatorlaridan birida bo'lsa
            if src in operator_ids or dst in operator_ids:
                client_calls.append(call)

        # Qo'shimcha filterlar
        filtered_calls = client_calls

        # Operator filter
        if operator_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('src') == operator_filter or call.get('dst') == operator_filter]

        # Destination filter
        if dst_filter:
            filtered_calls = [call for call in filtered_calls
                              if dst_filter.lower() in call.get('dst', '').lower()]

        # Disposition filter
        if disposition_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('disposition', '').upper() == disposition_filter.upper()]

        # Direction filter
        if direction_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('call_direction') == direction_filter]

        # Search filter
        if search_query:
            search_lower = search_query.lower()
            filtered_calls = [call for call in filtered_calls
                              if (search_lower in call.get('src', '').lower() or
                                  search_lower in call.get('dst', '').lower() or
                                  search_lower in call.get('caller_name', '').lower() or
                                  search_lower in call.get('caller_id', '').lower())]

        # Pagination
        paginator = Paginator(filtered_calls, per_page)
        try:
            calls = paginator.page(page)
        except PageNotAnInteger:
            calls = paginator.page(1)
        except EmptyPage:
            calls = paginator.page(paginator.num_pages)

        # Filter choices
        disposition_choices = [
            ('', 'Barchasi'),
            ('ANSWERED', 'Javob berildi'),
            ('NO ANSWER', 'Javob berilmadi'),
            ('BUSY', 'Band'),
            ('FAILED', 'Muvaffaqiyatsiz'),
            ('CONGESTION', 'Tarmoq yuklanishi'),
        ]

        direction_choices = [
            ('', 'Barchasi'),
            ('incoming', 'Kiruvchi'),
            ('outgoing', 'Chiquvchi'),
            ('internal', 'Ichki'),
        ]

        # Operator choices (client operatorlari)
        operator_choices = [('', 'Barcha operatorlar')]
        for operator in client_profile.operators.all():
            operator_choices.append((
                operator.operator_id,
                f"{operator.full_name} ({operator.operator_id})"
            ))

        per_page_choices = [10, 25, 50, 100]

        # Statistics
        client_stats = pbx_service._calculate_call_statistics(client_calls)
        filtered_stats = pbx_service._calculate_call_statistics(filtered_calls)

        context.update({
            'calls': calls,
            'statistics': client_stats,
            'filtered_stats': filtered_stats,
            'total_calls': len(client_calls),
            'filtered_total': len(filtered_calls),
            'operator_ids': operator_ids,

            # Filter values
            'current_filters': {
                'start_date': start_date,
                'end_date': end_date,
                'operator': operator_filter,
                'dst': dst_filter,
                'disposition': disposition_filter,
                'direction': direction_filter,
                'search': search_query,
                'per_page': per_page,
            },

            # Filter choices
            'disposition_choices': disposition_choices,
            'direction_choices': direction_choices,
            'operator_choices': operator_choices,
            'per_page_choices': per_page_choices,

            # Export URL
            'export_url': request.get_full_path().replace('/calls/', '/calls/export/'),
        })

    except Exception as e:
        logger.error(f"Client calls list error: {str(e)}")
        messages.error(request, f'Ma\'lumotlarni yuklashda xatolik: {str(e)}')

        context.update({
            'calls': None,
            'statistics': {},
            'filtered_stats': {},
            'total_calls': 0,
            'filtered_total': 0,
            'current_filters': {
                'start_date': (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d'),
                'end_date': timezone.now().strftime('%Y-%m-%d'),
                'operator': '',
                'dst': '',
                'disposition': '',
                'direction': '',
                'search': '',
                'per_page': 25,
            },
            'disposition_choices': [],
            'direction_choices': [],
            'operator_choices': [],
            'per_page_choices': [10, 25, 50, 100],
        })

    return render(request, 'dashboards/client/calls_list.html', context)


@login_required
def client_calls_export_view(request):
    """Client qo'ng'iroqlarini CSV formatida eksport qilish"""
    if request.user.role != 'client':
        messages.error(request, "Bu sahifaga faqat client'lar kirishi mumkin")
        return redirect('dashboard')

    client_profile = request.user.client_profile
    if not client_profile:
        messages.error(request, "Client profile topilmadi")
        return redirect('dashboard')

    try:
        # Client operatorlari
        operator_ids = list(client_profile.operators.values_list('operator_id', flat=True))

        if not operator_ids:
            messages.error(request, 'Eksport uchun operatorlar mavjud emas')
            return redirect('client_calls_list')

        # Filter parametrlari
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        operator_filter = request.GET.get('operator', '').strip()
        dst_filter = request.GET.get('dst', '').strip()
        disposition_filter = request.GET.get('disposition', '').strip()
        direction_filter = request.GET.get('direction', '').strip()
        search_query = request.GET.get('search', '').strip()

        if not start_date:
            start_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        if not end_date:
            end_date = timezone.now().strftime('%Y-%m-%d')

        # Ma'lumotlarni olish
        cdr_response = pbx_service.get_cdr_data(
            start_date=start_date,
            end_date=end_date
        )
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            messages.error(request, 'Eksport qilishda xatolik yuz berdi')
            return redirect('client_calls_list')

        all_calls = calls_data['calls']

        # Faqat client qo'ng'iroqlari
        client_calls = []
        for call in all_calls:
            src = call.get('src', '')
            dst = call.get('dst', '')
            if src in operator_ids or dst in operator_ids:
                client_calls.append(call)

        # Filterlarni qo'llash
        filtered_calls = client_calls

        if operator_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('src') == operator_filter or call.get('dst') == operator_filter]

        if dst_filter:
            filtered_calls = [call for call in filtered_calls
                              if dst_filter.lower() in call.get('dst', '').lower()]

        if disposition_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('disposition', '').upper() == disposition_filter.upper()]

        if direction_filter:
            filtered_calls = [call for call in filtered_calls
                              if call.get('call_direction') == direction_filter]

        if search_query:
            search_lower = search_query.lower()
            filtered_calls = [call for call in filtered_calls
                              if (search_lower in call.get('src', '').lower() or
                                  search_lower in call.get('dst', '').lower() or
                                  search_lower in call.get('caller_name', '').lower())]

        # CSV response
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="company_calls_{start_date}_to_{end_date}.csv"'

        # UTF-8 BOM qo'shish (Excel uchun)
        response.write('\ufeff')

        writer = csv.writer(response)

        # CSV headers
        writer.writerow([
            'Sana', 'Vaqt', 'Operator', 'Qabul qiluvchi/Qo\'ng\'iroq qiluvchi',
            'Davomiyligi', 'Hisoblangan vaqt', 'Holati', 'Yo\'nalishi', 'Kanal'
        ])

        # CSV data
        for call in filtered_calls:
            src = call.get('src', '')
            dst = call.get('dst', '')

            # Operator nomini aniqlash
            operator_name = src
            if src in operator_ids:
                try:
                    operator = client_profile.operators.get(operator_id=src)
                    operator_name = f"{operator.full_name} ({src})"
                except:
                    operator_name = src
            elif dst in operator_ids:
                try:
                    operator = client_profile.operators.get(operator_id=dst)
                    operator_name = f"{operator.full_name} ({dst})"
                except:
                    operator_name = dst

            # Ikkinchi shaxs (client operator bo'lmagan)
            other_party = dst if src in operator_ids else src

            writer.writerow([
                call.get('date', ''),
                call.get('time', ''),
                operator_name,
                other_party,
                call.get('duration_formatted', ''),
                call.get('billsec_formatted', ''),
                call.get('disposition_uz', ''),
                call.get('call_direction_uz', ''),
                call.get('channel', ''),
            ])

        return response

    except Exception as e:
        logger.error(f"Client export error: {str(e)}")
        messages.error(request, f'Eksport qilishda xatolik: {str(e)}')
        return redirect('client_calls_list')


@login_required
def client_call_detail_view(request, call_id):
    """Client uchun qo'ng'iroq tafsilotlari"""
    if request.user.role != 'client':
        messages.error(request, "Bu sahifaga faqat client'lar kirishi mumkin")
        return redirect('dashboard')

    client_profile = request.user.client_profile
    if not client_profile:
        messages.error(request, "Client profile topilmadi")
        return redirect('dashboard')

    context = {
        'title': 'Qo\'ng\'iroq tafsilotlari',
        'user': request.user,
        'client_profile': client_profile,
    }

    try:
        # Client operatorlari
        operator_ids = list(client_profile.operators.values_list('operator_id', flat=True))

        if not operator_ids:
            messages.error(request, 'Operatorlar mavjud emas')
            return redirect('client_calls_list')

        # Ma'lumotlarni qidirish
        today = timezone.now().date()
        last_month = today - timedelta(days=30)

        cdr_response = pbx_service.get_cdr_data(
            start_date=last_month.strftime('%Y-%m-%d'),
            end_date=today.strftime('%Y-%m-%d')
        )
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            raise Exception('Ma\'lumot olishda xatolik')

        # Call ID bo'yicha qidirish va client'ga tegishliligini tekshirish
        call_detail = None
        for call in calls_data['calls']:
            if (str(call.get('id')) == str(call_id) or str(call.get('uniqueid')) == str(call_id)):
                src = call.get('src', '')
                dst = call.get('dst', '')

                # Client operatoriga tegishli ekanligini tekshirish
                if src in operator_ids or dst in operator_ids:
                    call_detail = call
                    break

        if not call_detail:
            # Dummy data yaratish (test uchun)
            call_detail = {
                'id': call_id,
                'uniqueid': call_id,
                'calldate': '2025-02-10 15:30:45',
                'date': '10.02.2025',
                'time': '15:30:45',
                'caller_id': f'""Client Operator"" <{operator_ids[0] if operator_ids else "201"}>',
                'caller_name': 'Client Operator',
                'src': operator_ids[0] if operator_ids else '201',
                'dst': '916411414',
                'context': 'from-internal',
                'channel': f'SIP/{operator_ids[0] if operator_ids else "201"}-00000000',
                'dst_channel': 'SIP/tr752200122-00000000',
                'duration': 125,
                'billsec': 85,
                'duration_formatted': '2m 5s',
                'billsec_formatted': '1m 25s',
                'disposition': 'ANSWERED',
                'disposition_uz': 'Javob berildi',
                'recording_file': '',
                'call_direction': 'outgoing',
                'call_direction_uz': 'Chiquvchi',
                'is_answered': True,
                'raw_data': {}
            }

        # Operator ma'lumotlarini qo'shish
        src = call_detail.get('src', '')
        dst = call_detail.get('dst', '')

        call_detail['operator_info'] = None
        if src in operator_ids:
            try:
                operator = client_profile.operators.get(operator_id=src)
                call_detail['operator_info'] = {
                    'id': operator.operator_id,
                    'name': operator.full_name,
                    'department': operator.department,
                    'position': operator.position
                }
            except:
                pass
        elif dst in operator_ids:
            try:
                operator = client_profile.operators.get(operator_id=dst)
                call_detail['operator_info'] = {
                    'id': operator.operator_id,
                    'name': operator.full_name,
                    'department': operator.department,
                    'position': operator.position
                }
            except:
                pass

        # Majburiy fieldlarni tekshirish
        def ensure_field(data, field, default=''):
            if field not in data or data[field] is None:
                data[field] = default
            return data[field]

        ensure_field(call_detail, 'billsec', 0)
        ensure_field(call_detail, 'billsec_formatted', f"{call_detail.get('billsec', 0)}s")
        ensure_field(call_detail, 'duration_formatted', f"{call_detail.get('duration', 0)}s")
        ensure_field(call_detail, 'disposition_uz', call_detail.get('disposition', 'Noma\'lum'))
        ensure_field(call_detail, 'call_direction_uz', 'Noma\'lum')
        ensure_field(call_detail, 'caller_name', call_detail.get('src', ''))
        ensure_field(call_detail, 'recording_file', '')
        ensure_field(call_detail, 'context', '')
        ensure_field(call_detail, 'dst_channel', '')
        ensure_field(call_detail, 'raw_data', {})

        context['call'] = call_detail

    except Exception as e:
        logger.error(f"Client call detail error: {str(e)}")
        messages.error(request, f'Qo\'ng\'iroq ma\'lumotini olishda xatolik: {str(e)}')

        # Fallback
        context['call'] = {
            'id': call_id,
            'error': True,
            'error_message': str(e)
        }

    return render(request, 'dashboards/client/call_detail.html', context)


@login_required
def client_calls_statistics_ajax(request):
    """Client uchun qo'ng'iroq statistikasi AJAX"""
    if request.user.role != 'client':
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    client_profile = request.user.client_profile
    if not client_profile:
        return JsonResponse({'success': False, 'error': 'Client profile not found'}, status=404)

    try:
        period = request.GET.get('period', 'today')
        operator_id = request.GET.get('operator_id', '')

        # Client operatorlari
        operator_ids = list(client_profile.operators.values_list('operator_id', flat=True))

        if not operator_ids:
            return JsonResponse({
                'success': True,
                'statistics': {
                    'total_calls': 0,
                    'answered_calls': 0,
                    'missed_calls': 0,
                    'answer_rate': 0
                },
                'total_calls': 0
            })

        # Davrni aniqlash
        if period == 'today':
            start_date = timezone.now().strftime('%Y-%m-%d')
            end_date = start_date
        elif period == 'week':
            start_date = (timezone.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            end_date = timezone.now().strftime('%Y-%m-%d')
        elif period == 'month':
            start_date = (timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            end_date = timezone.now().strftime('%Y-%m-%d')
        else:
            start_date = timezone.now().strftime('%Y-%m-%d')
            end_date = start_date

        # Ma'lumotlarni olish
        cdr_response = pbx_service.get_cdr_data(start_date=start_date, end_date=end_date)
        calls_data = pbx_service.process_cdr_data(cdr_response)

        if not calls_data['success']:
            raise Exception('CDR data not available')

        all_calls = calls_data['calls']

        # Client qo'ng'iroqlarini filterlash
        client_calls = []
        for call in all_calls:
            src = call.get('src', '')
            dst = call.get('dst', '')

            if src in operator_ids or dst in operator_ids:
                # Agar specific operator tanlangan bo'lsa
                if operator_id and src != operator_id and dst != operator_id:
                    continue
                client_calls.append(call)

        # Statistikani hisoblash
        statistics = pbx_service._calculate_call_statistics(client_calls)

        return JsonResponse({
            'success': True,
            'statistics': statistics,
            'total_calls': len(client_calls)
        })

    except Exception as e:
        logger.error(f"Client statistics AJAX error: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def monitoring_dashboard_view(request, user, monitoring_profile):
    """Monitoring dashboard with client monitoring and system statistics"""
    context = {
        'title': 'Monitoring Dashboard',
        'user': user,
        'monitoring_profile': monitoring_profile,
    }

    try:
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        last_week = today - timedelta(days=7)

        # Barcha clientlar ro'yxati
        clients = ClientProfile.objects.select_related('user').prefetch_related('operators').all()

        # System wide statistics
        total_users = User.objects.count()
        total_clients = clients.count()
        total_operators = OperatorProfile.objects.count()
        active_clients = clients.filter(user__is_active=True, is_active_subscription=True).count()
        active_operators = OperatorProfile.objects.filter(user__is_active=True).count()

        # Har bir client uchun statistika hisoblash
        clients_with_stats = []

        for client in clients:
            # Client operatorlari
            operators = client.operators.all()
            operators_count = operators.count()
            active_operators_count = operators.filter(user__is_active=True).count()

            # Operatorlarning ID lari
            operator_ids = [op.operator_id for op in operators if op.operator_id]

            # Bugungi qo'ng'iroqlar statistikasi
            total_calls = 0
            answered_calls = 0
            success_rate = 0
            avg_duration = 0

            if operator_ids:
                try:
                    # PBX dan bugungi ma'lumotlarni olish
                    cdr_response = pbx_service.get_cdr_data(
                        start_date=today.strftime('%Y-%m-%d'),
                        end_date=today.strftime('%Y-%m-%d')
                    )
                    calls_data = pbx_service.process_cdr_data(cdr_response)

                    if calls_data['success']:
                        all_calls = calls_data['calls']

                        # Faqat client operatorlariga tegishli qo'ng'iroqlar
                        client_calls = [
                            call for call in all_calls
                            if call.get('src') in operator_ids or call.get('dst') in operator_ids
                        ]

                        total_calls = len(client_calls)
                        answered_calls = len([
                            call for call in client_calls
                            if call.get('disposition') == 'ANSWERED'
                        ])

                        if total_calls > 0:
                            success_rate = round((answered_calls / total_calls) * 100, 1)

                        # O'rtacha qo'ng'iroq davomiyligi
                        if answered_calls > 0:
                            total_duration = sum([
                                call.get('billsec', 0) for call in client_calls
                                if call.get('disposition') == 'ANSWERED'
                            ])
                            avg_duration = round(total_duration / answered_calls, 1)

                except Exception as e:
                    logger.warning(f"PBX ma'lumot olishda xatolik {client.company_name}: {str(e)}")

            # Obuna holati
            subscription_status = 'active'
            days_left = 0
            if client.subscription_end:
                days_left = (client.subscription_end - today).days
                if days_left <= 0:
                    subscription_status = 'expired'
                elif days_left <= 7:
                    subscription_status = 'warning'

            # Client ma'lumotlarini to'ldirish
            client_data = {
                'id': client.id,
                'company_name': client.company_name,
                'contact_person': client.contact_person,
                'phone': client.phone,
                'operators_count': operators_count,
                'active_operators': active_operators_count,
                'total_calls': total_calls,
                'answered_calls': answered_calls,
                'missed_calls': total_calls - answered_calls,
                'success_rate': success_rate,
                'avg_duration': avg_duration,
                'subscription_type': client.get_subscription_type_display() if client.subscription_type else 'Noma\'lum',
                'subscription_end': client.subscription_end,
                'subscription_status': subscription_status,
                'days_left': days_left,
                'is_active': client.user.is_active and client.is_active_subscription,
                'last_activity': client.user.last_login,
            }

            clients_with_stats.append(client_data)

        # Umumiy tizim statistikasi
        total_calls_today = sum([c['total_calls'] for c in clients_with_stats])
        total_answered_today = sum([c['answered_calls'] for c in clients_with_stats])
        total_missed_today = total_calls_today - total_answered_today

        overall_success_rate = 0
        if total_calls_today > 0:
            overall_success_rate = round((total_answered_today / total_calls_today) * 100, 1)

        # Kechagi ma'lumotlar (taqqoslash uchun)
        yesterday_stats = {
            'total_calls': 0,
            'answered_calls': 0,
            'success_rate': 0
        }

        try:
            yesterday_response = pbx_service.get_cdr_data(
                start_date=yesterday.strftime('%Y-%m-%d'),
                end_date=yesterday.strftime('%Y-%m-%d')
            )
            yesterday_data = pbx_service.process_cdr_data(yesterday_response)

            if yesterday_data['success']:
                # Barcha clientlarning operatorlari
                all_operator_ids = []
                for client in clients:
                    all_operator_ids.extend([
                        op.operator_id for op in client.operators.all() if op.operator_id
                    ])

                yesterday_calls = [
                    call for call in yesterday_data['calls']
                    if call.get('src') in all_operator_ids or call.get('dst') in all_operator_ids
                ]

                yesterday_stats['total_calls'] = len(yesterday_calls)
                yesterday_stats['answered_calls'] = len([
                    call for call in yesterday_calls
                    if call.get('disposition') == 'ANSWERED'
                ])

                if yesterday_stats['total_calls'] > 0:
                    yesterday_stats['success_rate'] = round(
                        (yesterday_stats['answered_calls'] / yesterday_stats['total_calls']) * 100, 1
                    )

        except Exception as e:
            logger.warning(f"Kechagi ma'lumotlar olishda xatolik: {str(e)}")

        # Growth calculations
        def calculate_growth(today_val, yesterday_val):
            if yesterday_val == 0:
                return 100 if today_val > 0 else 0
            return round(((today_val - yesterday_val) / yesterday_val) * 100, 1)

        # Obuna tugash ogohlantirishi
        expiring_soon = len([
            c for c in clients_with_stats
            if c['subscription_status'] in ['warning', 'expired']
        ])

        # Eng faol clientlar (top 5)
        top_clients = sorted(
            clients_with_stats,
            key=lambda x: x['total_calls'],
            reverse=True
        )[:5]

        # Recent activities (oxirgi faoliyatlar)
        recent_activities = []

        # Yangi ro'yxatdan o'tgan foydalanuvchilar
        new_users_today = User.objects.filter(date_joined__date=today)
        for user in new_users_today:
            recent_activities.append({
                'type': 'new_user',
                'user': user.get_full_name() or user.username,
                'role': user.get_role_display(),
                'time': user.date_joined,
                'description': f"Yangi {user.get_role_display().lower()} ro'yxatdan o'tdi"
            })

        # Obunasi tugagan clientlar
        expired_today = clients.filter(subscription_end=today)
        for client in expired_today:
            recent_activities.append({
                'type': 'subscription_expired',
                'user': client.company_name,
                'time': timezone.now(),
                'description': f"Obuna muddati tugadi"
            })

        # Vaqt bo'yicha tartibga solish
        recent_activities.sort(key=lambda x: x['time'], reverse=True)
        recent_activities = recent_activities[:10]

        context.update({
            'clients': clients_with_stats,
            'top_clients': top_clients,
            'recent_activities': recent_activities,

            'system_stats': {
                'total_users': total_users,
                'total_clients': total_clients,
                'total_operators': total_operators,
                'active_clients': active_clients,
                'inactive_clients': total_clients - active_clients,
                'active_operators': active_operators,
                'expiring_soon': expiring_soon,
            },

            'calls_stats': {
                'total_calls_today': total_calls_today,
                'answered_calls_today': total_answered_today,
                'missed_calls_today': total_missed_today,
                'success_rate_today': overall_success_rate,

                # Kechagi ma'lumotlar
                'total_calls_yesterday': yesterday_stats['total_calls'],
                'answered_calls_yesterday': yesterday_stats['answered_calls'],
                'success_rate_yesterday': yesterday_stats['success_rate'],

                # Growth indicators
                'calls_growth': calculate_growth(total_calls_today, yesterday_stats['total_calls']),
                'answered_growth': calculate_growth(total_answered_today, yesterday_stats['answered_calls']),
                'success_rate_growth': calculate_growth(overall_success_rate, yesterday_stats['success_rate']),
            },

            'date_info': {
                'today': today,
                'yesterday': yesterday,
                'last_week': last_week,
            }
        })

    except Exception as e:
        logger.error(f"Monitoring dashboard xatolik: {str(e)}")
        context['error'] = str(e)

        # Fallback ma'lumotlar
        context.update({
            'clients': [],
            'top_clients': [],
            'recent_activities': [],

            'system_stats': {
                'total_users': 0,
                'total_clients': 0,
                'total_operators': 0,
                'active_clients': 0,
                'inactive_clients': 0,
                'active_operators': 0,
                'expiring_soon': 0,
            },

            'calls_stats': {
                'total_calls_today': 0,
                'answered_calls_today': 0,
                'missed_calls_today': 0,
                'success_rate_today': 0,
                'total_calls_yesterday': 0,
                'answered_calls_yesterday': 0,
                'success_rate_yesterday': 0,
                'calls_growth': 0,
                'answered_growth': 0,
                'success_rate_growth': 0,
            },

            'date_info': {
                'today': timezone.now().date(),
                'yesterday': timezone.now().date() - timedelta(days=1),
                'last_week': timezone.now().date() - timedelta(days=7),
            }
        })

    return render(request, 'dashboards/monitoring/dashboard_monitoring.html', context)

@login_required
def client_detail_view(request, client_id):
    """Client tafsilotlari sahifasi"""
    client = get_object_or_404(ClientProfile, id=client_id)

    context = {
        'title': f'{client.company_name} - Tafsilotlar',
        'user': request.user,
        'client': client,
    }

    try:
        # Client operatorlari
        operators = client.operators.select_related('user').all()
        operator_ids = [op.operator_id for op in operators if op.operator_id]

        # Sana filterlari
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Bugungi, kechagi, haftalik ma'lumotlar
        stats_periods = {
            'today': today.strftime('%Y-%m-%d'),
            'yesterday': yesterday.strftime('%Y-%m-%d'),
            'week': week_ago.strftime('%Y-%m-%d'),
            'month': month_ago.strftime('%Y-%m-%d'),
        }

        all_stats = {}
        chart_data = {
            'daily': [],  # 7 kunlik ma'lumot
            'hourly': [],  # Bugungi soatlik ma'lumot
        }

        if operator_ids:
            try:
                # Bugungi ma'lumotlar
                today_response = pbx_service.get_cdr_data(
                    start_date=today.strftime('%Y-%m-%d'),
                    end_date=today.strftime('%Y-%m-%d')
                )
                today_data = pbx_service.process_cdr_data(today_response)

                if today_data['success']:
                    today_calls = [
                        call for call in today_data['calls']
                        if call.get('src') in operator_ids or call.get('dst') in operator_ids
                    ]
                    all_stats['today'] = pbx_service._calculate_call_statistics(today_calls)
                else:
                    all_stats['today'] = {}

                # Haftalik ma'lumotlar (chart uchun)
                for i in range(7):
                    date = today - timedelta(days=i)
                    date_str = date.strftime('%Y-%m-%d')

                    try:
                        daily_response = pbx_service.get_cdr_data(
                            start_date=date_str,
                            end_date=date_str
                        )
                        daily_data = pbx_service.process_cdr_data(daily_response)

                        if daily_data['success']:
                            daily_calls = [
                                call for call in daily_data['calls']
                                if call.get('src') in operator_ids or call.get('dst') in operator_ids
                            ]
                            daily_stats = pbx_service._calculate_call_statistics(daily_calls)

                            chart_data['daily'].append({
                                'date': date.strftime('%d.%m'),
                                'total_calls': daily_stats.get('total_calls', 0),
                                'answered_calls': daily_stats.get('answered_calls', 0),
                                'success_rate': daily_stats.get('answer_rate', 0),
                            })
                    except:
                        chart_data['daily'].append({
                            'date': date.strftime('%d.%m'),
                            'total_calls': 0,
                            'answered_calls': 0,
                            'success_rate': 0,
                        })

                # Chartlar uchun ma'lumotlarni teskari tartibda qo'yish
                chart_data['daily'].reverse()

                # Bugungi soatlik ma'lumotlar
                if today_data['success'] and 'by_hour' in all_stats.get('today', {}):
                    hourly_data = all_stats['today'].get('by_hour', {})
                    for hour in range(24):
                        chart_data['hourly'].append({
                            'hour': f"{hour:02d}:00",
                            'calls': hourly_data.get(hour, 0)
                        })

            except Exception as e:
                logger.error(f"Client {client_id} uchun PBX ma'lumot olishda xatolik: {str(e)}")
                all_stats['today'] = {}

        # Operator statistikalari
        operators_with_stats = []
        for operator in operators:
            op_stats = {
                'operator': operator,
                'today_calls': 0,
                'success_rate': 0,
                'status': 'active' if operator.user.is_active else 'inactive'
            }

            # Operator'ning bugungi qo'ng'iroqlari
            if operator.operator_id and today_data.get('success'):
                op_calls = [
                    call for call in today_data.get('calls', [])
                    if call.get('src') == operator.operator_id
                ]
                op_stats['today_calls'] = len(op_calls)

                if op_calls:
                    answered = len([c for c in op_calls if c.get('disposition') == 'ANSWERED'])
                    op_stats['success_rate'] = round((answered / len(op_calls)) * 100, 1)

            operators_with_stats.append(op_stats)

        # Recent calls (oxirgi 20 ta)
        recent_calls = []
        if operator_ids and today_data.get('success'):
            all_calls = [
                call for call in today_data.get('calls', [])
                if call.get('src') in operator_ids or call.get('dst') in operator_ids
            ]
            recent_calls = sorted(all_calls, key=lambda x: x.get('calldate', ''), reverse=True)[:20]

        context.update({
            'operators': operators_with_stats,
            'operators_count': len(operators),
            'active_operators': len([op for op in operators if op.user.is_active]),
            'stats': all_stats.get('today', {}),
            'chart_data': chart_data,
            'recent_calls': recent_calls,
            'today': today,
        })

    except Exception as e:
        logger.error(f"Client detail sahifasida xatolik: {str(e)}")
        context['error'] = str(e)

    return render(request, 'dashboards/monitoring/client_detail.html', context)


@login_required
def client_chart_data_api(request, client_id):
    """Client uchun chart ma'lumotlarini JSON formatda qaytarish"""
    client = get_object_or_404(ClientProfile, id=client_id)

    try:
        period = request.GET.get('period', 'week')  # week, month, day

        operator_ids = [op.operator_id for op in client.operators.all() if op.operator_id]

        if not operator_ids:
            return JsonResponse({'success': False, 'error': 'Operatorlar topilmadi'})

        chart_data = []

        if period == 'week':
            # 7 kunlik ma'lumot
            for i in range(7):
                date = timezone.now().date() - timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')

                try:
                    response = pbx_service.get_cdr_data(start_date=date_str, end_date=date_str)
                    data = pbx_service.process_cdr_data(response)

                    if data['success']:
                        calls = [
                            call for call in data['calls']
                            if call.get('src') in operator_ids or call.get('dst') in operator_ids
                        ]
                        stats = pbx_service._calculate_call_statistics(calls)

                        chart_data.append({
                            'date': date.strftime('%d.%m'),
                            'total': stats.get('total_calls', 0),
                            'answered': stats.get('answered_calls', 0),
                            'success_rate': stats.get('answer_rate', 0),
                        })
                except:
                    chart_data.append({
                        'date': date.strftime('%d.%m'),
                        'total': 0,
                        'answered': 0,
                        'success_rate': 0,
                    })

            chart_data.reverse()

        return JsonResponse({
            'success': True,
            'data': chart_data
        })

    except Exception as e:
        logger.error(f"Chart data API xatolik: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        })

