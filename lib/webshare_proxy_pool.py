#!/usr/bin/env python3
"""
Unified Webshare Proxy Manager - Production Grade
- Pools from ALL API keys
- Deduplicates IPs globally
- Parallel testing & speed sorting
- NO free proxies
- Immediate rotation on errors
"""

import requests
import time
import threading
import concurrent.futures
from typing import Dict, List, Optional, Tuple, Set

G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


class WebshareProxyPool:
    """
    Global proxy pool manager - fetches from ALL Webshare API keys
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, api_keys: List[str] = None):
        """Singleton pattern - one pool for entire application"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, api_keys: List[str] = None):
        if self._initialized:
            return
        
        self.api_keys = api_keys or self._load_api_keys()
        self.global_used_ips: Set[str] = set()
        self.pool_lock = threading.Lock()
        self._initialized = True
        
        print(f"{G}[ProxyPool] Initialized with {len(self.api_keys)} Webshare API keys{W}")
    
    def reload_api_keys(self):
        """Force reload API keys from config (for runtime updates)"""
        new_keys = self._load_api_keys()
        if new_keys and new_keys != self.api_keys:
            self.api_keys = new_keys
            print(f"{G}[ProxyPool] ✓ Reloaded {len(self.api_keys)} API keys{W}")
            return True
        return False
    
    def _load_api_keys(self) -> List[str]:
        """Load API keys from config"""
        import os
        import json
        
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'api_keys.json')
        try:
            with open(config_path) as f:
                config = json.load(f)
                keys = config.get('webshare', {}).get('api_keys', [])
                if keys and keys[0] != 'YOUR_WEBSHARE_API_KEY_1':
                    return keys
        except Exception as e:
            print(f"{R}[ProxyPool] Failed to load API keys: {e}{W}")
        
        return []
    
    def fetch_all_proxies(self, exclude_ips: Set[str] = None) -> List[Dict]:
        """
        Fetch from ALL API keys and merge with deduplication
        
        Returns:
            List of unique proxy dicts with format:
            {
                'ip': str,
                'port': int,
                'username': str,
                'password': str,
                'proxy_string': str,
                'proxy_url': str
            }
        """
        # Auto-reload API keys setiap fetch (untuk detect config changes)
        self.reload_api_keys()
        
        # Clear global used IPs if too many (allow reuse after threshold)
        with self.pool_lock:
            if len(self.global_used_ips) > 20:  # Lower threshold for more reuse
                print(f"{Y}[ProxyPool] Clearing {len(self.global_used_ips)} used IPs (allow reuse){W}")
                self.global_used_ips.clear()
        
        exclude_ips = exclude_ips or set()
        all_proxies = []
        
        print(f"{C}[ProxyPool] Fetching from {len(self.api_keys)} API keys...{W}")
        
        # Fetch from each API key
        for idx, api_key in enumerate(self.api_keys, 1):
            try:
                proxies = self._fetch_from_single_key(api_key, limit=100)
                all_proxies.extend(proxies)
                print(f"{G}[ProxyPool] ✓ Key {idx}/{len(self.api_keys)}: {len(proxies)} proxies{W}")
            except Exception as e:
                print(f"{R}[ProxyPool] ✗ Key {idx}/{len(self.api_keys)} failed: {str(e)[:60]}{W}")
                continue
        
        if not all_proxies:
            print(f"{R}[ProxyPool] ✗ No proxies fetched from any API key{W}")
            return []
        
        # Deduplicate by IP
        seen_ips = set()
        unique_proxies = []
        
        for proxy in all_proxies:
            ip = proxy['ip']
            
            # Skip if already seen in this batch
            if ip in seen_ips:
                continue
            
            # Skip if already used globally or in exclude list
            with self.pool_lock:
                if ip in self.global_used_ips or ip in exclude_ips:
                    continue
            
            seen_ips.add(ip)
            unique_proxies.append(proxy)
        
        print(f"{G}[ProxyPool] ✓ Deduplicated: {len(all_proxies)} → {len(unique_proxies)} unique{W}")
        return unique_proxies
    
    def _fetch_from_single_key(self, api_key: str, limit: int = 100) -> List[Dict]:
        """Fetch proxies from single Webshare API key"""
        url = f"https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size={limit}"
        headers = {'Authorization': f'Token {api_key}'}
        
        resp = requests.get(url, headers=headers, timeout=15)
        
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}")
        
        data = resp.json()
        proxies = []
        
        for item in data.get('results', []):
            ip = item.get('proxy_address')
            port = item.get('port')
            username = item.get('username')
            password = item.get('password')
            
            if not all([ip, port, username, password]):
                continue
            
            proxy_url = f"http://{username}:{password}@{ip}:{port}"
            
            proxies.append({
                'ip': ip,
                'port': port,
                'username': username,
                'password': password,
                'proxy_string': f"{ip}:{port}:{username}:{password}",
                'proxy_url': proxy_url
            })
        
        return proxies
    
    def validate_and_select_best(self, proxies: List[Dict], max_tests: int = 50) -> Optional[Dict]:
        """
        Test proxies in parallel and return fastest working one
        
        Returns:
            Best proxy dict with added fields:
            {
                ...(original fields),
                'response_time': float,
                'ip_info': {
                    'ip': str,
                    'country': str,
                    'city': str
                }
            }
        """
        if not proxies:
            return None
        
        test_batch = proxies[:max_tests]
        working_proxies = []
        
        print(f"{C}[ProxyPool] Testing {len(test_batch)} proxies in parallel...{W}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_proxy = {
                executor.submit(self._test_proxy, proxy): proxy 
                for proxy in test_batch
            }
            
            for future in concurrent.futures.as_completed(future_to_proxy):
                proxy = future_to_proxy[future]
                try:
                    success, response_time, ip_info = future.result(timeout=15)
                    if success:
                        working_proxies.append({
                            **proxy,
                            'response_time': response_time,
                            'ip_info': ip_info
                        })
                        print(f"{G}[ProxyPool] ✓ {proxy['ip']}: {response_time:.2f}s{W}")
                except Exception as e:
                    continue
        
        if not working_proxies:
            print(f"{R}[ProxyPool] ✗ No working proxies found{W}")
            return None
        
        # Sort by response time (fastest first)
        working_proxies.sort(key=lambda x: x['response_time'])
        best_proxy = working_proxies[0]
        
        # Mark IP as used globally
        with self.pool_lock:
            self.global_used_ips.add(best_proxy['ip'])
        
        print(f"{G}[ProxyPool] ✓ Best proxy: {best_proxy['ip']} ({best_proxy['ip_info']['country']}) - {best_proxy['response_time']:.2f}s{W}")
        return best_proxy
    
    def _test_proxy(self, proxy: Dict) -> Tuple[bool, float, Dict]:
        """Test single proxy and measure response time"""
        proxies = {'http': proxy['proxy_url'], 'https': proxy['proxy_url']}
        
        start_time = time.time()
        try:
            resp = requests.get(
                'http://ip-api.com/json/',
                proxies=proxies,
                timeout=10
            )
            response_time = time.time() - start_time
            
            if resp.status_code == 200:
                data = resp.json()
                return True, response_time, {
                    'ip': data.get('query'),
                    'country': data.get('country', 'Unknown'),
                    'city': data.get('city', 'Unknown')
                }
        except:
            pass
        
        return False, 999.0, {}
    
    def get_proxy_for_account(self, account_name: str, exclude_ips: Set[str] = None) -> Optional[Dict]:
        """
        Get best working proxy for an account
        
        Args:
            account_name: Account identifier for logging
            exclude_ips: Set of IPs to exclude (already used by other accounts)
        
        Returns:
            Proxy dict or None if failed
        """
        print(f"{C}[{account_name}] Getting proxy from Webshare pool...{W}")
        
        # Fetch from ALL API keys
        proxies = self.fetch_all_proxies(exclude_ips=exclude_ips)
        
        if not proxies:
            print(f"{R}[{account_name}] ✗ No proxies available{W}")
            return None
        
        # Validate and select best
        best_proxy = self.validate_and_select_best(proxies, max_tests=50)
        
        if best_proxy:
            print(f"{G}[{account_name}] ✓ Proxy assigned: {best_proxy['ip']}{W}")
            return best_proxy
        else:
            print(f"{R}[{account_name}] ✗ No working proxies found{W}")
            return None
    
    def rotate_proxy(self, account_name: str, old_ip: str, exclude_ips: Set[str] = None, max_retries: int = 3) -> Optional[Dict]:
        """
        Rotate to new proxy (called on error)
        
        Args:
            account_name: Account identifier
            old_ip: Current proxy IP to exclude
            exclude_ips: Additional IPs to exclude
            max_retries: Max retry attempts if fetch fails
        
        Returns:
            New proxy dict or None
        """
        print(f"{Y}[{account_name}] Rotating proxy (old: {old_ip})...{W}")
        
        # Add old IP to exclusion list
        exclude_ips = exclude_ips or set()
        exclude_ips.add(old_ip)
        
        # Try to get new proxy with retries
        for attempt in range(max_retries):
            new_proxy = self.get_proxy_for_account(account_name, exclude_ips=exclude_ips)
            
            if new_proxy:
                return new_proxy
            
            if attempt < max_retries - 1:
                wait_time = 10 * (attempt + 1)
                print(f"{Y}[{account_name}] Retry {attempt+1}/{max_retries} in {wait_time}s...{W}")
                time.sleep(wait_time)
        
        print(f"{R}[{account_name}] ✗ Failed to rotate proxy after {max_retries} attempts{W}")
        return None
    
    def release_ip(self, ip: str):
        """Release IP back to pool (when account finishes)"""
        with self.pool_lock:
            self.global_used_ips.discard(ip)
    
    def get_stats(self) -> Dict:
        """Get pool statistics"""
        with self.pool_lock:
            return {
                'api_keys': len(self.api_keys),
                'used_ips': len(self.global_used_ips),
                'used_ips_list': list(self.global_used_ips)
            }


# Singleton instance
_proxy_pool_instance = None

def get_proxy_pool() -> WebshareProxyPool:
    """Get global proxy pool instance"""
    global _proxy_pool_instance
    if _proxy_pool_instance is None:
        _proxy_pool_instance = WebshareProxyPool()
    return _proxy_pool_instance
