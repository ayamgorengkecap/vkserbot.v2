#!/usr/bin/env python3
"""
Smart Proxy Manager - Webshare Only with Error-Based Rotation
- 1 account = 1 proxy (sticky)
- Rotate ONLY on consecutive errors
- No free proxies
"""

import requests
import time
from typing import Optional, Tuple, Dict, List

G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


class SmartProxyManager:
    """
    Proxy manager with intelligent error-based rotation.
    - Tracks consecutive errors per proxy
    - Rotates only when threshold reached
    - Webshare API only (no free proxies)
    """

    def __init__(
        self,
        account_name: str,
        initial_proxy: Optional[str] = None,
        error_threshold: int = 3,
        max_rotations: int = 10,
        exclude_ips: Optional[set] = None
    ):

        self.WEBSHARE_API_KEYS = self._load_webshare_keys()
        self.WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"

        self.WEBSHARE_API_KEYS = self._load_webshare_keys()
        self.WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"


        self.ROTATION_ERRORS = (
            requests.exceptions.ReadTimeout,
            requests.exceptions.ConnectTimeout,
            requests.exceptions.ProxyError,
            requests.exceptions.SSLError,
            requests.exceptions.ConnectionError,
        )


        self.ROTATION_STATUS_CODES = {403, 407, 429, 500, 502, 503, 504}

        self.account_name = account_name
        self.error_threshold = error_threshold
        self.max_rotations = max_rotations
        self.exclude_ips = exclude_ips or set()


        self.consecutive_errors = 0
        self.rotation_count = 0
        self.current_proxy_string = initial_proxy
        self.current_proxy_dict = None
        self.current_ip = None
        self.webshare_pool: List[str] = []
        self.pool_index = 0


        if initial_proxy:
            self.current_proxy_dict = self._parse_proxy(initial_proxy)
            self.current_ip = self._extract_ip(initial_proxy)

    def _load_webshare_keys(self):
        """Load Webshare API keys from config file"""
        import os
        import json

        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'api_keys.json')
        try:
            with open(config_path) as f:
                config = json.load(f)
                keys = config.get('webshare', {}).get('api_keys', [])
                if keys and keys[0] != 'YOUR_WEBSHARE_API_KEY_1':
                    return keys
        except:
            pass


        print(f"{R}[SmartProxyMgr] Warning: Webshare API keys not configured in config/api_keys.json{W}")
        return []

    def _parse_proxy(self, proxy_string: str) -> Optional[Dict]:
        """Parse proxy string to requests format"""
        if not proxy_string:
            return None
        try:
            proxy_string = proxy_string.strip()

            if proxy_string.startswith(('http://', 'https://')):
                proxy_url = proxy_string if proxy_string.startswith('http://') else proxy_string.replace('https://', 'http://')
            elif '@' in proxy_string:
                proxy_url = f"http://{proxy_string}"
            else:
                parts = proxy_string.split(':')
                if len(parts) == 4:
                    host, port, user, pwd = parts
                    proxy_url = f"http://{user}:{pwd}@{host}:{port}"
                elif len(parts) == 2:
                    proxy_url = f"http://{proxy_string}"
                else:
                    return None

            return {'http': proxy_url, 'https': proxy_url, 'raw': proxy_string}
        except:
            return None

    def _extract_ip(self, proxy_string: str) -> Optional[str]:
        """Extract IP from proxy string"""
        if not proxy_string:
            return None
        try:
            if '@' in proxy_string:
                return proxy_string.split('@')[1].split(':')[0]
            parts = proxy_string.split(':')
            return parts[0].replace('http://', '').replace('https://', '')
        except:
            return None

    def get_proxy(self) -> Optional[Dict]:
        """Get current proxy dict for requests"""
        return self.current_proxy_dict

    def get_proxy_info(self) -> Dict:
        """Get current proxy info"""
        return {
            'ip': self.current_ip or 'None',
            'proxy_string': self.current_proxy_string,
            'consecutive_errors': self.consecutive_errors,
            'rotation_count': self.rotation_count
        }

    def mark_success(self):
        """Mark successful request - reset error counter"""
        if self.consecutive_errors > 0:
            self.consecutive_errors = 0

    def mark_error(self, error: Exception = None, status_code: int = None) -> bool:
        """
        Mark failed request. Returns True if rotation was triggered.
        """

        should_count = False
        reason = ""

        if error and isinstance(error, self.ROTATION_ERRORS):
            should_count = True
            reason = type(error).__name__
        elif status_code and status_code in self.ROTATION_STATUS_CODES:
            should_count = True
            reason = f"HTTP {status_code}"

        if not should_count:
            return False

        self.consecutive_errors += 1
        old_ip = self.current_ip or 'None'

        print(f"{Y}[{self.account_name}] Proxy error #{self.consecutive_errors}/{self.error_threshold}: {reason}{W}")


        if self.consecutive_errors >= self.error_threshold:
            return self.rotate_now(f"{self.consecutive_errors} consecutive errors ({reason})")

        return False

    def rotate_now(self, reason: str = "manual") -> bool:
        """
        Force rotation to new proxy.
        Returns True if successful, False if no more proxies.
        """
        if self.rotation_count >= self.max_rotations:
            print(f"{R}[{self.account_name}] Max rotations ({self.max_rotations}) reached - giving up{W}")
            return False

        old_ip = self.current_ip or 'None'


        new_proxy = self._get_next_proxy()

        if not new_proxy:

            if not self._fetch_webshare_pool():
                print(f"{R}[{self.account_name}] Failed to fetch Webshare proxies{W}")
                return False
            new_proxy = self._get_next_proxy()

        if not new_proxy:
            print(f"{R}[{self.account_name}] No available proxies{W}")
            return False


        self.current_proxy_string = new_proxy
        self.current_proxy_dict = self._parse_proxy(new_proxy)
        self.current_ip = self._extract_ip(new_proxy)
        self.consecutive_errors = 0
        self.rotation_count += 1

        print(f"{G}[{self.account_name}] Proxy rotated: {old_ip} → {self.current_ip} (reason: {reason}){W}")

        return True

    def _get_next_proxy(self) -> Optional[str]:
        """Get next proxy from pool, excluding used IPs"""
        while self.pool_index < len(self.webshare_pool):
            proxy = self.webshare_pool[self.pool_index]
            self.pool_index += 1

            ip = self._extract_ip(proxy)
            if ip and ip not in self.exclude_ips and ip != self.current_ip:
                return proxy

        return None

    def _fetch_webshare_pool(self) -> bool:
        """Fetch fresh proxies from Webshare API"""
        import random

        try:
            api_key = random.choice(self.WEBSHARE_API_KEYS)
            headers = {'Authorization': f'Token {api_key}'}

            print(f"{C}[{self.account_name}] Fetching Webshare proxies...{W}")
            resp = requests.get(self.WEBSHARE_API_URL, headers=headers, timeout=15)

            if resp.status_code != 200:
                print(f"{R}[{self.account_name}] Webshare API error: HTTP {resp.status_code}{W}")
                return False

            data = resp.json()
            results = data.get('results', [])

            self.webshare_pool = []
            for item in results:
                addr = item.get('proxy_address')
                port = item.get('port')
                user = item.get('username')
                pwd = item.get('password')
                if addr and port and user and pwd:
                    self.webshare_pool.append(f"{addr}:{port}:{user}:{pwd}")

            self.pool_index = 0
            print(f"{G}[{self.account_name}] Fetched {len(self.webshare_pool)} proxies{W}")
            return len(self.webshare_pool) > 0

        except Exception as e:
            print(f"{R}[{self.account_name}] Webshare fetch error: {e}{W}")
            return False

    def test_proxy(self, timeout: int = 10) -> Tuple[bool, Optional[Dict]]:
        """Test current proxy connectivity"""
        if not self.current_proxy_dict:
            return False, None

        try:
            resp = requests.get(
                'http://ip-api.com/json/',
                proxies=self.current_proxy_dict,
                timeout=timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return True, {
                    'ip': data.get('query'),
                    'country': data.get('country'),
                    'city': data.get('city')
                }
        except:
            pass
        return False, None

    def ensure_working_proxy(self) -> bool:
        """Ensure we have a working proxy, rotate if needed"""
        if not self.current_proxy_dict:
            return self.rotate_now("no proxy configured")

        success, _ = self.test_proxy(timeout=5)
        if success:
            return True

        return self.rotate_now("proxy test failed")
