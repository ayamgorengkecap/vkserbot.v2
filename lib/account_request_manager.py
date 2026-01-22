#!/usr/bin/env python3
"""
Per-Account Request Manager with Proxy Rotation
"""

import requests
from typing import Optional
from enum import Enum

G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


class RequestState(Enum):
    READY = 0
    ABORTED = 1


class AccountRequestManager:
    """Request manager with domain fallback and proxy rotation"""

    NETWORK_ERRORS = (
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ProxyError,
        requests.exceptions.SSLError,
        requests.exceptions.ConnectionError,
    )
    
    PROXY_ERROR_STATUS_CODES = {403, 407, 429, 502, 503, 504}

    DOMAINS = ['https://vkserfing.ru', 'https://vkserfing.com']

    def __init__(self, account_name: str, session: requests.Session,
                 proxy_pool, current_proxy_ip: str, config: dict):
        self.account_name = account_name
        self.session = session
        self.proxy_pool = proxy_pool
        self.current_proxy_ip = current_proxy_ip
        self.config = config
        self.state = RequestState.READY
        self.current_domain_idx = 0
        self.proxy_rotation_count = 0
        self.max_proxy_rotations = 5

    def is_aborted(self) -> bool:
        return self.state == RequestState.ABORTED
    
    def _rotate_proxy(self) -> bool:
        """Rotate to new proxy on error"""
        if self.proxy_rotation_count >= self.max_proxy_rotations:
            print(f"{R}[{self.account_name}] Max proxy rotations ({self.max_proxy_rotations}) reached{W}")
            return False
        
        # Get all used IPs to exclude
        from automation_core import get_all_used_proxies
        exclude_ips = get_all_used_proxies()
        
        # Rotate proxy
        new_proxy = self.proxy_pool.rotate_proxy(
            self.account_name,
            self.current_proxy_ip,
            exclude_ips=exclude_ips,
            max_retries=2
        )
        
        if not new_proxy:
            return False
        
        # Update session with new proxy
        self.session.proxies.update({
            'http': new_proxy['proxy_url'],
            'https': new_proxy['proxy_url']
        })
        self.current_proxy_ip = new_proxy['ip']
        self.proxy_rotation_count += 1
        
        # Update config
        self.config['proxy'] = {
            'proxy_string': new_proxy['proxy_string'],
            'ip': new_proxy['ip'],
            'port': new_proxy['port'],
            'username': new_proxy['username'],
            'password': new_proxy['password']
        }
        
        print(f"{G}[{self.account_name}] ✓ Proxy rotated to {new_proxy['ip']}{W}")
        return True

    def request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """Make request with domain fallback and proxy rotation"""
        if self.state == RequestState.ABORTED:
            return None

        if 'timeout' not in kwargs:
            kwargs['timeout'] = (5, 15)

        domain = self.DOMAINS[self.current_domain_idx]
        url = f"{domain}{endpoint}"

        try:
            if method.upper() == 'GET':
                response = self.session.get(url, **kwargs)
            else:
                response = self.session.post(url, **kwargs)
            
            # Check for proxy-related status codes
            if response.status_code in self.PROXY_ERROR_STATUS_CODES:
                print(f"{Y}[{self.account_name}] HTTP {response.status_code} - proxy issue detected{W}")
                
                # Try to rotate proxy
                if self._rotate_proxy():
                    # Retry with new proxy
                    print(f"{C}[{self.account_name}] Retrying with new proxy...{W}")
                    if method.upper() == 'GET':
                        response = self.session.get(url, **kwargs)
                    else:
                        response = self.session.post(url, **kwargs)
            
            return response

        except self.NETWORK_ERRORS as e:
            error_type = type(e).__name__
            print(f"{Y}[{self.account_name}] {error_type} on {domain} (proxy={self.current_proxy_ip}){W}")

            # Try fallback domain first
            fallback_idx = (self.current_domain_idx + 1) % len(self.DOMAINS)
            fallback_domain = self.DOMAINS[fallback_idx]
            fallback_url = f"{fallback_domain}{endpoint}"

            print(f"{C}[{self.account_name}] Trying fallback {fallback_domain}...{W}")

            try:
                if method.upper() == 'GET':
                    response = self.session.get(fallback_url, **kwargs)
                else:
                    response = self.session.post(fallback_url, **kwargs)

                self.current_domain_idx = fallback_idx
                print(f"{G}[{self.account_name}] Fallback success{W}")
                return response

            except self.NETWORK_ERRORS as e2:
                # Both domains failed - try proxy rotation
                print(f"{Y}[{self.account_name}] Both domains failed - attempting proxy rotation...{W}")
                
                if self._rotate_proxy():
                    # Retry with new proxy on original domain
                    print(f"{C}[{self.account_name}] Retrying with new proxy...{W}")
                    try:
                        if method.upper() == 'GET':
                            response = self.session.get(url, **kwargs)
                        else:
                            response = self.session.post(url, **kwargs)
                        return response
                    except:
                        print(f"{R}[{self.account_name}] Request failed even after proxy rotation{W}")
                        return None
                else:
                    print(f"{R}[{self.account_name}] Proxy rotation failed - skipping request{W}")
                    return None
