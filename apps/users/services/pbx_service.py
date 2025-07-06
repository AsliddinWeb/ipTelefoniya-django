# apps/users/services/pbx_service.py
import requests
import json
import logging
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache
from typing import Optional, Dict, Any, List
import urllib3

# SSL warning o'chirish
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class PBXAPIService:
    """PBX API bilan ishlash uchun service class"""

    def __init__(self):
        self.base_url = getattr(settings, 'PBX_API_BASE_URL', 'https://185.203.236.211:27218/pbxapi')
        self.username = getattr(settings, 'PBX_API_USERNAME', 'apiuser')
        self.password = getattr(settings, 'PBX_API_PASSWORD', 'SqhAKnQUt9CV3yLp0Hgs10x')
        self.token_cache_key = 'pbx_api_access_token'
        self.refresh_token_cache_key = 'pbx_api_refresh_token'
        self.session = requests.Session()

        # SSL verification o'chirish
        self.session.verify = False

        # Default headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Django-PBX-Client/1.0'
        })

        # Timeout settings
        self.timeout = 30

    def test_connection(self) -> bool:
        """PBX server bilan bog'lanishni test qilish"""
        try:
            # Oddiy ping yoki status endpoint
            response = self.session.get(
                f"{self.base_url}/status/",
                timeout=10,
                verify=False
            )
            return response.status_code == 200
        except:
            return False

    def authenticate(self) -> Dict[str, Any]:
        """PBX API ga authenticate qilish"""
        url = f"{self.base_url}/authenticate/"

        # Debug: URL va ma'lumotlarni log qilish
        logger.info(f"Authenticating to: {url}")
        logger.info(f"Username: {self.username}")

        # Turli formatlarni sinab ko'rish
        payloads_to_try = [
            # Format 1: user/password
            {
                'user': self.username,
                'password': self.password
            },
            # Format 2: username/password
            {
                'username': self.username,
                'password': self.password
            },
            # Format 3: login/pass
            {
                'login': self.username,
                'pass': self.password
            }
        ]

        headers_to_try = [
            # Headers variant 1
            {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            # Headers variant 2 (Postman style)
            {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            }
        ]

        # Har bir kombinatsiyani sinash
        for i, payload in enumerate(payloads_to_try):
            for j, headers in enumerate(headers_to_try):
                try:
                    logger.info(f"Trying payload format {i + 1}, headers format {j + 1}")
                    logger.info(f"Payload: {payload}")

                    if headers.get('Content-Type') == 'application/json':
                        response = self.session.post(
                            url,
                            json=payload,
                            headers=headers,
                            timeout=self.timeout,
                            verify=False
                        )
                    else:
                        response = self.session.post(
                            url,
                            data=payload,
                            headers=headers,
                            timeout=self.timeout,
                            verify=False
                        )

                    logger.info(f"Response status: {response.status_code}")
                    logger.info(f"Response body: {response.text}")

                    if response.status_code == 200:
                        try:
                            data = response.json()
                            logger.info("Authentication successful!")

                            # Token'larni cache'ga saqlash
                            access_token = data.get('access_token') or data.get('token')
                            refresh_token = data.get('refresh_token')
                            expires_in = data.get('expires_in', 3600)

                            if access_token:
                                cache.set(self.token_cache_key, access_token, expires_in - 240)
                                logger.info("Access token successfully cached")

                            if refresh_token:
                                cache.set(self.refresh_token_cache_key, refresh_token, expires_in * 2)
                                logger.info("Refresh token successfully cached")

                            return data
                        except json.JSONDecodeError as e:
                            logger.error(f"Invalid JSON response: {response.text}")
                            continue

                    elif response.status_code == 403:
                        logger.error(f"403 Forbidden with payload {i + 1}, headers {j + 1}: {response.text}")
                        continue
                    else:
                        logger.error(f"Status {response.status_code}: {response.text}")
                        continue

                except requests.exceptions.RequestException as e:
                    logger.error(f"Request failed with payload {i + 1}, headers {j + 1}: {str(e)}")
                    continue

        # Agar hech qaysi format ishlamasa
        raise Exception(f"All authentication attempts failed. Please check credentials and API format.")

    def get_access_token(self) -> str:
        """Access token olish (cache'dan yoki yangi authenticate qilish)"""
        # Avval cache'dan tekshirish
        token = cache.get(self.token_cache_key)

        if token:
            logger.debug("Using cached access token")
            return token

        # Cache'da yo'q bo'lsa, authenticate qilish
        logger.info("No cached token found, authenticating...")
        try:
            auth_data = self.authenticate()
            return auth_data.get('access_token') or auth_data.get('token')
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise

    def make_authenticated_request(self, endpoint: str, method: str = 'GET',
                                   data: Optional[Dict] = None,
                                   params: Optional[Dict] = None,
                                   retry_count: int = 0) -> Dict[str, Any]:
        """Token bilan himoyalangan so'rov yuborish"""
        if retry_count >= 3:
            raise Exception("Maximum retry attempts reached")

        # Access token olish
        access_token = self.get_access_token()

        if not access_token:
            raise Exception("Unable to obtain access token")

        # Headers tayyorlash
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        # URL yaratish
        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        logger.info(f"Making {method} request to: {url}")

        try:
            # So'rov yuborish
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params, timeout=self.timeout, verify=False)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, json=data, params=params, timeout=self.timeout,
                                             verify=False)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            logger.info(f"Response status: {response.status_code}")
            logger.info(f"Response: {response.text}")

            # 401 (Unauthorized) bo'lsa token yangilash
            if response.status_code == 401:
                logger.warning("Access token expired, refreshing...")
                cache.delete(self.token_cache_key)
                return self.make_authenticated_request(endpoint, method, data, params, retry_count + 1)

            # Boshqa xatoliklar
            response.raise_for_status()

            # JSON response qaytarish
            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {str(e)}")
            if retry_count < 2:
                logger.info(f"Retrying request... (attempt {retry_count + 1})")
                return self.make_authenticated_request(endpoint, method, data, params, retry_count + 1)
            raise Exception(f"PBX API request failed: {str(e)}")

    def get_cdr_data(self, start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     limit: Optional[int] = None,
                     src: Optional[str] = None,
                     dst: Optional[str] = None) -> Dict[str, Any]:
        """CDR ma'lumotlarini olish"""
        params = {}

        if start_date:
            params['start_date'] = start_date
        if end_date:
            params['end_date'] = end_date
        if limit:
            params['limit'] = limit
        if src:
            params['src'] = src
        if dst:
            params['dst'] = dst

        return self.make_authenticated_request('cdr', params=params)

    def get_today_calls(self) -> Dict[str, Any]:
        """Bugungi qo'ng'iroqlar"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            cdr_response = self.get_cdr_data(start_date=today, end_date=today)
            return self.process_cdr_data(cdr_response)
        except Exception as e:
            logger.error(f"Failed to get today's calls: {str(e)}")
            # Fallback data
            return {
                'success': False,
                'error': str(e),
                'calls': [],
                'statistics': {
                    'total_calls': 0,
                    'answered_calls': 0,
                    'missed_calls': 0,
                    'answer_rate': 0,
                    'total_duration': 0,
                    'total_billsec': 0,
                }
            }

    def process_cdr_data(self, cdr_response: Dict[str, Any]) -> Dict[str, Any]:
        """CDR ma'lumotlarini qayta ishlash va statistika yaratish"""
        if cdr_response.get('status') != 'success':
            return {
                'success': False,
                'error': 'CDR data retrieval failed',
                'calls': [],
                'statistics': {}
            }

        calls = cdr_response.get('results', [])

        # Statistikalar hisoblash
        statistics = self._calculate_call_statistics(calls)

        # Ma'lumotlarni qayta formatlash
        formatted_calls = []
        for call in calls:
            formatted_call = self._format_call_record(call)
            formatted_calls.append(formatted_call)

        return {
            'success': True,
            'calls': formatted_calls,
            'statistics': statistics,
            'total_records': len(calls)
        }

    def _format_call_record(self, call: Dict[str, Any]) -> Dict[str, Any]:
        """Qo'ng'iroq rekordini formatlash"""
        try:
            # Vaqtni formatlash
            calldate = datetime.strptime(call.get('calldate', ''), '%Y-%m-%d %H:%M:%S')
            formatted_date = calldate.strftime('%d.%m.%Y %H:%M:%S')
            formatted_time = calldate.strftime('%H:%M:%S')
            formatted_date_only = calldate.strftime('%d.%m.%Y')
        except:
            formatted_date = call.get('calldate', '')
            formatted_time = ''
            formatted_date_only = ''

        # Duration ni formatlash
        duration = int(call.get('duration', 0))
        billsec = int(call.get('billsec', 0))

        def format_duration(seconds):
            if seconds < 60:
                return f"{seconds}s"
            elif seconds < 3600:
                minutes = seconds // 60
                secs = seconds % 60
                return f"{minutes}m {secs}s"
            else:
                hours = seconds // 3600
                minutes = (seconds % 3600) // 60
                secs = seconds % 60
                return f"{hours}h {minutes}m {secs}s"

        # Disposition ni uz tilida
        disposition_map = {
            'ANSWERED': 'Javob berildi',
            'NO ANSWER': 'Javob berilmadi',
            'BUSY': 'Band',
            'FAILED': 'Muvaffaqiyatsiz',
            'CONGESTION': 'Tarmoq yuklanishi'
        }

        # Call direction aniqlash
        src = call.get('src', '')
        dst = call.get('dst', '')

        call_direction = 'internal'  # default
        if src.startswith('0') or len(src) > 4:
            call_direction = 'incoming'
        elif dst.startswith('0') or len(dst) > 4:
            call_direction = 'outgoing'

        direction_map = {
            'incoming': 'Kiruvchi',
            'outgoing': 'Chiquvchi',
            'internal': 'Ichki'
        }

        return {
            'id': call.get('uniqueid', ''),
            'calldate': formatted_date,
            'time': formatted_time,
            'date': formatted_date_only,
            'caller_id': call.get('clid', ''),
            'caller_name': call.get('cnam', ''),
            'src': src,
            'dst': dst,
            'context': call.get('dcontext', ''),
            'channel': call.get('channel', ''),
            'dst_channel': call.get('dstchannel', ''),
            'duration': duration,
            'billsec': billsec,
            'duration_formatted': format_duration(duration),
            'billsec_formatted': format_duration(billsec),
            'disposition': call.get('disposition', ''),
            'disposition_uz': disposition_map.get(call.get('disposition', ''), call.get('disposition', '')),
            'recording_file': call.get('recordingfile', ''),
            'call_direction': call_direction,
            'call_direction_uz': direction_map.get(call_direction, ''),
            'is_answered': call.get('disposition') == 'ANSWERED',
            'raw_data': call  # Original ma'lumot
        }

    def _calculate_call_statistics(self, calls: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Qo'ng'iroq statistikalarini hisoblash"""
        if not calls:
            return {
                'total_calls': 0,
                'answered_calls': 0,
                'missed_calls': 0,
                'total_duration': 0,
                'total_billsec': 0,
                'answer_rate': 0,
                'by_direction': {},
                'by_hour': {},
                'top_callers': [],
                'top_destinations': []
            }

        total_calls = len(calls)
        answered_calls = sum(1 for call in calls if call.get('disposition') == 'ANSWERED')
        missed_calls = total_calls - answered_calls

        total_duration = sum(int(call.get('duration', 0)) for call in calls)
        total_billsec = sum(int(call.get('billsec', 0)) for call in calls)

        answer_rate = (answered_calls / total_calls * 100) if total_calls > 0 else 0

        # Yo'nalish bo'yicha statistika
        by_direction = {}
        for call in calls:
            src = call.get('src', '')
            dst = call.get('dst', '')

            if src.startswith('0') or len(src) > 4:
                direction = 'incoming'
            elif dst.startswith('0') or len(dst) > 4:
                direction = 'outgoing'
            else:
                direction = 'internal'

            by_direction[direction] = by_direction.get(direction, 0) + 1

        # Soat bo'yicha statistika
        by_hour = {}
        for call in calls:
            try:
                calldate = datetime.strptime(call.get('calldate', ''), '%Y-%m-%d %H:%M:%S')
                hour = calldate.hour
                by_hour[hour] = by_hour.get(hour, 0) + 1
            except:
                continue

        # Top callers va destinations
        caller_count = {}
        dest_count = {}

        for call in calls:
            src = call.get('src', '')
            dst = call.get('dst', '')

            if src:
                caller_count[src] = caller_count.get(src, 0) + 1
            if dst:
                dest_count[dst] = dest_count.get(dst, 0) + 1

        top_callers = sorted(caller_count.items(), key=lambda x: x[1], reverse=True)[:10]
        top_destinations = sorted(dest_count.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            'total_calls': total_calls,
            'answered_calls': answered_calls,
            'missed_calls': missed_calls,
            'total_duration': total_duration,
            'total_billsec': total_billsec,
            'total_duration_formatted': self._format_duration_stats(total_duration),
            'total_billsec_formatted': self._format_duration_stats(total_billsec),
            'answer_rate': round(answer_rate, 2),
            'by_direction': by_direction,
            'by_hour': dict(sorted(by_hour.items())),
            'top_callers': top_callers,
            'top_destinations': top_destinations
        }

    def _format_duration_stats(self, total_seconds: int) -> str:
        """Umumiy davomiylikni formatlash"""
        if total_seconds < 60:
            return f"{total_seconds} soniya"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            return f"{minutes} daqiqa {seconds} soniya"
        else:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            return f"{hours} soat {minutes} daqiqa"


# Singleton instance
pbx_service = PBXAPIService()