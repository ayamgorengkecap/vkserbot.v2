#!/usr/bin/env python3
"""
Proxy Manager with Auto-Rotation and Free Proxy Fallback
Supports automatic proxy switching when connection fails
"""

import requests
import time
import random
import concurrent.futures
from typing import Dict, List, Optional, Tuple


G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


class ProxyManager:
    """
    Manages proxy rotation with automatic fallback to free proxies
    """


    def __init__(self, initial_proxy_string=None, max_retries=3, test_timeout=10, max_proxy_attempts=100):
        """
        Initialize proxy manager

        Args:
            initial_proxy_string: Initial proxy in format "host:port:user:pass"
            max_retries: Maximum retries per proxy before switching
            test_timeout: Timeout for proxy testing
            max_proxy_attempts: Maximum different proxies to try before giving up (default: 30)
        """

        self.WEBSHARE_API_KEYS = self._load_webshare_keys()
        self.WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"


    FREE_PROXY_SOURCES = [
        {
            'name': 'proxy-checker-api',
            'type': 'api',
            'url': 'https://api.proxy-checker.net/api/free-proxy-list/',
            'headers': {
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Origin': 'https://proxy-checker.net',
                'Referer': 'https://proxy-checker.net/'
            }
        },
        {
            'name': 'fresh-proxy-list',
            'urls': {
                'http': 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt',
                'https': 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/https.txt',
                'socks4': 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt',
                'socks5': 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt',
                'all': 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/proxylist.txt',
            }
        },
        {
            'name': 'proxifly',
            'urls': {
                'http': 'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt',
                'https': 'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt',
                'socks4': 'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt',
                'socks5': 'https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt',
            }
        },
        {
            'name': 'TheSpeedX',
            'urls': {
                'http': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
                'https': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt',
                'socks4': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt',
                'socks5': 'https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt',
            }
        }
    ]

    def __init__(self, initial_proxy_string=None, max_retries=3, test_timeout=10, max_proxy_attempts=100):
        """
        Initialize proxy manager

        Args:
            initial_proxy_string: Initial proxy in format "host:port:user:pass"
            max_retries: Maximum retries per proxy before switching
            test_timeout: Timeout for proxy testing
            max_proxy_attempts: Maximum different proxies to try before giving up (default: 30)
        """

        self.WEBSHARE_API_KEYS = self._load_webshare_keys()
        self.WEBSHARE_API_URL = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"

        self.current_proxy_string = initial_proxy_string
        self.current_proxy_dict = None
        self.max_retries = max_retries
        self.test_timeout = test_timeout
        self.retry_count = 0
        self.free_proxy_cache = []
        self.tested_proxies = set()
        self.working_proxies_backup = []
        self.max_proxy_attempts = max_proxy_attempts
        self.proxy_attempt_count = 0


        if initial_proxy_string:
            self.current_proxy_dict = self._parse_proxy(initial_proxy_string)
            self.proxy_attempt_count = 1

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


        print(f"{R}[ProxyMgr] Warning: Webshare API keys not configured in config/api_keys.json{W}")
        return []

    def _parse_proxy(self, proxy_string, protocol='http'):
        """
        Parse proxy string to dict format for requests

        Args:
            proxy_string: Format "host:port" or "host:port:user:pass" or "http://user:pass@host:port"
            protocol: Proxy protocol (http, socks4, socks5)
        """
        if not proxy_string or proxy_string.strip() == '':
            return None

        try:

            proxy_string = proxy_string.strip()


            for prefix in ['http://', 'https://', 'socks4://', 'socks5://']:
                if proxy_string.startswith(prefix):
                    proxy_string = proxy_string.replace(prefix, '', 1)
                    break


            if '@' in proxy_string:
                auth_part, host_part = proxy_string.split('@', 1)
                username, password = auth_part.split(':', 1)
                host, port = host_part.split(':', 1)

                if protocol in ['socks4', 'socks5']:
                    proxy_url = f"{protocol}://{username}:{password}@{host}:{port}"
                else:
                    proxy_url = f"http://{username}:{password}@{host}:{port}"
            else:

                parts = proxy_string.split(':')

                if len(parts) == 4:

                    host, port, username, password = parts
                    if protocol in ['socks4', 'socks5']:
                        proxy_url = f"{protocol}://{username}:{password}@{host}:{port}"
                    else:
                        proxy_url = f"http://{username}:{password}@{host}:{port}"
                elif len(parts) == 2:

                    host, port = parts
                    if protocol in ['socks4', 'socks5']:
                        proxy_url = f"{protocol}://{host}:{port}"
                    else:
                        proxy_url = f"http://{host}:{port}"
                else:
                    return None


            try:
                port_num = int(port)
                if port_num < 1 or port_num > 65535:
                    return None
            except:
                return None

            return {
                'http': proxy_url,
                'https': proxy_url,
                'host': host,
                'port': port,
                'protocol': protocol,
                'raw': proxy_string
            }
        except Exception as e:
            print(f"{R}[ProxyMgr] Error parsing proxy: {e}{W}")
            return None

    def _test_proxy(self, proxy_dict, timeout=None):
        """
        Test if proxy is working

        Args:
            proxy_dict: Proxy dictionary from _parse_proxy
            timeout: Test timeout (uses self.test_timeout if None)

        Returns:
            Tuple (success: bool, ip_info: dict or None)
        """
        if not proxy_dict:
            return False, None

        timeout = timeout or self.test_timeout


        test_urls = [
            'http://ip-api.com/json/',
            'https://api.ipify.org?format=json',
            'https://ipapi.co/json/',
        ]

        proxies = {
            'http': proxy_dict['http'],
            'https': proxy_dict['https']
        }

        for url in test_urls:
            try:
                resp = requests.get(url, proxies=proxies, timeout=timeout)
                if resp.status_code == 200:
                    data = resp.json()


                    ip = data.get('ip') or data.get('query')
                    country = data.get('country') or data.get('country_name') or 'Unknown'
                    city = data.get('city') or 'Unknown'

                    return True, {
                        'ip': ip,
                        'country': country,
                        'city': city,
                        'proxy': proxy_dict['raw']
                    }
            except (requests.exceptions.ProxyError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout,
                    requests.exceptions.SSLError):
                continue
            except Exception as e:
                continue

        return False, None

    def _fetch_from_api(self, api_config, protocol='http'):
        """
        Fetch proxies from JSON API (proxy-checker.net style)

        Args:
            api_config: API configuration dict
            protocol: Filter by protocol (http, socks4, socks5)

        Returns:
            List of proxy strings with protocol prefix (e.g., ["http://1.1.1.1:80", "socks4://2.2.2.2:1080"])
        """
        proxies = []

        try:
            headers = api_config.get('headers', {})
            resp = requests.get(api_config['url'], headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()


                for item in data:
                    proxy_protocol = item.get('protocol', 'http')
                    ip = item.get('ip')
                    port = item.get('port')

                    if not ip or not port:
                        continue


                    if protocol != 'all' and proxy_protocol != protocol:
                        continue


                    proxy_string = f"{proxy_protocol}://{ip}:{port}"
                    proxies.append(proxy_string)

                return proxies
            else:
                print(f"{Y}[ProxyMgr] ⚠ API returned HTTP {resp.status_code}{W}")
                return []

        except Exception as e:
            print(f"{Y}[ProxyMgr] ⚠ Failed to fetch from API: {e}{W}")
            return []

    def _replace_webshare_proxy(self, old_proxy_string):
        """
        Replace invalid proxy using Webshare API replace endpoint

        Args:
            old_proxy_string: Old proxy string to replace (format: "host:port:user:pass")

        Returns:
            New proxy string or None if failed
        """
        try:
            import random

            old_ip = old_proxy_string.split(':')[0]


            api_key = random.choice(self.WEBSHARE_API_KEYS)

            headers = {
                'Authorization': f'Token {api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }


            replace_url = "https://proxy.webshare.io/api/v2/proxy/replace/"
            payload = {
                "proxy_address": old_ip
            }

            print(f"{C}[ProxyMgr] Replacing invalid proxy {old_ip} via Webshare API...{W}")
            resp = requests.post(replace_url, headers=headers, json=payload, timeout=15)

            if resp.status_code == 200:
                data = resp.json()


                proxy_address = data.get('proxy_address')
                port = data.get('port')
                username = data.get('username')
                password = data.get('password')

                if proxy_address and port and username and password:
                    new_proxy_string = f"{proxy_address}:{port}:{username}:{password}"
                    print(f"{G}[ProxyMgr] ✓ Replaced with new proxy: {proxy_address}{W}")
                    return new_proxy_string
                else:
                    print(f"{R}[ProxyMgr] ✗ Invalid response format{W}")
                    return None
            else:
                print(f"{R}[ProxyMgr] ✗ Replace API returned HTTP {resp.status_code}{W}")
                return None

        except Exception as e:
            print(f"{R}[ProxyMgr] ✗ Failed to replace proxy: {e}{W}")
            return None

    def _fetch_webshare_proxies(self, limit=100):
        """
        Fetch proxies from Webshare API

        Args:
            limit: Maximum number of proxies to fetch

        Returns:
            List of proxy strings in format "host:port:username:password"
        """
        proxies = []

        try:
            import random

            api_key = random.choice(self.WEBSHARE_API_KEYS)

            headers = {
                'Authorization': f'Token {api_key}',
                'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'
            }

            print(f"{C}[ProxyMgr] Fetching proxies from Webshare API...{W}")
            resp = requests.get(self.WEBSHARE_API_URL, headers=headers, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])

                for item in results[:limit]:
                    proxy_address = item.get('proxy_address')
                    port = item.get('port')
                    username = item.get('username')
                    password = item.get('password')

                    if proxy_address and port and username and password:
                        proxy_string = f"{proxy_address}:{port}:{username}:{password}"
                        proxies.append(proxy_string)

                print(f"{G}[ProxyMgr] ✓ Fetched {len(proxies)} proxies from Webshare{W}")
                return proxies
            else:
                print(f"{R}[ProxyMgr] ✗ Webshare API returned HTTP {resp.status_code}{W}")
                return []

        except Exception as e:
            print(f"{R}[ProxyMgr] ✗ Failed to fetch from Webshare: {e}{W}")
            return []

    def _fetch_free_proxies(self, protocol='http', limit=1000):
        """
        Fetch free proxies from multiple sources (text-based + API)

        Args:
            protocol: Proxy protocol (http, https, socks4, socks5, all)
            limit: Maximum number of proxies to fetch

        Returns:
            List of proxy strings (may include protocol prefix from API)
        """
        all_proxies = []


        for source in self.FREE_PROXY_SOURCES:
            source_name = source['name']
            source_type = source.get('type', 'text')

            try:

                if source_type == 'api':
                    print(f"{Y}[ProxyMgr] Fetching {protocol.upper()} proxies from {source_name} API...{W}")
                    count_before = len(all_proxies)
                    api_proxies = self._fetch_from_api(source, protocol)
                    all_proxies.extend(api_proxies)
                    count_added = len(all_proxies) - count_before
                    print(f"{G}[ProxyMgr] ✓ Fetched {count_added} proxies from {source_name}{W}")
                    continue


                url = source['urls'].get(protocol)
                if not url:
                    continue

                print(f"{Y}[ProxyMgr] Fetching {protocol.upper()} proxies from {source_name}...{W}")
                resp = requests.get(url, timeout=15)

                if resp.status_code == 200:

                    lines = resp.text.strip().split('\n')

                    count_before = len(all_proxies)
                    for line in lines:
                        line = line.strip()
                        if line and ':' in line and not line.startswith('#'):
                            all_proxies.append(line)

                    count_added = len(all_proxies) - count_before
                    print(f"{G}[ProxyMgr] ✓ Fetched {count_added} proxies from {source_name}{W}")
                else:
                    print(f"{Y}[ProxyMgr] ⚠ {source_name} returned HTTP {resp.status_code}{W}")

            except Exception as e:
                print(f"{Y}[ProxyMgr] ⚠ Failed to fetch from {source_name}: {e}{W}")
                continue


        all_proxies = list(set(all_proxies))

        if all_proxies:
            source_count = len([s for s in self.FREE_PROXY_SOURCES if s.get('type') == 'api' or s.get('urls', {}).get(protocol)])
            print(f"{G}[ProxyMgr] ✓ Total fetched: {len(all_proxies)} unique proxies (from {source_count} sources){W}")
        else:
            print(f"{R}[ProxyMgr] ✗ No proxies fetched from any source!{W}")


        return all_proxies[:limit]

    def _test_proxy_with_speed(self, proxy_string):
        """
        Test a single proxy and measure response time

        Returns:
            Tuple (success, proxy_dict, ip_info, response_time) or (False, None, None, 999)
        """

        if proxy_string in self.tested_proxies:
            return False, None, None, 999

        self.tested_proxies.add(proxy_string)


        protocol = 'http'
        if proxy_string.startswith('socks5://'):
            protocol = 'socks5'
        elif proxy_string.startswith('socks4://'):
            protocol = 'socks4'
        elif proxy_string.startswith('https://'):
            protocol = 'https'

        proxy_dict = self._parse_proxy(proxy_string, protocol=protocol)
        if not proxy_dict:
            return False, None, None, 999


        start_time = time.time()
        success, ip_info = self._test_proxy(proxy_dict, timeout=8)
        response_time = time.time() - start_time

        if success:
            return True, proxy_dict, ip_info, response_time
        else:
            return False, None, None, 999

    def _find_working_proxy(self, proxy_list, max_tests=1000, top_n=200, exclude_proxies=None):
        """
        Find the fastest working proxies from list using parallel testing

        Args:
            proxy_list: List of proxy strings
            max_tests: Maximum proxies to test in parallel (default: 1000 = test all)
            top_n: Number of fastest proxies to save (default: 200)
            exclude_proxies: Set of proxy strings to exclude (already used by other accounts)

        Returns:
            Tuple (proxy_dict, ip_info) or (None, None)
        """
        if not proxy_list:
            return None, None


        if exclude_proxies:
            original_count = len(proxy_list)

            filtered_list = []
            for proxy in proxy_list:
                try:

                    proxy_ip = proxy.split(':')[0]
                    if proxy_ip not in exclude_proxies:
                        filtered_list.append(proxy)
                except:

                    filtered_list.append(proxy)

            proxy_list = filtered_list
            excluded_count = original_count - len(proxy_list)
            if excluded_count > 0:
                print(f"{Y}[ProxyMgr] Filtered {excluded_count} already-used proxy IPs{W}")


        random.shuffle(proxy_list)


        test_list = proxy_list[:max_tests]

        print(f"{C}[ProxyMgr] Testing {len(test_list)} proxies in parallel (finding top {top_n} fastest)...{W}")


        working_proxies = []
        total_tests = len(test_list)
        completed = 0
        failed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:

            future_to_proxy = {
                executor.submit(self._test_proxy_with_speed, proxy): proxy
                for proxy in test_list
            }


            try:
                for future in concurrent.futures.as_completed(future_to_proxy, timeout=20):
                    try:
                        success, proxy_dict, ip_info, response_time = future.result()
                        completed += 1

                        if success:
                            working_proxies.append((proxy_dict, ip_info, response_time))
                            print(f"{G}✓{W}", end='', flush=True)
                        else:
                            failed += 1
                            print(f"{R}✗{W}", end='', flush=True)


                        if completed % 50 == 0:
                            progress_pct = (completed / total_tests) * 100
                            working_count = len(working_proxies)
                            print(f" {C}[{completed}/{total_tests} = {progress_pct:.0f}% | ✓{working_count} ✗{failed}]{W}", end='', flush=True)

                    except Exception as e:
                        completed += 1
                        failed += 1
                        print(f"{R}✗{W}", end='', flush=True)
            except concurrent.futures.TimeoutError:

                print(f"{Y}⏱{W}", end='', flush=True)


        progress_pct = (completed / total_tests) * 100
        working_count = len(working_proxies)
        print(f" {G}[{completed}/{total_tests} = {progress_pct:.0f}% | ✓{working_count} ✗{failed}]{W}")

        if working_proxies:

            working_proxies.sort(key=lambda x: x[2])

            print(f"{G}[ProxyMgr] Found {len(working_proxies)} working proxies{W}")


            top_fastest = working_proxies[:min(top_n, len(working_proxies))]


            self.working_proxies_backup = top_fastest


            best_proxy, best_info, best_time = top_fastest[0]

            print(f"{G}[ProxyMgr] Saved top {len(self.working_proxies_backup)} fastest proxies for testing{W}")
            print(f"{G}[ProxyMgr] Fastest: {best_info['ip']} ({best_info['country']}) - {best_time:.2f}s{W}")

            return best_proxy, best_info
        else:
            print(f"{R}[ProxyMgr] No working proxies found{W}")
            return None, None

    def get_proxy(self):
        """
        Get current working proxy

        Returns:
            Dict with proxy config for requests or None for direct connection
        """
        return self.current_proxy_dict

    def test_current_proxy(self):
        """
        Test if current proxy is working

        Returns:
            Tuple (success: bool, ip_info: dict or None)
        """
        if not self.current_proxy_dict:
            return False, None

        return self._test_proxy(self.current_proxy_dict)

    def rotate_proxy(self, use_free_proxy=False, protocol='http', allow_direct=False, exclude_proxies=None, use_webshare=True):
        """
        Rotate to a new working proxy - WEBSHARE ONLY, NO FREE PROXIES

        Args:
            use_free_proxy: IGNORED - free proxies are disabled
            protocol: Proxy protocol
            allow_direct: Allow fallback to direct connection if all proxies fail
            exclude_proxies: Set of proxy strings to exclude (already used by other accounts)
            use_webshare: Always True - only Webshare proxies are used

        Returns:
            Tuple (success: bool, ip_info: dict or None)
        """

        if self.proxy_attempt_count >= self.max_proxy_attempts:
            print(f"{R}[ProxyMgr] ✗ Max proxy attempts reached ({self.proxy_attempt_count}/{self.max_proxy_attempts}){W}")
            if allow_direct:
                print(f"{Y}[ProxyMgr] → Falling back to direct connection{W}")
                self.current_proxy_dict = None
                self.current_proxy_string = None
                return False, None
            else:
                print(f"{R}[ProxyMgr] ✗ Account will be SKIPPED{W}")
                return False, None

        print(f"{Y}[ProxyMgr] ⚠️  Rotating proxy... (attempt {self.proxy_attempt_count + 1}/{self.max_proxy_attempts}){W}")


        if self.working_proxies_backup and len(self.working_proxies_backup) > 0:
            if exclude_proxies:
                self.working_proxies_backup = [
                    (proxy, info, time) for proxy, info, time in self.working_proxies_backup
                    if info.get('ip') not in exclude_proxies
                ]

            if self.working_proxies_backup:
                next_proxy, next_info, next_time = self.working_proxies_backup.pop(0)
                self.current_proxy_dict = next_proxy
                self.current_proxy_string = next_proxy['raw']
                self.retry_count = 0
                self.proxy_attempt_count += 1
                print(f"{G}[ProxyMgr] ✓ Using backup proxy: {next_info['ip']} ({next_info['country']}){W}")
                return True, next_info


        print(f"{C}[ProxyMgr] Fetching proxies from Webshare API...{W}")
        webshare_proxies = self._fetch_webshare_proxies(limit=100)

        if webshare_proxies:
            proxy_dict, ip_info = self._find_working_proxy(
                webshare_proxies,
                max_tests=100,
                top_n=50,
                exclude_proxies=exclude_proxies
            )

            if proxy_dict:
                self.current_proxy_dict = proxy_dict
                self.current_proxy_string = proxy_dict['raw']
                self.retry_count = 0
                self.proxy_attempt_count += 1
                print(f"{G}[ProxyMgr] ✓ Switched to Webshare proxy: {ip_info['ip']} ({ip_info['country']}){W}")
                return True, ip_info


        print(f"{R}[ProxyMgr] ✗ Failed to get working proxy from Webshare{W}")

        if allow_direct:
            print(f"{Y}[ProxyMgr] → Falling back to direct connection{W}")
            self.current_proxy_dict = None
            self.current_proxy_string = None
            return False, None
        else:
            print(f"{R}[ProxyMgr] ✗ Account will be SKIPPED (no direct connection allowed){W}")
            return False, None

    def handle_proxy_error(self, error_msg="", allow_direct=False, use_webshare=True):
        """
        Handle proxy error and decide whether to rotate

        Args:
            error_msg: Error message for logging
            allow_direct: Allow fallback to direct connection if all proxies fail
            use_webshare: Use Webshare API (always True, free proxies disabled)

        Returns:
            Tuple (should_retry: bool, new_proxy_info: dict or None)
        """
        self.retry_count += 1

        print(f"{Y}[ProxyMgr] ⚠️  Rotating proxy... (attempt {self.retry_count}/{self.max_proxy_attempts}){W}")


        success, ip_info = self.rotate_proxy(
            use_free_proxy=False,
            allow_direct=allow_direct,
            use_webshare=True
        )

        if success:
            return True, ip_info
        else:
            if allow_direct:
                return True, None
            else:
                print(f"{R}[ProxyMgr] ✗ All proxies failed and direct connection not allowed{W}")
                print(f"{R}[ProxyMgr] ✗ Account will be SKIPPED{W}")
                return False, None

    def reset_retry_count(self):
        """Reset retry counter after successful operation"""
        self.retry_count = 0

    def get_proxy_info(self):
        """
        Get current proxy information

        Returns:
            Dict with proxy info or None
        """
        if not self.current_proxy_dict:
            return None


        success, ip_info = self._test_proxy(self.current_proxy_dict, timeout=5)

        if success:
            return ip_info
        else:
            return {
                'proxy': self.current_proxy_string,
                'status': 'Unknown (test failed)',
                'ip': 'Unknown',
                'country': 'Unknown'
            }

    def auto_discover_proxy(self, exclude_proxies=None, protocol='http'):
        """
        Auto-discover a working proxy from free proxy list

        Args:
            exclude_proxies: Set of proxy strings to exclude (already used by other accounts)
            protocol: Proxy protocol to use

        Returns:
            Tuple (success: bool, proxy_dict: dict or None, ip_info: dict or None)
        """
        print(f"{C}[ProxyMgr] 🔍 Auto-discovering working proxy...{W}")
        print(f"{C}[ProxyMgr] Fetching up to 1000 proxies and testing for top 200 fastest...{W}")


        self.free_proxy_cache = self._fetch_free_proxies(protocol, limit=1000)

        if not self.free_proxy_cache:
            print(f"{R}[ProxyMgr] ✗ Failed to fetch free proxies{W}")
            return False, None, None


        proxy_dict, ip_info = self._find_working_proxy(
            self.free_proxy_cache,
            max_tests=1000,
            top_n=200,
            exclude_proxies=exclude_proxies
        )

        if proxy_dict and ip_info:

            self.current_proxy_dict = proxy_dict
            self.current_proxy_string = proxy_dict['raw']
            self.retry_count = 0
            self.proxy_attempt_count = 1

            print(f"{G}[ProxyMgr] ✓ Auto-discovered proxy: {ip_info['ip']} ({ip_info['country']}, {ip_info['city']}){W}")
            return True, proxy_dict, ip_info
        else:
            print(f"{R}[ProxyMgr] ✗ No working proxy found after testing{W}")
            return False, None, None


def demo():
    """Demo proxy manager usage"""
    print(f"{C}=== Proxy Manager Demo ==={W}\n")


    manager = ProxyManager(initial_proxy_string="1.2.3.4:8080:user:pass", max_retries=2)

    print(f"Initial proxy: {manager.current_proxy_string}")
    print(f"\nTesting initial proxy...")

    success, info = manager.test_current_proxy()
    if not success:
        print(f"{R}Initial proxy failed!{W}")
        print(f"\nTrying to rotate to free proxy...")

        success, info = manager.rotate_proxy(use_free_proxy=True, protocol='http')

        if success:
            print(f"\n{G}Success! New proxy info:{W}")
            print(f"  IP: {info['ip']}")
            print(f"  Country: {info['country']}")
            print(f"  City: {info['city']}")
        else:
            print(f"\n{Y}Using direct connection{W}")

    print(f"\n{C}=== Demo Complete ==={W}")


if __name__ == '__main__':
    demo()
