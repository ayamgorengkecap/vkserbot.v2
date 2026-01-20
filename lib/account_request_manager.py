#!/usr/bin/env python3
"""
Per-Account Request Manager - Simplified version based on working reference
"""

import requests
from typing import Optional
from smart_proxy_manager import SmartProxyManager
from enum import Enum

G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


class RequestState(Enum):
    READY = 0
    ABORTED = 1


class AccountRequestManager:
    """Simple request manager with domain fallback"""

    NETWORK_ERRORS = (
        requests.exceptions.ReadTimeout,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ProxyError,
        requests.exceptions.SSLError,
        requests.exceptions.ConnectionError,
    )

    DOMAINS = ['https://vkserfing.ru', 'https://vkserfing.com']

    def __init__(self, account_name: str, session: requests.Session,
                 smart_proxy: SmartProxyManager, config: dict):
        self.account_name = account_name
        self.session = session
        self.smart_proxy = smart_proxy
        self.config = config
        self.state = RequestState.READY
        self.current_domain_idx = 0

    def is_aborted(self) -> bool:
        return self.state == RequestState.ABORTED

    def request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        """Make request with domain fallback (no proxy rotation on timeout)"""
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
            return response

        except self.NETWORK_ERRORS as e:
            error_type = type(e).__name__
            proxy_ip = self.smart_proxy.current_ip or 'direct'
            print(f"{Y}[{self.account_name}] {error_type} on {domain} (proxy={proxy_ip}){W}")


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


                print(f"{R}[{self.account_name}] Both domains failed - skipping request{W}")
                return None
