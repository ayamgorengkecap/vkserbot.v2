#!/usr/bin/env python3
"""
VKSerfing Full Automation - VK + Telegram + Instagram
"""

import requests
import time
import json
import random
import re
import os
import getpass
import sys
import signal
import subprocess
from typing import Dict, List, Optional


try:
    from clean_output import CleanOutput
    CLEAN_OUTPUT_AVAILABLE = True
except ImportError:
    CLEAN_OUTPUT_AVAILABLE = False


STOP_FLAG = False


def signal_handler(sig, frame):
    global STOP_FLAG
    print(f"\n\n\033[93m⏸ Stopping... (Ctrl+C detected)\033[0m")
    STOP_FLAG = True

    import threading
    def force_exit():
        time.sleep(2)
        print(f"\n\033[91m✗ Force exit\033[0m")
        os._exit(0)
    threading.Thread(target=force_exit, daemon=True).start()

signal.signal(signal.SIGINT, signal_handler)


try:
    from vk_api_wrapper import VKApi, VKApiError
    VK_AVAILABLE = True
except ImportError:
    VK_AVAILABLE = False

try:
    from telegram_wrapper import TelegramWrapper
    TG_AVAILABLE = True
except ImportError:
    TG_AVAILABLE = False

try:
    from instagrapi import Client as InstaClient
    import warnings, logging
    warnings.filterwarnings("ignore")
    logging.getLogger("instagrapi").setLevel(logging.CRITICAL)
    logging.getLogger("pydantic").setLevel(logging.CRITICAL)

    import sys
    class SuppressPydanticErrors:
        def __init__(self, stream):
            self.stream = stream
        def write(self, msg):
            if 'validation error' not in msg.lower() and 'pydantic' not in msg.lower():
                self.stream.write(msg)
        def flush(self):
            self.stream.flush()

    IG_AVAILABLE = True
except ImportError:
    IG_AVAILABLE = False


G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'

class Colors:
    GREEN, RED, YELLOW, CYAN, RESET = G, R, Y, C, W

CONFIG_FILE = "config.json"
VENV_DIR = "venv"

def clear():
    os.system('clear' if os.name != 'nt' else 'cls')




from proxy_manager import ProxyManager
from smart_proxy_manager import SmartProxyManager
from account_request_manager import AccountRequestManager, RequestState

def parse_proxy(proxy_string):
    """
    Parse proxy string - supports multiple formats:
    - host:port:username:password
    - http://username:password@host:port
    - http://host:port
    Returns dict with proxy config for requests or None if invalid
    """
    if not proxy_string or proxy_string.strip() == '':
        return None

    try:
        proxy_string = proxy_string.strip()


        if proxy_string.startswith(('http://', 'https://', 'socks4://', 'socks5://')):

            protocol = proxy_string.split('://')[0]
            rest = proxy_string.split('://', 1)[1]


            if '@' in rest:

                auth_part, host_part = rest.split('@', 1)
                username, password = auth_part.split(':', 1)
                host, port = host_part.split(':', 1)
            else:

                host, port = rest.split(':', 1)
                username = None
                password = None
        else:

            parts = proxy_string.split(':')
            if len(parts) == 4:
                host, port, username, password = parts
            elif len(parts) == 2:
                host, port = parts
                username = None
                password = None
            else:
                print(f"{R}Invalid proxy format. Expected: host:port:user:pass or http://user:pass@host:port{W}")
                return None


        try:
            port_num = int(port)
            if port_num < 1 or port_num > 65535:
                raise ValueError()
        except:
            print(f"{R}Invalid proxy port: {port}{W}")
            return None


        if username and password:
            proxy_url = f"http://{username}:{password}@{host}:{port}"
        else:
            proxy_url = f"http://{host}:{port}"

        return {
            'http': proxy_url,
            'https': proxy_url,
            'host': host,
            'port': port,
            'username': username
        }
    except Exception as e:
        print(f"{R}Error parsing proxy: {e}{W}")
        return None
        return None

def check_proxy_ip(proxy_dict, timeout=10):
    """
    Check proxy IP and location using multiple services
    Returns dict with IP info or None if failed
    """
    if not proxy_dict:
        return check_current_ip(timeout)


    services = [
        'https://api.ipify.org?format=json',
        'https://api.myip.com',
        'https://ipapi.co/json/',
        'http://ip-api.com/json/'
    ]

    proxies = {
        'http': proxy_dict['http'],
        'https': proxy_dict['https']
    }

    for service in services:
        try:
            resp = requests.get(service, proxies=proxies, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()


                ip = data.get('ip') or data.get('query')
                country = data.get('country') or data.get('country_name') or 'Unknown'
                city = data.get('city') or 'Unknown'

                return {
                    'ip': ip,
                    'country': country,
                    'city': city,
                    'service': service
                }
        except Exception as e:
            continue

    print(f"{R}Failed to check proxy IP (all services failed){W}")
    return None

def check_current_ip(timeout=10):
    """Check current IP without proxy"""
    services = [
        'https://api.ipify.org?format=json',
        'https://api.myip.com',
    ]

    for service in services:
        try:
            resp = requests.get(service, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                ip = data.get('ip')
                country = data.get('country', 'Unknown')

                return {
                    'ip': ip,
                    'country': country,
                    'city': 'Unknown',
                    'service': service
                }
        except:
            continue

    return {'ip': 'Unknown', 'country': 'Unknown', 'city': 'Unknown'}


COUNTRY_FLAGS = {
    'US': '🇺🇸', 'United States': '🇺🇸', 'USA': '🇺🇸',
    'GB': '🇬🇧', 'United Kingdom': '🇬🇧', 'UK': '🇬🇧',
    'RU': '🇷🇺', 'Russia': '🇷🇺', 'Russian Federation': '🇷🇺',
    'CN': '🇨🇳', 'China': '🇨🇳',
    'JP': '🇯🇵', 'Japan': '🇯🇵',
    'DE': '🇩🇪', 'Germany': '🇩🇪', 'Deutschland': '🇩🇪',
    'FR': '🇫🇷', 'France': '🇫🇷',
    'CA': '🇨🇦', 'Canada': '🇨🇦',
    'AU': '🇦🇺', 'Australia': '🇦🇺',
    'BR': '🇧🇷', 'Brazil': '🇧🇷', 'Brasil': '🇧🇷',
    'IN': '🇮🇳', 'India': '🇮🇳',
    'ID': '🇮🇩', 'Indonesia': '🇮🇩',
    'SG': '🇸🇬', 'Singapore': '🇸🇬',
    'MY': '🇲🇾', 'Malaysia': '🇲🇾',
    'TH': '🇹🇭', 'Thailand': '🇹🇭',
    'VN': '🇻🇳', 'Vietnam': '🇻🇳',
    'PH': '🇵🇭', 'Philippines': '🇵🇭',
    'KR': '🇰🇷', 'Korea': '🇰🇷', 'South Korea': '🇰🇷',
    'NL': '🇳🇱', 'Netherlands': '🇳🇱',
    'IT': '🇮🇹', 'Italy': '🇮🇹', 'Italia': '🇮🇹',
    'ES': '🇪🇸', 'Spain': '🇪🇸', 'España': '🇪🇸',
    'MX': '🇲🇽', 'Mexico': '🇲🇽', 'México': '🇲🇽',
    'TR': '🇹🇷', 'Turkey': '🇹🇷', 'Türkiye': '🇹🇷',
    'PL': '🇵🇱', 'Poland': '🇵🇱', 'Polska': '🇵🇱',
    'UA': '🇺🇦', 'Ukraine': '🇺🇦',
    'AR': '🇦🇷', 'Argentina': '🇦🇷',
    'SE': '🇸🇪', 'Sweden': '🇸🇪',
    'CH': '🇨🇭', 'Switzerland': '🇨🇭',
    'BE': '🇧🇪', 'Belgium': '🇧🇪',
    'AT': '🇦🇹', 'Austria': '🇦🇹',
    'NO': '🇳🇴', 'Norway': '🇳🇴',
    'DK': '🇩🇰', 'Denmark': '🇩🇰',
    'FI': '🇫🇮', 'Finland': '🇫🇮',
    'IE': '🇮🇪', 'Ireland': '🇮🇪',
    'NZ': '🇳🇿', 'New Zealand': '🇳🇿',
    'ZA': '🇿🇦', 'South Africa': '🇿🇦',
    'CZ': '🇨🇿', 'Czech Republic': '🇨🇿', 'Czechia': '🇨🇿',
    'RO': '🇷🇴', 'Romania': '🇷🇴',
    'PT': '🇵🇹', 'Portugal': '🇵🇹',
    'GR': '🇬🇷', 'Greece': '🇬🇷',
    'HU': '🇭🇺', 'Hungary': '🇭🇺',
    'BG': '🇧🇬', 'Bulgaria': '🇧🇬',
    'IL': '🇮🇱', 'Israel': '🇮🇱',
    'AE': '🇦🇪', 'United Arab Emirates': '🇦🇪', 'UAE': '🇦🇪',
    'SA': '🇸🇦', 'Saudi Arabia': '🇸🇦',
    'EG': '🇪🇬', 'Egypt': '🇪🇬',
    'NG': '🇳🇬', 'Nigeria': '🇳🇬',
    'KE': '🇰🇪', 'Kenya': '🇰🇪',
    'PK': '🇵🇰', 'Pakistan': '🇵🇰',
    'BD': '🇧🇩', 'Bangladesh': '🇧🇩',
    'HK': '🇭🇰', 'Hong Kong': '🇭🇰',
    'TW': '🇹🇼', 'Taiwan': '🇹🇼',
}

def get_country_flag(country_name_or_code):
    """Get emoji flag for country"""
    if not country_name_or_code or country_name_or_code == 'Unknown':
        return '🌍'


    if country_name_or_code in COUNTRY_FLAGS:
        return COUNTRY_FLAGS[country_name_or_code]


    for key, flag in COUNTRY_FLAGS.items():
        if key.lower() == country_name_or_code.lower():
            return flag


    return '🌍'

def get_ip_location(ip=None, proxy_dict=None, timeout=15, max_retries=3):
    """
    Get detailed IP location information with retry mechanism

    Args:
        ip: IP address to check (optional, will detect current IP if not provided)
        proxy_dict: Proxy configuration dict (from parse_proxy)
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts per service

    Returns:
        Dict with detailed location info or None on failure
    """


    services = [
        {
            'url': 'http://ip-api.com/json/',
            'parser': lambda d: {
                'ip': d.get('query'),
                'country': d.get('country', 'Unknown'),
                'country_code': d.get('countryCode', ''),
                'region': d.get('regionName', 'Unknown'),
                'city': d.get('city', 'Unknown'),
                'zip': d.get('zip', ''),
                'lat': d.get('lat', 0),
                'lon': d.get('lon', 0),
                'timezone': d.get('timezone', ''),
                'isp': d.get('isp', 'Unknown'),
                'org': d.get('org', 'Unknown'),
                'as': d.get('as', ''),
            }
        },
        {
            'url': 'https://ipapi.co/json/',
            'parser': lambda d: {
                'ip': d.get('ip'),
                'country': d.get('country_name', 'Unknown'),
                'country_code': d.get('country_code', ''),
                'region': d.get('region', 'Unknown'),
                'city': d.get('city', 'Unknown'),
                'zip': d.get('postal', ''),
                'lat': d.get('latitude', 0),
                'lon': d.get('longitude', 0),
                'timezone': d.get('timezone', ''),
                'isp': d.get('org', 'Unknown'),
                'org': d.get('org', 'Unknown'),
                'as': d.get('asn', ''),
            }
        },
        {
            'url': 'https://ipwhois.app/json/',
            'parser': lambda d: {
                'ip': d.get('ip'),
                'country': d.get('country', 'Unknown'),
                'country_code': d.get('country_code', ''),
                'region': d.get('region', 'Unknown'),
                'city': d.get('city', 'Unknown'),
                'zip': d.get('postal', ''),
                'lat': d.get('latitude', 0),
                'lon': d.get('longitude', 0),
                'timezone': d.get('timezone', ''),
                'isp': d.get('isp', 'Unknown'),
                'org': d.get('org', 'Unknown'),
                'as': d.get('asn', ''),
            }
        }
    ]


    proxies = None
    if proxy_dict:
        proxies = {
            'http': proxy_dict['http'],
            'https': proxy_dict['https']
        }


    for service_info in services:
        for retry in range(max_retries):
            try:
                url = service_info['url']
                if ip:
                    url += ip

                resp = requests.get(url, proxies=proxies, timeout=timeout)

                if resp.status_code == 200:
                    data = resp.json()


                    if data.get('status') == 'fail':
                        continue


                    result = service_info['parser'](data)


                    result['flag'] = get_country_flag(result.get('country_code') or result.get('country'))
                    result['service'] = url

                    return result

            except (requests.exceptions.ProxyError,
                    requests.exceptions.ConnectionError,
                    requests.exceptions.Timeout) as e:

                if retry < max_retries - 1:

                    time.sleep(1 * (retry + 1))
                    continue
                else:

                    break
            except Exception as e:

                break


    return None

def format_ip_location(location_info, detailed=False):
    """
    Format IP location info for display

    Args:
        location_info: Dict from get_ip_location()
        detailed: Show detailed information

    Returns:
        Formatted string
    """
    if not location_info:
        return "Unknown Location"

    flag = location_info.get('flag', '🌍')
    ip = location_info.get('ip', 'Unknown')
    country = location_info.get('country', 'Unknown')
    city = location_info.get('city', 'Unknown')

    if detailed:
        region = location_info.get('region', '')
        isp = location_info.get('isp', '')

        result = f"{flag} {ip}"


        location_parts = []
        if city != 'Unknown':
            location_parts.append(city)
        if region and region != 'Unknown':
            location_parts.append(region)
        if country != 'Unknown':
            location_parts.append(country)

        if location_parts:
            result += f" ({', '.join(location_parts)})"


        if isp and isp != 'Unknown':
            result += f" | {isp}"

        return result
    else:

        if city != 'Unknown' and city != country:
            return f"{flag} {ip} ({city}, {country})"
        else:
            return f"{flag} {ip} ({country})"


def get_all_used_proxies(accounts_dir='accounts'):
    """
    Get set of all proxy IPs already used by other accounts

    Args:
        accounts_dir: Path to accounts directory

    Returns:
        Set of proxy IPs (just the IP addresses)
    """
    used_ips = set()


    possible_paths = [
        accounts_dir,
        os.path.join(os.path.dirname(os.path.dirname(__file__)), accounts_dir),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), accounts_dir),
        '/home/ubuntu/vkservingbot/accounts'
    ]

    actual_path = None
    for path in possible_paths:
        if os.path.exists(path):
            actual_path = path
            break

    if not actual_path:
        return used_ips


    for account_folder in os.listdir(actual_path):
        account_path = os.path.join(actual_path, account_folder)
        config_file = os.path.join(account_path, 'config.json')

        if not os.path.isfile(config_file):
            continue

        try:
            with open(config_file, 'r') as f:
                config = json.load(f)


            proxy_string = config.get('proxy', {}).get('proxy_string')
            if proxy_string:

                try:
                    if '@' in proxy_string:
                        ip = proxy_string.split('@')[1].split(':')[0]
                    else:
                        ip = proxy_string.split('://')[1].split(':')[0] if '://' in proxy_string else proxy_string.split(':')[0]
                    used_ips.add(ip)
                except:
                    pass
        except:

            pass

    return used_ips

class UserAgentGenerator:
    """
    Generate realistic user agents based on real device statistics
    Focuses on popular Android devices and browsers
    """


    DEVICES = [

        {'brand': 'Samsung', 'model': 'SM-G998B', 'name': 'Galaxy S21 Ultra', 'weight': 15},
        {'brand': 'Samsung', 'model': 'SM-G991B', 'name': 'Galaxy S21', 'weight': 12},
        {'brand': 'Samsung', 'model': 'SM-A525F', 'name': 'Galaxy A52', 'weight': 10},
        {'brand': 'Samsung', 'model': 'SM-A515F', 'name': 'Galaxy A51', 'weight': 10},
        {'brand': 'Samsung', 'model': 'SM-N986B', 'name': 'Galaxy Note 20 Ultra', 'weight': 8},


        {'brand': 'Xiaomi', 'model': 'M2102J20SG', 'name': 'Redmi Note 10 Pro', 'weight': 12},
        {'brand': 'Xiaomi', 'model': 'M2101K6G', 'name': 'Redmi Note 10', 'weight': 10},
        {'brand': 'Xiaomi', 'model': 'M2007J20CG', 'name': 'Mi 11', 'weight': 8},
        {'brand': 'Xiaomi', 'model': '21081111RG', 'name': 'Redmi 10', 'weight': 8},


        {'brand': 'OPPO', 'model': 'CPH2237', 'name': 'A96', 'weight': 7},
        {'brand': 'OPPO', 'model': 'CPH2325', 'name': 'Reno 7', 'weight': 7},


        {'brand': 'vivo', 'model': 'V2120', 'name': 'V23', 'weight': 6},
        {'brand': 'vivo', 'model': 'V2111', 'name': 'Y53s', 'weight': 5},


        {'brand': 'realme', 'model': 'RMX3363', 'name': '9 Pro+', 'weight': 6},
        {'brand': 'realme', 'model': 'RMX2205', 'name': '8 Pro', 'weight': 5},
    ]


    ANDROID_VERSIONS = [
        {'version': '13', 'sdk': 33, 'weight': 25},
        {'version': '12', 'sdk': 32, 'weight': 30},
        {'version': '11', 'sdk': 30, 'weight': 25},
        {'version': '10', 'sdk': 29, 'weight': 15},
        {'version': '9', 'sdk': 28, 'weight': 5},
    ]


    CHROME_VERSIONS = [
        '120.0.6099.144',
        '119.0.6045.193',
        '118.0.5993.112',
        '117.0.5938.153',
        '116.0.5845.172'
    ]

    @staticmethod
    def generate(config=None):
        """
        Generate a realistic user agent string
        Args:
            config: Config dict to check for existing user_agent
        Returns:
            Dict with user_agent data
        """
        import random


        if config:
            existing_ua = config.get('user_agent', {})
            if existing_ua and existing_ua.get('user_agent'):

                return existing_ua



        devices_pool = []
        for device in UserAgentGenerator.DEVICES:
            devices_pool.extend([device] * device['weight'])
        device = random.choice(devices_pool)


        android_pool = []
        for version in UserAgentGenerator.ANDROID_VERSIONS:
            android_pool.extend([version] * version['weight'])
        android = random.choice(android_pool)


        chrome_version = random.choice(UserAgentGenerator.CHROME_VERSIONS)


        user_agent = (
            f"Mozilla/5.0 (Linux; Android {android['version']}; {device['model']}) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Mobile Safari/537.36"
        )

        return {
            'user_agent': user_agent,
            'device': f"{device['brand']} {device['name']}",
            'model': device['model'],
            'android_version': android['version'],
            'chrome_version': chrome_version
        }

    @staticmethod
    def get_device_info(user_agent_data):
        """Get readable device info from user agent data"""
        if not user_agent_data:
            return "Unknown Device"

        return f"{user_agent_data['device']} | Android {user_agent_data['android_version']}"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)

def show_header():
    clear()
    print(f"{C}┌{'─' * 58}┐{W}")
    print(f"{C}│{W}  {G}██╗   ██╗{C}██╗  ██╗{R}███████╗{W}███████╗██████╗ ███████╗  {C}│{W}")
    print(f"{C}│{W}  {G}██║   ██║{C}██║ ██╔╝{R}██╔════╝{W}██╔════╝██╔══██╗██╔════╝  {C}│{W}")
    print(f"{C}│{W}  {G}██║   ██║{C}█████╔╝ {R}███████╗{W}█████╗  ██████╔╝█████╗    {C}│{W}")
    print(f"{C}│{W}  {G}╚██╗ ██╔╝{C}██╔═██╗ {R}╚════██║{W}██╔══╝  ██╔══██╗██╔══╝    {C}│{W}")
    print(f"{C}│{W}   {G}╚████╔╝ {C}██║  ██╗{R}███████║{W}███████╗██║  ██║██║       {C}│{W}")
    print(f"{C}│{W}    {G}╚═══╝  {C}╚═╝  ╚═╝{R}╚══════╝{W}╚══════╝╚═╝  ╚═╝╚═╝       {C}│{W}")
    print(f"{C}├{'─' * 58}┤{W}")
    print(f"{C}│{W}  {Y}▶{W} Automated Social Media Bot {Y}v2.1{W}                       {C}│{W}")
    print(f"{C}│{W}  {Y}▶{W} VK · Instagram · Telegram Multi-Platform            {C}│{W}")
    print(f"{C}│{W}  {Y}▶{W} Status: {G}[ONLINE]{W} {Y}|{W} Mode: {C}[AUTO]{W}                      {C}│{W}")
    print(f"{C}└{'─' * 58}┘{W}\n")

def show_status(config):
    ck = config.get('credentials', {}).get('cookies', {}).get('vkstoken')
    vk = config.get('vk_api', {})
    ig = config.get('instagram', {})
    tg = TG_AVAILABLE and os.path.exists('telegram_session.json')

    print("Status:")
    print(f"  Cookie  : {G}OK{W}" if ck else f"  Cookie  : {R}Not Set{W}")
    print(f"  VK API  : {G}@{vk.get('user_id','?')}{W}" if vk.get('enabled') else f"  VK API  : {R}Not Set{W}")
    print(f"  Instagram: {G}@{ig.get('username','?')}{W}" if ig.get('enabled') else f"  Instagram: {R}Not Set{W}")
    print(f"  Telegram : {G}OK{W}" if tg else f"  Telegram : {Y}Not Set{W}")
    print()


def get_pip_cmd():
    """Get the correct pip command (venv or system)"""
    venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')
    if os.path.exists(venv_pip):
        return venv_pip
    return None


def get_python_cmd():
    """Get the correct python command (venv or system)"""
    venv_python = os.path.join(VENV_DIR, 'bin', 'python')
    if os.path.exists(venv_python):
        return venv_python
    return sys.executable


def run_cmd(cmd, show_output=True):
    """Run command and return success status"""
    try:
        if show_output:
            result = subprocess.run(cmd, shell=True)
        else:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"{R}Error: {e}{W}")
        return False


def install_requirements():
    """Install Python requirements with venv support"""
    show_header()
    print(f"{C}[Install Requirements]{W}\n")

    packages = ['requests', 'instagrapi', 'telethon', 'beautifulsoup4']

    print("Packages:")
    for pkg in packages:
        print(f"  - {pkg}")

    print(f"\nVenv: {G}{VENV_DIR}{W}" if os.path.exists(VENV_DIR) else f"\nVenv: {Y}Not exists{W}")

    ans = input(f"\nInstall? (y/n): ").strip().lower()
    if ans != 'y':
        return


    venv_python = os.path.join(VENV_DIR, 'bin', 'python')
    venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')

    if not os.path.exists(venv_python):
        print(f"\n{Y}Creating venv...{W}")
        if not run_cmd(f"{sys.executable} -m venv {VENV_DIR}"):
            print(f"{R}Failed to create venv!{W}")
            print(f"{Y}Trying with system pip...{W}")
            venv_pip = None
        else:
            print(f"{G}Venv created!{W}")
            venv_pip = os.path.join(VENV_DIR, 'bin', 'pip')


    if venv_pip and os.path.exists(venv_pip):
        pip_cmd = venv_pip
        print(f"\n{G}Using venv pip{W}")
    else:

        pip_cmd = f"{sys.executable} -m pip"
        print(f"\n{Y}Using system pip{W}")


    print(f"\n{Y}Upgrading pip...{W}")
    run_cmd(f"{pip_cmd} install --upgrade pip -q", show_output=False)


    print()
    for pkg in packages:
        print(f"Installing {pkg}...", end=" ", flush=True)

        cmd = f"{pip_cmd} install {pkg} -q"
        if run_cmd(cmd, show_output=False):
            print(f"{G}OK{W}")
        else:

            cmd = f"{pip_cmd} install {pkg} --break-system-packages -q"
            if run_cmd(cmd, show_output=False):
                print(f"{G}OK{W}")
            else:
                print(f"{R}FAILED{W}")

    print(f"\n{G}Done!{W}")


    if os.path.exists(venv_python):
        print(f"\n{Y}Note: Gunakan venv untuk menjalankan:{W}")
        print(f"  source {VENV_DIR}/bin/activate")
        print(f"  python vk_full_automation.py")
        print(f"\n{Y}Atau langsung:{W}")
        print(f"  {venv_python} vk_full_automation.py")

    input("\nEnter...")


def read_multiline_input():
    """Read multi-line input until 'END' or 2 empty lines"""
    print(f"{Y}Paste data, lalu ketik END dan Enter:{W}\n")

    lines = []
    empty_count = 0

    while True:
        try:
            line = input()

            if line.strip().upper() == 'END':
                break

            if not line.strip():
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0

            lines.append(line)

        except EOFError:
            break
        except KeyboardInterrupt:
            return ""

    return '\n'.join(lines)


def parse_http_request(text):
    """Parse HTTP request format to extract cookies and xsrf token"""
    cookies = {}
    xsrf = ""

    for line in text.split('\n'):
        line = line.strip()

        if line.lower().startswith('x-xsrf-token:'):
            xsrf = line.split(':', 1)[1].strip()

        if line.lower().startswith('cookie:'):
            cookie_part = line.split(':', 1)[1].strip()
            if '=' in cookie_part:
                parts = cookie_part.split('=', 1)
                if len(parts) == 2:
                    cookies[parts[0].strip()] = parts[1].strip()

    return cookies, xsrf


def parse_vk_oauth_url(url):
    """Parse VK OAuth URL to extract token and user_id"""
    token, user_id = "", ""

    match = re.search(r'access_token=([^&\s]+)', url)
    if match:
        token = match.group(1)

    match = re.search(r'user_id=(\d+)', url)
    if match:
        user_id = match.group(1)

    return token, user_id


def setup_cookie(config):
    show_header()
    print(f"{C}[Setup Cookie VKSerfing]{W}\n")

    current = config.get('credentials', {}).get('cookies', {}).get('vkstoken')
    if current:
        print(f"Current: {G}...{current[-20:]}{W}")
        choice = input("\n1. Gunakan yang ada\n2. Update baru\n\n[1/2]: ").strip()
        if choice == '1':
            return config

    print("\nCopy HTTP request dari browser DevTools:")
    print("(Network tab > klik request > Copy as cURL atau Copy request headers)\n")

    text = read_multiline_input()

    if text:
        cookies, xsrf = parse_http_request(text)

        if cookies.get('vkstoken'):
            if 'credentials' not in config:
                config['credentials'] = {}
            config['credentials']['cookies'] = cookies
            config['credentials']['xsrf_token'] = xsrf

            print(f"\n{G}Cookie saved!{W}")
            print(f"  vkstoken : ...{cookies.get('vkstoken','')[-15:]}")
            print(f"  vksid    : ...{cookies.get('vksid','')[-15:]}")
            print(f"  sessid   : {cookies.get('sessid','')}")
            print(f"  xsrf     : {xsrf[:20]}..." if xsrf else "  xsrf     : -")
        else:
            print(f"\n{R}vkstoken not found!{W}")
    else:
        print(f"\n{Y}Cancelled{W}")

    input("\nEnter...")
    return config


def setup_vk(config):
    show_header()
    print(f"{C}[Setup VK API Token]{W}\n")

    if not VK_AVAILABLE:
        print(f"{R}vk_api_wrapper not found!{W}")
        input("\nEnter...")
        return config

    current = config.get('vk_api', {})
    if current.get('access_token'):
        print(f"Token: {G}...{current['access_token'][-20:]}{W}")
        print(f"User ID: {current.get('user_id', '?')}")
        choice = input("\n1. Gunakan yang ada\n2. Update baru\n3. Disable\n\n[1/2/3]: ").strip()
        if choice == '1':
            config['vk_api']['enabled'] = True
            return config
        elif choice == '3':
            config['vk_api']['enabled'] = False
            print(f"\n{Y}Disabled{W}")
            input("\nEnter...")
            return config

    print("\nPaste URL dari VK OAuth:")
    print(f"{Y}(https://oauth.vk.com/blank.html#access_token=...&user_id=...){W}\n")

    url = input("URL: ").strip()

    if url:
        token, user_id = parse_vk_oauth_url(url)

        if token:
            config['vk_api'] = {
                'enabled': True,
                'access_token': token,
                'user_id': user_id,
            }
            print(f"\n{G}VK Token saved!{W}")
            print(f"  Token  : ...{token[-20:]}")
            print(f"  User ID: {user_id}")
        else:
            print(f"\n{R}Token not found!{W}")

    input("\nEnter...")
    return config


def check_instagrapi():
    """Check if instagrapi is available and try to import it"""
    try:
        from instagrapi import Client as InstaClient
        import warnings, logging
        warnings.filterwarnings("ignore")
        logging.getLogger("instagrapi").setLevel(logging.CRITICAL)
        return True, InstaClient
    except ImportError:
        return False, None


def setup_instagram(config):
    show_header()
    print(f"{C}[Setup Instagram]{W}\n")


    ig_available, InstaClient = check_instagrapi()

    if not ig_available:
        print(f"{R}instagrapi not installed!{W}\n")
        choice = input("Install instagrapi sekarang? (y/n): ").strip().lower()

        if choice == 'y':
            print(f"\n{Y}Installing instagrapi...{W}")


            pip_cmd = f"{sys.executable} -m pip"
            cmd = f"{pip_cmd} install instagrapi -q"

            if run_cmd(cmd, show_output=False):
                print(f"{G}Installation successful!{W}")


                ig_available, InstaClient = check_instagrapi()
                if not ig_available:
                    print(f"{R}Import failed after install. Please restart script.{W}")
                    input("\nEnter...")
                    return config
                else:
                    print(f"{G}Import successful!{W}\n")
            else:

                cmd = f"{pip_cmd} install instagrapi --break-system-packages -q"
                if run_cmd(cmd, show_output=False):
                    print(f"{G}Installation successful!{W}")


                    ig_available, InstaClient = check_instagrapi()
                    if not ig_available:
                        print(f"{R}Import failed after install. Please restart script.{W}")
                        input("\nEnter...")
                        return config
                    else:
                        print(f"{G}Import successful!{W}\n")
                else:
                    print(f"{R}Installation failed!{W}")
                    print(f"{Y}Coba manual: pip install instagrapi{W}")
                    input("\nEnter...")
                    return config
        else:
            print(f"\n{Y}Setup dibatalkan.{W}")
            print(f"{Y}Install manual: pip install instagrapi{W}")
            input("\nEnter...")
            return config

    current = config.get('instagram', {})
    if current.get('username'):
        print(f"Account: {G}@{current['username']}{W}")
        choice = input("\n1. Gunakan yang ada\n2. Update baru\n3. Disable\n\n[1/2/3]: ").strip()
        if choice == '1':
            config['instagram']['enabled'] = True
            return config
        elif choice == '3':
            config['instagram']['enabled'] = False
            print(f"\n{Y}Disabled{W}")
            input("\nEnter...")
            return config

    print()
    username = input("Username: ").strip()
    password = input("Password: ")

    print(f"\n{Y}Testing login...{W}")
    try:
        client = InstaClient()
        client.login(username, password)
        client.dump_settings(f"ig_session_{username}.json")
        print(f"{G}Login OK!{W}")

        config['instagram'] = {
            'enabled': True,
            'username': username,
            'password': password,
        }
    except Exception as e:
        print(f"{R}Login failed: {e}{W}")

    input("\nEnter...")
    return config


def setup_telegram(config):
    show_header()
    print(f"{C}[Setup Telegram]{W}\n")

    if not TG_AVAILABLE:
        print(f"{R}telethon not installed!{W}")
        print("Pilih menu 8 untuk install.")
        input("\nEnter...")
        return config

    if os.path.exists('telegram_session.json'):
        print(f"Session: {G}Available{W}")
        choice = input("\n1. Gunakan yang ada\n2. Setup ulang\n\n[1/2]: ").strip()
        if choice == '1':
            return config


    import asyncio
    from telegram_session_manager import TelegramSessionManager


    os.makedirs('sessions', exist_ok=True)


    manager = TelegramSessionManager()


    API_ID = "1724399"
    API_HASH = "7f6c4af5220db320413ff672093ee102"

    print(f"\n{Y}API credentials (default):{W}")
    print(f"  API ID: {API_ID}")
    print(f"  API Hash: {API_HASH[:20]}...")


    print(f"\n{Y}Setup session baru:{W}")
    session_name = input("Session name [my_telegram]: ").strip() or "my_telegram"
    phone = input("Nomor HP (dengan kode negara, contoh: +6281234567890): ").strip()

    if not phone:
        print(f"\n{R}Nomor HP wajib diisi!{W}")
        input("\nEnter...")
        return config


    print(f"\n{Y}Menambahkan session '{session_name}'...{W}")
    manager.add_session(session_name, int(API_ID), API_HASH, phone)


    print(f"\n{Y}Kode verifikasi akan dikirim ke Telegram Anda{W}")
    confirm = input("Lanjutkan? (y/n): ").strip().lower()
    if confirm != 'y':
        print(f"\n{Y}Dibatalkan{W}")
        input("\nEnter...")
        return config


    print(f"\n{Y}Membuat session...{W}")

    async def create():
        return await manager.create_session(session_name)

    success = asyncio.run(create())

    if success:
        print(f"\n{G}Session berhasil dibuat!{W}")
        print(f"Session akan otomatis digunakan untuk Telegram tasks")
    else:
        print(f"\n{R}Gagal membuat session!{W}")

    input("\nEnter...")
    return config


def setup_credentials(config):
    show_header()
    print(f"{C}[Setup Login Credentials]{W}\n")
    print("Email dan password dibutuhkan untuk auto re-login")
    print("saat cookie expired.\n")

    if 'credentials' not in config:
        config['credentials'] = {}

    current_email = config['credentials'].get('email', '')
    current_pwd = config['credentials'].get('password', '')

    if current_email:
        print(f"Current Email: {G}{current_email}{W}")
        choice = input("\n1. Gunakan yang ada\n2. Update baru\n\n[1/2]: ").strip()
        if choice == '1':
            return config

    print()
    email = input("Email: ").strip() or current_email
    password = getpass.getpass("Password: ") or current_pwd

    if email and password:
        config['credentials']['email'] = email
        config['credentials']['password'] = password
        print(f"\n{G}Credentials saved!{W}")
        print(f"  Email: {email}")
    else:
        print(f"\n{Y}Incomplete data, not saved{W}")

    input("\nEnter...")
    return config


def setup_captcha(config):
    show_header()
    print(f"{C}[Setup Captcha Solver]{W}\n")

    if 'captcha' not in config:
        config['captcha'] = {}

    current = config.get('captcha', {})
    solver = current.get('solver', '2captcha')
    api_key = current.get('api_key', '')
    enabled = current.get('enabled', False)

    print(f"Current Status: {G}Enabled{W}" if enabled else f"Current Status: {R}Disabled{W}")
    if api_key:
        print(f"Solver: {solver}")
        print(f"API Key: {api_key[:20]}...")

    print(f"\n{Y}Note: Yandex SmartCaptcha support:{W}")
    print(f"  ✓ 2Captcha.com - RECOMMENDED (full support)")
    print(f"  ✓ XEvil - Local software")
    print(f"  ✗ Anti-Captcha - Limited/No support")

    print(f"\nOptions:")
    print(f"  1. 2Captcha.com {G}(recommended for Yandex){W}")
    print(f"  2. XEvil (local)")
    print(f"  3. Anti-Captcha.com {Y}(not recommended){W}")
    print(f"  4. Disable auto-login")
    print()

    choice = input("[1/2/3/4]: ").strip()

    if choice == '4':
        config['captcha']['enabled'] = False
        print(f"\n{Y}Auto-login disabled{W}")
    elif choice in ['1', '2', '3']:
        if choice == '1':
            solver_name = '2captcha'
        elif choice == '2':
            solver_name = 'xevil'
        else:
            solver_name = 'anticaptcha'

        print()
        if choice == '1':
            print("2Captcha API Key:")
            print(f"{Y}(Dapatkan di: https://2captcha.com){W}")
            print(f"{Y}(Harga: ~$2.99 per 1000 captcha){W}")
            new_key = input(f"API Key [{api_key[:10]}... (current) if key else 'none']: ").strip()
        elif choice == '2':
            print("XEvil API Key:")
            new_key = input(f"API Key [current: {api_key[:10] if api_key else 'none'}]: ").strip()
            xevil_host = input(f"XEvil Host [http://127.0.0.1]: ").strip() or "http://127.0.0.1"
            config['captcha']['xevil_host'] = xevil_host
        else:
            print("Anti-Captcha API Key:")
            print(f"{Y}(Dapatkan di: https://anti-captcha.com){W}")
            print(f"{R}WARNING: Anti-Captcha may not support Yandex SmartCaptcha!{W}")
            new_key = input(f"API Key [{api_key[:10]}... (current) if key else 'none']: ").strip()

        if new_key:
            config['captcha']['api_key'] = new_key
            config['captcha']['solver'] = solver_name
            config['captcha']['enabled'] = True

            print(f"\n{G}Captcha solver configured!{W}")
            print(f"  Solver: {solver_name}")
            print(f"  API Key: {config['captcha']['api_key'][:20]}...")
        else:
            print(f"\n{Y}No changes made{W}")

    input("\nEnter...")
    return config


def setup_tasks(config):
    show_header()
    print(f"{C}[Task Settings]{W}\n")

    if 'task_types' not in config:
        config['task_types'] = {}

    tasks = [
        ('vk_friends', 'VK Friends'),
        ('vk_groups', 'VK Groups'),
        ('vk_likes', 'VK Likes'),
        ('vk_reposts', 'VK Reposts'),
        ('vk_polls', 'VK Polls'),
        ('instagram_followers', 'IG Followers'),
        ('instagram_likes', 'IG Likes'),
        ('instagram_comments', 'IG Comments'),
        ('instagram_video', 'IG Video Views'),
        ('telegram_followers', 'TG Followers'),
        ('telegram_views', 'TG Views'),
        ('tiktok_video', 'TikTok Video Views'),
    ]

    print("Toggle (y/n/enter=skip):\n")
    for key, name in tasks:
        cur = config['task_types'].get(key, False)
        st = f"{G}ON{W}" if cur else f"{R}OFF{W}"
        ans = input(f"  {name} [{st}]: ").strip().lower()
        if ans == 'y': config['task_types'][key] = True
        elif ans == 'n': config['task_types'][key] = False

    print(f"\n{G}Saved!{W}")
    input("\nEnter...")
    return config


def main_menu():
    config = load_config()

    while True:
        show_header()
        show_status(config)

        print("Menu:")
        print(f"  1. {G}Start Bot{W}")
        print(f"  2. {G}Start Loop{W}")
        print(f"  3. Setup Cookie")
        print(f"  4. Setup Login Credentials {Y}(for auto-login){W}")
        print(f"  5. Setup Captcha Solver {Y}(for auto-login){W}")
        print(f"  6. Setup VK Token")
        print(f"  7. Setup Instagram")
        print(f"  8. Setup Telegram")
        print(f"  9. Task Settings")
        print(f"  10. Install Requirements")
        print(f"  11. {C}Validate Accounts{W}")
        print(f"  12. {C}Test Auto-Login{W}")
        print(f"  0. Exit")
        print()

        ch = input("Choice: ").strip()

        if ch == '1':
            save_config(config)
            return 'run', config
        elif ch == '2':
            save_config(config)
            return 'loop', config
        elif ch == '3':
            config = setup_cookie(config)
            save_config(config)
        elif ch == '4':
            config = setup_credentials(config)
            save_config(config)
        elif ch == '5':
            config = setup_captcha(config)
            save_config(config)
        elif ch == '6':
            config = setup_vk(config)
            save_config(config)
        elif ch == '7':
            config = setup_instagram(config)
            save_config(config)
        elif ch == '8':
            config = setup_telegram(config)
        elif ch == '9':
            config = setup_tasks(config)
            save_config(config)
        elif ch == '10':
            install_requirements()
        elif ch == '11':

            show_header()
            print(f"{C}[Validate Accounts]{W}\n")


            if not config.get('credentials', {}).get('cookies', {}).get('vkstoken'):
                print(f"{R}Cookie not configured!{W}")
                print("Please setup cookie first (Menu 3)")
            else:
                bot = VKSerfingBot(config)
                print("Fetching account info from server...")
                if bot.get_accounts_info():
                    bot.validate_accounts()
                else:
                    print(f"{R}Failed to fetch account info{W}")
                    print("Check your cookie or internet connection")

            input("\nEnter...")
        elif ch == '12':

            show_header()
            print(f"{C}[Test Auto-Login]{W}\n")

            creds = config.get('credentials', {})
            captcha_cfg = config.get('captcha', {})

            email = creds.get('email', '')
            password = creds.get('password', '')

            if not email or not password:
                print(f"{R}Credentials not configured!{W}")
                print("Please setup credentials first (Menu 4)")
            elif not captcha_cfg.get('enabled'):
                print(f"{R}Captcha solver not configured!{W}")
                print("Please setup captcha solver first (Menu 5)")
            else:
                print(f"Email: {email}")
                print(f"Captcha: {captcha_cfg.get('solver', 'anticaptcha')}")
                print()

                confirm = input("Start test login? (y/n): ").strip().lower()
                if confirm == 'y':
                    try:
                        from auth_manager import VKSerfingAuth, AuthError

                        auth = VKSerfingAuth(email, password, captcha_cfg)
                        cookies = auth.auto_login()


                        if 'credentials' not in config:
                            config['credentials'] = {}
                        config['credentials']['cookies'] = cookies
                        save_config(config)

                        print(f"\n{G}✓ Test successful! Cookies saved to config.{W}")
                    except AuthError as e:
                        print(f"\n{R}✗ Test failed: {e}{W}")
                    except ImportError:
                        print(f"\n{R}✗ auth_manager module not found!{W}")
                    except Exception as e:
                        print(f"\n{R}✗ Error: {e}{W}")

            input("\nEnter...")
        elif ch == '0':
            return 'exit', config




class DeviceFingerprintGenerator:
    """Generate realistic and unique device fingerprints for Instagram"""


    DEVICES = [

        {'manufacturer': 'Samsung', 'device': 'SM-G998B', 'model': 'Galaxy S21 Ultra', 'cpu': 'exynos990', 'dpi': '480dpi', 'resolution': '1440x3200', 'weight': 10},
        {'manufacturer': 'Samsung', 'device': 'SM-G996B', 'model': 'Galaxy S21+', 'cpu': 'exynos990', 'dpi': '480dpi', 'resolution': '1080x2400', 'weight': 8},
        {'manufacturer': 'Samsung', 'device': 'SM-G991B', 'model': 'Galaxy S21', 'cpu': 'exynos990', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 9},
        {'manufacturer': 'Samsung', 'device': 'SM-A515F', 'model': 'Galaxy A51', 'cpu': 'exynos9611', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 12},
        {'manufacturer': 'Samsung', 'device': 'SM-A525F', 'model': 'Galaxy A52', 'cpu': 'sm7125', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 11},
        {'manufacturer': 'Samsung', 'device': 'SM-N975F', 'model': 'Galaxy Note10+', 'cpu': 'exynos9825', 'dpi': '480dpi', 'resolution': '1440x3040', 'weight': 7},
        {'manufacturer': 'Samsung', 'device': 'SM-G973F', 'model': 'Galaxy S10', 'cpu': 'exynos9820', 'dpi': '480dpi', 'resolution': '1440x3040', 'weight': 8},


        {'manufacturer': 'Xiaomi', 'device': 'M2101K9G', 'model': 'Redmi Note 10 Pro', 'cpu': 'sm7150', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 13},
        {'manufacturer': 'Xiaomi', 'device': 'M2102J20SG', 'model': 'Redmi Note 10', 'cpu': 'sm6115', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 12},
        {'manufacturer': 'Xiaomi', 'device': 'M2007J20CG', 'model': 'Redmi Note 9 Pro', 'cpu': 'sm7125', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 10},
        {'manufacturer': 'Xiaomi', 'device': 'M2004J19C', 'model': 'Redmi 9', 'cpu': 'mt6765', 'dpi': '400dpi', 'resolution': '1080x2340', 'weight': 11},
        {'manufacturer': 'Xiaomi', 'device': 'M2012K11AG', 'model': 'POCO X3 Pro', 'cpu': 'sm8150', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 9},
        {'manufacturer': 'Xiaomi', 'device': '21081111RG', 'model': 'Redmi 10', 'cpu': 'mt6769', 'dpi': '400dpi', 'resolution': '1080x2400', 'weight': 10},


        {'manufacturer': 'OnePlus', 'device': 'LE2123', 'model': 'OnePlus 9 Pro', 'cpu': 'sm8350', 'dpi': '480dpi', 'resolution': '1440x3216', 'weight': 6},
        {'manufacturer': 'OnePlus', 'device': 'LE2121', 'model': 'OnePlus 9', 'cpu': 'sm8350', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 5},
        {'manufacturer': 'OnePlus', 'device': 'GM1913', 'model': 'OnePlus 7 Pro', 'cpu': 'sm8150', 'dpi': '480dpi', 'resolution': '1440x3120', 'weight': 4},
        {'manufacturer': 'OnePlus', 'device': 'IN2023', 'model': 'OnePlus Nord', 'cpu': 'sm7250', 'dpi': '420dpi', 'resolution': '1080x2400', 'weight': 5},


        {'manufacturer': 'OPPO', 'device': 'CPH2205', 'model': 'Reno6', 'cpu': 'mt6877', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 7},
        {'manufacturer': 'OPPO', 'device': 'CPH2021', 'model': 'A53', 'cpu': 'sm4250', 'dpi': '400dpi', 'resolution': '1080x2400', 'weight': 8},
        {'manufacturer': 'OPPO', 'device': 'CPH2121', 'model': 'A74', 'cpu': 'sm6115', 'dpi': '400dpi', 'resolution': '1080x2400', 'weight': 7},


        {'manufacturer': 'vivo', 'device': 'V2109', 'model': 'V21', 'cpu': 'mt6853', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 6},
        {'manufacturer': 'vivo', 'device': 'V2061', 'model': 'Y20', 'cpu': 'sm4250', 'dpi': '400dpi', 'resolution': '720x1600', 'weight': 6},
        {'manufacturer': 'vivo', 'device': 'V2111', 'model': 'Y33s', 'cpu': 'mt6769', 'dpi': '400dpi', 'resolution': '1080x2400', 'weight': 5},


        {'manufacturer': 'Google', 'device': 'redfin', 'model': 'Pixel 5', 'cpu': 'sm7250', 'dpi': '440dpi', 'resolution': '1080x2340', 'weight': 4},
        {'manufacturer': 'Google', 'device': 'barbet', 'model': 'Pixel 5a', 'cpu': 'sm7250', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 4},
        {'manufacturer': 'Google', 'device': 'raven', 'model': 'Pixel 6 Pro', 'cpu': 'gs101', 'dpi': '480dpi', 'resolution': '1440x3120', 'weight': 3},


        {'manufacturer': 'realme', 'device': 'RMX3085', 'model': 'realme 8 Pro', 'cpu': 'sm7125', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 4},
        {'manufacturer': 'realme', 'device': 'RMX3201', 'model': 'realme GT Master', 'cpu': 'sm7325', 'dpi': '440dpi', 'resolution': '1080x2400', 'weight': 3},
    ]


    APP_VERSIONS = [
        {'version': '269.0.0.18.75', 'version_code': '314665256'},
        {'version': '268.0.0.18.75', 'version_code': '314174760'},
        {'version': '267.0.0.17.75', 'version_code': '313684264'},
        {'version': '266.0.0.19.75', 'version_code': '313193768'},
        {'version': '265.0.0.19.75', 'version_code': '312703272'},
    ]


    ANDROID_VERSIONS = [
        {'api': 33, 'release': '13.0'},
        {'api': 32, 'release': '12.0'},
        {'api': 31, 'release': '12.0'},
        {'api': 30, 'release': '11.0'},
        {'api': 29, 'release': '10.0'},
        {'api': 28, 'release': '9.0'},
    ]

    def __init__(self, config=None):
        self.current_fingerprint = None
        self.generation_count = 0
        self.config = config

    def generate(self, force_new=False):
        """Generate a new realistic device fingerprint"""
        import random


        if not force_new and self.config:
            existing_fp = self.config.get('device_fingerprint', {})
            if existing_fp and existing_fp.get('user_agent'):

                self.current_fingerprint = existing_fp
                return existing_fp


        if self.current_fingerprint and not force_new:
            return self.current_fingerprint


        devices = self.DEVICES
        weights = [d['weight'] for d in devices]
        device = random.choices(devices, weights=weights, k=1)[0].copy()



        if device['weight'] <= 6:
            android = random.choice(self.ANDROID_VERSIONS[:4])
        elif device['weight'] <= 10:
            android = random.choice(self.ANDROID_VERSIONS[2:])
        else:
            android = random.choice(self.ANDROID_VERSIONS[3:])


        app = random.choices(self.APP_VERSIONS, weights=[5, 4, 3, 2, 1], k=1)[0]


        fingerprint = {
            'app_version': app['version'],
            'android_version': android['api'],
            'android_release': android['release'],
            'dpi': device['dpi'],
            'resolution': device['resolution'],
            'manufacturer': device['manufacturer'],
            'device': device['device'],
            'model': device['model'],
            'cpu': device['cpu'],
            'version_code': app['version_code']
        }


        user_agent = (
            f"Instagram {app['version']} Android "
            f"({android['api']}/{android['release']}; {device['dpi']}; "
            f"{device['resolution']}; {device['manufacturer']}; "
            f"{device['model']}; {device['device']}; {device['cpu']}; en_US; {app['version_code']})"
        )

        fingerprint['user_agent'] = user_agent

        self.current_fingerprint = fingerprint
        self.generation_count += 1

        return fingerprint

    def rotate(self):
        """Force generate a new fingerprint (for error recovery)"""
        return self.generate(force_new=True)

    def get_display_info(self):
        """Get human-readable fingerprint info"""
        if not self.current_fingerprint:
            return "No fingerprint generated"

        fp = self.current_fingerprint
        return (f"{fp['manufacturer']} {fp['model']} | "
                f"Android {fp['android_release']} | "
                f"IG {fp['app_version']}")


class InstagramBot:
    def __init__(self, config=None):
        self.ok = False
        self.client = None
        self.username = None
        self.password = None
        self.alternative = None
        self.account_name = None
        self.otp_required = False
        self.otp_alert_sent = False
        self.consecutive_connection_errors = 0

        self.rate_limited_actions = {}


        self.config = config


        self.device_generator = DeviceFingerprintGenerator(config)


        try:
            from instagrapi import Client as InstaClient
            import warnings, logging
            warnings.filterwarnings("ignore")
            logging.getLogger("instagrapi").setLevel(logging.CRITICAL)
            self.client = InstaClient()
            self.client.delay_range = [2, 5]

            self.client.set_proxy(None)
        except ImportError:
            self.client = None
            print(f"{R}[IG] instagrapi module not installed{W}")
        except Exception as e:
            self.client = None
            print(f"{R}[IG] Failed to initialize Instagram client: {e}{W}")

    def _apply_device_fingerprint(self, client, fingerprint=None):
        """Apply device fingerprint to client"""
        if not fingerprint:
            fingerprint = self.device_generator.generate()

            if self.config is not None:
                self.config['device_fingerprint'] = fingerprint


        client.set_device({
            'app_version': fingerprint['app_version'],
            'android_version': fingerprint['android_version'],
            'android_release': fingerprint['android_release'],
            'dpi': fingerprint['dpi'],
            'resolution': fingerprint['resolution'],
            'manufacturer': fingerprint['manufacturer'],
            'device': fingerprint['device'],
            'model': fingerprint['model'],
            'cpu': fingerprint['cpu'],
            'version_code': fingerprint['version_code']
        })


        client.set_user_agent(fingerprint['user_agent'])

        return fingerprint

    def _save_session_with_fingerprint(self, session_file, fingerprint):
        """Save session and store device fingerprint in both session file and config"""
        import json


        self.client.dump_settings(session_file)


        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)


            session_data['device_fingerprint'] = fingerprint


            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
        except Exception as e:

            pass


        try:
            if hasattr(self, 'config'):
                self.config['device_fingerprint'] = fingerprint

                from automation_core import save_config
                save_config(self.config)
                print(f"{G}[IG] Device fingerprint saved to config{W}")
        except Exception as e:
            pass

    def _load_fingerprint_from_session(self, session_file):
        """Load device fingerprint from session file or config"""
        import json


        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)

            if 'device_fingerprint' in session_data:
                fingerprint = session_data['device_fingerprint']
                self.device_generator.current_fingerprint = fingerprint
                return fingerprint
        except Exception:
            pass


        try:
            if hasattr(self, 'config') and 'device_fingerprint' in self.config:
                fingerprint = self.config['device_fingerprint']
                self.device_generator.current_fingerprint = fingerprint
                print(f"{C}[IG] Loaded device fingerprint from config{W}")
                return fingerprint
        except Exception:
            pass

        return None

    def _is_connection_error(self, error_msg):
        """Detect if error is a network/connection issue (recoverable without OTP)"""
        connection_keywords = [
            'max retries exceeded',
            'httpsconnectionpool',
            'httpconnectionpool',
            'connectionerror',
            'connection refused',
            'connection reset',
            'connection aborted',
            'timeout',
            'timeouterror',
            'read timed out',
            'connect timed out',
            'network is unreachable',
            'temporary failure',
            'name resolution',
            'getaddrinfo failed',
            'ssl: wrong_version_number',
            'ssl: certificate_verify_failed',
            'remotedisconnected',
            'connectionreseterror',
            'brokenpipeerror',
        ]
        error_lower = error_msg.lower()
        return any(keyword in error_lower for keyword in connection_keywords)

    def _is_otp_error(self, error_msg):
        """Detect if error is OTP/verification related (NOT connection errors)"""

        if self._is_connection_error(error_msg):
            return False

        otp_keywords = [
            'challenge_required',
            'checkpoint_required',
            'checkpoint_challenge_required',
            'two_factor_required',
            'security code',
            'verification code',
            'confirm your identity',
            'suspicious activity',
            'verify your account',
            'security check',
            'challengeresolve',
            'submit_phone',
            'send you an email',
            'help you get back',
            'verify it\'s you',
            'unusual activity'
        ]
        error_lower = error_msg.lower()
        return any(keyword in error_lower for keyword in otp_keywords)

    def _is_critical_error(self, error_msg):
        """Detect if error is critical and makes account unusable (NOT connection errors)"""

        if self._is_connection_error(error_msg):
            return False

        critical_keywords = [
            'challenge_required',
            'checkpoint_required',
            'challengeresolve',
            'submit_phone',
            'two_factor_required',
            'account_disabled',
            'account_banned',
            'login_required',
            'consent_required',
            'feedback_required',
            'action_blocked',
            'sentry_block',
            'please wait a few minutes'
        ]
        error_lower = error_msg.lower()
        return any(keyword in error_lower for keyword in critical_keywords)

    def _get_error_type(self, error_msg):
        """Determine error type for better categorization"""
        error_lower = error_msg.lower()

        if 'submit_phone' in error_lower or 'phone' in error_lower:
            return "Phone Verification Required"
        elif 'challenge_required' in error_lower or 'challengeresolve' in error_lower:
            return "Challenge/Captcha Required"
        elif 'checkpoint_required' in error_lower:
            return "Checkpoint Required"
        elif 'two_factor' in error_lower:
            return "2FA Required"
        elif 'feedback_required' in error_lower:
            return "Feedback Required (Rate Limited)"
        elif 'action_blocked' in error_lower:
            return "Action Blocked (Spam Detection)"
        elif 'sentry_block' in error_lower:
            return "Sentry Block (Account Flagged)"
        elif 'account_disabled' in error_lower or 'account_banned' in error_lower:
            return "Account Disabled/Banned"
        elif 'login_required' in error_lower:
            return "Login Required (Session Expired)"
        elif 'consent_required' in error_lower:
            return "Consent Required"
        elif 'please wait' in error_lower:
            return "Rate Limited (Wait Required)"
        else:
            return "Unknown Error"

    def clear_error_state_on_success(self):
        """Clear error flags when an action succeeds - call after successful task"""
        if self.otp_required:
            print(f"{G}[IG] ✓ Clearing OTP flag - action succeeded, verification complete{W}")
            self.otp_required = False
            self.otp_alert_sent = False
        self.consecutive_connection_errors = 0

    def _send_error_alert(self, error_msg, task_type="Unknown"):
        """Send error alert to Telegram with account credentials"""
        print(f"{C}[IG] _send_error_alert called: account_name={self.account_name}, task_type={task_type}{W}")

        if not self.account_name:
            print(f"{Y}[IG] No account_name, skipping alert{W}")
            return


        if self._is_connection_error(error_msg):
            print(f"{Y}[IG] Connection error, skipping Telegram alert{W}")
            return


        is_critical = self._is_critical_error(error_msg)
        print(f"{C}[IG] Error critical check: {is_critical}{W}")
        if not is_critical:
            print(f"{Y}[IG] Not a critical error, skipping alert{W}")
            return


        if self.otp_alert_sent:
            print(f"{Y}[IG] Alert already sent this session, skipping{W}")
            return

        error_type = self._get_error_type(error_msg)


        username_display = self.username or "N/A"
        password_display = self.password or "N/A"
        alt_display = f"\n<b>Alternative:</b> {self.alternative}" if self.alternative else ""


        if "Phone Verification" in error_type:
            message = f"""<b>📱 Instagram PHONE VERIFICATION Required</b>

<b>Account:</b> {self.account_name}
<b>Username/Email:</b> <code>{username_display}</code>
<b>Password:</b> <code>{password_display}</code>{alt_display}

<b>Error Type:</b> {error_type}
<b>Task Type:</b> {task_type}

<b>Error Details:</b>
{error_msg[:300]}

<b>🚨 CRITICAL Action Required:</b>
1. Login via Instagram app/browser
2. Instagram akan minta NOMOR HP untuk verifikasi
3. Submit nomor HP yang valid
4. Verifikasi dengan SMS code
5. Setelah selesai, bot akan normal lagi

<b>Note:</b> IG tasks untuk akun ini akan di-skip sampai verifikasi selesai."""
        elif "Rate Limited" in error_type or "Action Blocked" in error_type:
            message = f"""<b>⚠️ Instagram Rate Limit / Action Blocked</b>

<b>Account:</b> {self.account_name}
<b>Username/Email:</b> <code>{username_display}</code>
<b>Password:</b> <code>{password_display}</code>{alt_display}

<b>Error Type:</b> {error_type}
<b>Task Type:</b> {task_type}

<b>Error Details:</b>
{error_msg[:300]}

<b>Action:</b>
- Akun akan otomatis di-skip untuk beberapa jam
- Bot akan retry otomatis setelah cooldown
- Jika terus terjadi, coba login manual dan verifikasi akun

<b>Note:</b> IG tasks sementara di-skip, VK tasks tetap jalan."""
        else:
            message = f"""<b>🔐 Instagram Account Issue Detected</b>

<b>Account:</b> {self.account_name}
<b>Username/Email:</b> <code>{username_display}</code>
<b>Password:</b> <code>{password_display}</code>{alt_display}

<b>Error Type:</b> {error_type}
<b>Task Type:</b> {task_type}

<b>Error Details:</b>
{error_msg[:300]}

<b>⚠️ Action Required:</b>
1. Login manual via Instagram app/browser
2. Selesaikan verifikasi yang diminta
3. Bot akan otomatis retry setelah issue resolved

<b>Note:</b> IG tasks untuk akun ini akan di-skip sampai issue selesai."""


        try:
            import urllib.request
            import urllib.parse


            TELEGRAM_BOT_TOKEN = "8442831261:AAEooy7Aeq_AlSGk3r-B46O_005xmNjhW-c"
            TELEGRAM_CHAT_ID = "7976183288"

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urllib.parse.urlencode({
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }).encode('utf-8')

            print(f"{C}[IG] Sending Telegram alert...{W}")
            req = urllib.request.Request(url, data=data)
            response = urllib.request.urlopen(req, timeout=10)
            result = response.read().decode('utf-8')
            print(f"{G}[IG] ✓ Error alert sent to Telegram ({error_type}){W}")
            print(f"{C}[IG] Telegram API response: {result[:100]}{W}")

            self.otp_alert_sent = True
        except Exception as e:
            print(f"{R}[IG] ✗ Could not send error alert: {e}{W}")
            import traceback
            traceback.print_exc()

    def login(self, user, pwd, alternative=None, account_name=None):
        """
        Login to Instagram with fallback support
        Args:
            user: primary username/email
            pwd: password
            alternative: alternative username/email for fallback
            account_name: account name for OTP alerts
        """
        if not self.client:
            print(f"{R}[IG] Client not initialized{W}")
            return False


        self.username = user
        self.password = pwd
        self.alternative = alternative
        self.account_name = account_name


        clean_id = user.replace('@', '_at_').replace('.', '_')
        session_filename = f"ig_session_{clean_id}.json"


        if account_name:

            session_file = os.path.join('accounts', account_name, session_filename)
            if not os.path.exists(session_file):

                session_file = os.path.join('test', account_name, session_filename)
            if not os.path.exists(session_file):
                session_file = session_filename
        else:
            session_file = session_filename


        if self.config and self.config.get('instagram', {}).get('session_data'):
            session_data = self.config['instagram']['session_data']
            print(f"{C}[IG] Found embedded session_data in config{W}")
            try:

                if 'device_settings' in session_data:
                    dev = session_data['device_settings']
                    self.client.set_device({
                        'app_version': dev.get('app_version', '269.0.0.18.75'),
                        'android_version': dev.get('android', 33),
                        'android_release': dev.get('release', '13.0'),
                        'dpi': dev.get('dpi', '420dpi'),
                        'resolution': dev.get('resolution', '1080x2340'),
                        'manufacturer': dev.get('manufacturer', 'Samsung'),
                        'device': dev.get('device', 'SM-S901B'),
                        'model': dev.get('model', 'Galaxy S22'),
                        'cpu': dev.get('cpu', 'exynos2200'),
                        'version_code': dev.get('version_code', '315174760')
                    })
                if 'user_agent' in session_data:
                    self.client.set_user_agent(session_data['user_agent'])


                self.client.set_settings(session_data)


                try:
                    self.client.get_timeline_feed()
                    print(f"{G}[IG] ✓ Session from config valid, logged in as {user}{W}")
                    self.ok = True
                    return True
                except Exception as test_err:
                    print(f"{Y}[IG] Embedded session expired: {str(test_err)[:60]}{W}")

            except Exception as e:
                print(f"{Y}[IG] Failed to load embedded session: {str(e)[:60]}{W}")


        if os.path.exists(session_file):
            print(f"{C}[IG] Loading session: {session_file}{W}")
            try:

                saved_fingerprint = self._load_fingerprint_from_session(session_file)


                if saved_fingerprint:
                    self._apply_device_fingerprint(self.client, saved_fingerprint)
                    print(f"{C}[IG] Using saved device fingerprint{W}")
                else:
                    self._apply_device_fingerprint(self.client)
                    print(f"{Y}[IG] No saved device, generated new{W}")


                self.client.load_settings(session_file)


                try:
                    self.client.get_timeline_feed()
                    print(f"{G}[IG] Session valid, logged in as {user}{W}")
                    self.ok = True
                    return True
                except Exception as validate_err:
                    print(f"{Y}[IG] Session validation failed: {str(validate_err)[:60]}{W}")

                    if not pwd:
                        print(f"{R}[IG] Session expired and no password for re-login{W}")
                        return False
                    raise
            except Exception as e:
                session_error = str(e)
                print(f"{Y}[IG] Session expired: {session_error[:80]}{W}")


                saved_fingerprint = self._load_fingerprint_from_session(session_file)









        saved_fingerprint = None
        if os.path.exists(session_file):
            saved_fingerprint = self._load_fingerprint_from_session(session_file)


        if saved_fingerprint:
            fingerprint = saved_fingerprint
            self._apply_device_fingerprint(self.client, fingerprint)
            print(f"{C}[IG] Reusing existing device for re-login{W}")
        else:
            fingerprint = self._apply_device_fingerprint(self.client)
            print(f"{Y}[IG] No saved device found, generated new (first login){W}")


        print(f"{C}[IG] Logging in as {user}...{W}")
        try:
            self.client.login(user, pwd)
            self._save_session_with_fingerprint(session_file, fingerprint)
            print(f"{G}[IG] ✓ Login success with primary credential{W}")
            self.ok = True
            self.otp_required = False
            self.otp_alert_sent = False
            self.consecutive_connection_errors = 0
            return True
        except Exception as e:
            error_msg = str(e)
            print(f"{R}[IG] ✗ Primary login failed: {error_msg[:100]}{W}")


            needs_new_device = any(keyword in error_msg.lower() for keyword in [
                'checkpoint_required',
                'challenge_required',
                'device_id',
                'suspicious',
                'challenge resolve'
            ])

            if needs_new_device:
                print(f"{Y}[IG] Error requires new device, rotating fingerprint...{W}")
                fingerprint = self.device_generator.rotate()
                self._apply_device_fingerprint(self.client, fingerprint)


                try:
                    self.client.login(user, pwd)
                    self._save_session_with_fingerprint(session_file, fingerprint)
                    print(f"{G}[IG] ✓ Login success with new device{W}")
                    self.ok = True
                    self.otp_required = False
                    self.otp_alert_sent = False
                    self.consecutive_connection_errors = 0
                    return True
                except Exception as retry_err:
                    error_msg = str(retry_err)
                    print(f"{R}[IG] ✗ Retry with new device also failed: {error_msg[:100]}{W}")


            if self._is_otp_error(error_msg):
                print(f"{Y}[IG] ⚠ OTP/Verification required!{W}")
                self.otp_required = True

                self._send_error_alert(error_msg, task_type="Instagram Login")


            if alternative:
                print(f"{Y}[IG] Trying alternative credential: {alternative}{W}")
                try:

                    from instagrapi import Client as InstaClient
                    import warnings, logging
                    warnings.filterwarnings("ignore")
                    logging.getLogger("instagrapi").setLevel(logging.CRITICAL)

                    alt_client = InstaClient()
                    alt_client.delay_range = [2, 5]


                    clean_alt_id = alternative.replace('@', '_at_').replace('.', '_')
                    alt_session_file = f"ig_session_{clean_alt_id}.json"
                    alt_saved_fingerprint = None

                    if os.path.exists(alt_session_file):
                        alt_saved_fingerprint = self._load_fingerprint_from_session(alt_session_file)


                    if alt_saved_fingerprint:
                        alt_fingerprint = alt_saved_fingerprint
                        self._apply_device_fingerprint(alt_client, alt_fingerprint)
                        print(f"{C}[IG] Using saved device for alternative credential{W}")
                    else:
                        alt_fingerprint = self.device_generator.rotate()
                        self._apply_device_fingerprint(alt_client, alt_fingerprint)
                        print(f"{Y}[IG] Generated new device for alternative credential{W}")

                    alt_client.login(alternative, pwd)


                    original_client = self.client
                    self.client = alt_client
                    self._save_session_with_fingerprint(alt_session_file, alt_fingerprint)


                    self.username = alternative
                    print(f"{G}[IG] ✓ Login success with alternative credential{W}")
                    self.ok = True
                    return True
                except Exception as e2:
                    print(f"{R}[IG] ✗ Alternative login also failed: {str(e2)[:100]}{W}")
                    self.client = original_client
                    return False
            else:
                return False

    def _attempt_relogin(self, force_new_device=False):
        """Attempt to re-login when session becomes invalid"""

        has_session_data = self.config and self.config.get('instagram', {}).get('session_data')
        if not self.username or (not self.password and not has_session_data):
            print(f"{R}[IG] Cannot re-login: no username/password and no session_data{W}")
            return False

        print(f"{Y}[IG] Attempting re-login due to connection error...{W}")


        if has_session_data and not force_new_device:
            try:
                from instagrapi import Client as InstaClient
                import warnings, logging
                warnings.filterwarnings("ignore")
                logging.getLogger("instagrapi").setLevel(logging.CRITICAL)

                new_client = InstaClient()
                new_client.delay_range = [2, 5]
                new_client.set_proxy(None)

                session_data = self.config['instagram']['session_data']


                if 'device_settings' in session_data:
                    dev = session_data['device_settings']
                    new_client.set_device({
                        'app_version': dev.get('app_version', '269.0.0.18.75'),
                        'android_version': dev.get('android', 33),
                        'android_release': dev.get('release', '13.0'),
                        'dpi': dev.get('dpi', '420dpi'),
                        'resolution': dev.get('resolution', '1080x2340'),
                        'manufacturer': dev.get('manufacturer', 'Samsung'),
                        'device': dev.get('device', 'SM-S901B'),
                        'model': dev.get('model', 'Galaxy S22'),
                        'cpu': dev.get('cpu', 'exynos2200'),
                        'version_code': dev.get('version_code', '315174760')
                    })
                if 'user_agent' in session_data:
                    new_client.set_user_agent(session_data['user_agent'])

                new_client.set_settings(session_data)
                new_client.get_timeline_feed()

                self.client = new_client
                self.ok = True
                print(f"{G}[IG] ✓ Re-login with embedded session_data successful{W}")
                return True
            except Exception as e:
                print(f"{Y}[IG] Embedded session_data re-login failed: {str(e)[:60]}{W}")



        if not self.password:
            print(f"{R}[IG] Cannot re-login: no password and session_data failed{W}")
            return False


        self.ok = False


        try:
            from instagrapi import Client as InstaClient
            import warnings, logging
            warnings.filterwarnings("ignore")
            logging.getLogger("instagrapi").setLevel(logging.CRITICAL)

            new_client = InstaClient()
            new_client.delay_range = [2, 5]
            new_client.set_proxy(None)


            if force_new_device:

                print(f"{Y}[IG] Forced device rotation (recovery mode){W}")
                new_fingerprint = self.device_generator.rotate()
            else:

                clean_id = self.username.replace('@', '_at_').replace('.', '_')
                session_file = f"ig_session_{clean_id}.json"

                saved_fingerprint = None
                if os.path.exists(session_file):
                    saved_fingerprint = self._load_fingerprint_from_session(session_file)

                if saved_fingerprint:
                    new_fingerprint = saved_fingerprint
                    print(f"{C}[IG] Reusing saved device for re-login{W}")
                else:

                    new_fingerprint = self.device_generator.generate()
                    print(f"{Y}[IG] Using current device for re-login{W}")

            self._apply_device_fingerprint(new_client, new_fingerprint)


            try:
                new_client.login(self.username, self.password)
                clean_id = self.username.replace('@', '_at_').replace('.', '_')
                session_file = f"ig_session_{clean_id}.json"


                original_client = self.client
                self.client = new_client
                self._save_session_with_fingerprint(session_file, new_fingerprint)

                self.ok = True
                self.otp_required = False
                self.otp_alert_sent = False
                self.consecutive_connection_errors = 0
                print(f"{G}[IG] ✓ Re-login successful{W}")
                return True
            except Exception as e1:
                error_msg = str(e1)


                if self._is_otp_error(error_msg):
                    print(f"{Y}[IG] ⚠ OTP/Verification required on re-login!{W}")
                    self.otp_required = True

                    self._send_error_alert(error_msg, task_type="Instagram Re-Login")
                    return False


                if self.alternative:
                    print(f"{Y}[IG] Trying re-login with alternative...{W}")


                    clean_alt_id = self.alternative.replace('@', '_at_').replace('.', '_')
                    alt_session_file = f"ig_session_{clean_alt_id}.json"
                    alt_saved_fingerprint = None

                    if os.path.exists(alt_session_file):
                        alt_saved_fingerprint = self._load_fingerprint_from_session(alt_session_file)


                    if alt_saved_fingerprint and not force_new_device:
                        alt_fingerprint = alt_saved_fingerprint
                        print(f"{C}[IG] Using saved device for alternative credential{W}")
                    else:

                        alt_fingerprint = self.device_generator.rotate()
                        print(f"{Y}[IG] Generated new device for alternative credential{W}")

                    self._apply_device_fingerprint(new_client, alt_fingerprint)

                    new_client.login(self.alternative, self.password)

                    self.client = new_client
                    self._save_session_with_fingerprint(alt_session_file, alt_fingerprint)

                    self.username = self.alternative
                    self.ok = True
                    self.otp_required = False
                    self.otp_alert_sent = False
                    self.consecutive_connection_errors = 0
                    print(f"{G}[IG] ✓ Re-login with alternative successful{W}")
                    return True
                raise e1
        except Exception as e:
            error_msg = str(e)
            print(f"{R}[IG] ✗ Re-login failed: {error_msg[:100]}{W}")


            if self._is_otp_error(error_msg):
                print(f"{Y}[IG] ⚠ OTP/Verification detected in re-login error{W}")
                self.otp_required = True

                self._send_error_alert(error_msg, task_type="Instagram Re-Login")

            return False

    def follow(self, username, retry_count=0):
        if not self.ok:
            return "ERROR: Not logged in"


        if 'follow' in self.rate_limited_actions:
            if time.time() < self.rate_limited_actions['follow']:
                remaining = int((self.rate_limited_actions['follow'] - time.time()) / 60)
                return f"ERROR: Follow rate limited (wait {remaining} minutes)"
            else:
                del self.rate_limited_actions['follow']

        try:
            clean_username = username.lstrip('@')
            uid = self.client.user_id_from_username(clean_username)
            self.client.user_follow(uid)
            self.clear_error_state_on_success()
            return True
        except Exception as e:
            error_msg = str(e)





            if 'not found' in error_msg.lower() or 'User not found' in error_msg:
                return f"ERROR: User @{username} not found"

            if 'feedback_required' in error_msg or 'action_blocked' in error_msg:
                self.rate_limited_actions['follow'] = time.time() + (2 * 60 * 60)
                return "ERROR: feedback_required - rate limited"


            return f"ERROR: {error_msg[:100]}"

    def _extract_media_pk_fallback(self, shortcode):
        """Fallback method to extract media PK using web scraping when API fails"""
        try:


            try:
                import json
                url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis"
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json'
                }


                if hasattr(self.client, 'private') and hasattr(self.client.private, 'get'):
                    response = self.client.private.get(url, headers=headers)
                    data = response.json()


                    if 'items' in data and len(data['items']) > 0:
                        media_id = str(data['items'][0].get('pk', ''))
                        if media_id:
                            print(f"{G}[IG] ✓ Extracted media ID from web API{W}")
                            return media_id
                    elif 'graphql' in data:
                        media = data.get('graphql', {}).get('shortcode_media', {})
                        media_id = media.get('id', '')
                        if media_id:
                            print(f"{G}[IG] ✓ Extracted media ID from GraphQL{W}")
                            return media_id
            except Exception as web_err:

                print(f"{Y}[IG] Web API unavailable, using shortcode conversion...{W}")



            alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'
            media_id = 0
            for char in shortcode:
                media_id = media_id * 64 + alphabet.index(char)

            converted_id = str(media_id)
            print(f"{G}[IG] ✓ Converted shortcode to media ID: {converted_id}{W}")
            return converted_id

        except Exception as e:
            print(f"{R}[IG] Fallback extraction failed: {str(e)[:80]}{W}")
            return None

    def like(self, url, retry_count=0):
        if not self.ok:
            return "ERROR: Not logged in"


        if 'like' in self.rate_limited_actions:
            if time.time() < self.rate_limited_actions['like']:
                remaining = int((self.rate_limited_actions['like'] - time.time()) / 60)
                return f"ERROR: Like rate limited (wait {remaining} minutes)"
            else:
                del self.rate_limited_actions['like']

        try:
            m = re.search(r'/(p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if m:
                shortcode = m.group(2)
                media_pk = self.client.media_pk_from_code(shortcode)
                self.client.media_like(media_pk)
                self.clear_error_state_on_success()
                return True
            return "ERROR: Could not parse media code from URL"
        except Exception as e:
            error_msg = str(e)


            if 'not found' in error_msg.lower() or '404' in error_msg:
                return "ERROR: Media not found"

            if 'feedback_required' in error_msg or 'action_blocked' in error_msg:
                self.rate_limited_actions['like'] = time.time() + (2 * 60 * 60)
                return "ERROR: feedback_required - rate limited"

            return f"ERROR: {error_msg[:100]}"

    def comment(self, url, text, retry_count=0):
        if not self.ok:
            return "ERROR: Not logged in"


        if 'comment' in self.rate_limited_actions:
            if time.time() < self.rate_limited_actions['comment']:
                remaining = int((self.rate_limited_actions['comment'] - time.time()) / 60)
                return f"ERROR: Comment rate limited (wait {remaining} minutes)"
            else:
                del self.rate_limited_actions['comment']

        try:
            m = re.search(r'/(p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if m:
                shortcode = m.group(2)
                media_pk = self.client.media_pk_from_code(shortcode)
                c = self.client.media_comment(media_pk, text)
                if c:
                    self.clear_error_state_on_success()
                return str(c.pk) if c else None
            return "ERROR: Could not parse media code from URL"
        except Exception as e:
            error_msg = str(e)


            if 'not found' in error_msg.lower() or '404' in error_msg:
                return "ERROR: Media not found"

            if 'feedback_required' in error_msg or 'action_blocked' in error_msg:
                self.rate_limited_actions['comment'] = time.time() + (2 * 60 * 60)
                return "ERROR: feedback_required - rate limited"

            return f"ERROR: {error_msg[:100]}"


class VKSerfingBot:
    def __init__(self, config, account_name=None, quiet_mode=True):
        self.config = config
        self.account_name = account_name
        self.quiet_mode = quiet_mode
        self.base = "https://vkserfing.ru"
        self.domains = ["https://vkserfing.ru", "https://vkserfing.com"]
        self.current_domain_index = 0
        self.session = requests.Session()
        self.balance = 0.0
        self.earned = 0.0
        self.completed_tasks = 0
        self.failed_tasks = 0
        self.server_accounts = {}
        self.server_email = ""
        self.registration_date = ""
        self.registration_timestamp = 0
        self.has_vk_account = False
        self.has_ig_account = False
        self.has_tg_account = False
        self.has_tiktok_account = False
        self.cookies_expired = False
        self.auto_login_attempts = 0


        self.task_type_errors = {}
        self.task_type_skip = set()


        self.is_banned = False


        self.vk_account_blocked = False


        self.allow_direct = False
        proxy_string = config.get('proxy', {}).get('proxy_string', '')


        used_proxy_ips = get_all_used_proxies()


        self.smart_proxy = SmartProxyManager(
            account_name=account_name or "unknown",
            initial_proxy=proxy_string,
            error_threshold=3,
            max_rotations=10,
            exclude_ips=used_proxy_ips
        )


        self.proxy_manager = ProxyManager(
            initial_proxy_string=proxy_string,
            max_retries=1,
            test_timeout=10,
            max_proxy_attempts=100
        )


        if proxy_string:
            success, ip_info = self.smart_proxy.test_proxy(timeout=10)
            if success:
                self.proxy_info = ip_info
                proxy_dict = self.smart_proxy.get_proxy()
                self.session.proxies.update({
                    'http': proxy_dict['http'],
                    'https': proxy_dict['https']
                })
            else:

                if self.smart_proxy.rotate_now("initial proxy test failed"):
                    proxy_dict = self.smart_proxy.get_proxy()
                    if proxy_dict:
                        self.session.proxies.update({
                            'http': proxy_dict['http'],
                            'https': proxy_dict['https']
                        })
                        info = self.smart_proxy.get_proxy_info()
                        self.proxy_info = {'ip': info['ip']}
                else:
                    raise Exception(f"PROXY_REQUIRED: All proxies failed for {account_name}")
        else:

            if self.smart_proxy.rotate_now("no proxy configured"):
                proxy_dict = self.smart_proxy.get_proxy()
                if proxy_dict:
                    self.session.proxies.update({
                        'http': proxy_dict['http'],
                        'https': proxy_dict['https']
                    })
                    info = self.smart_proxy.get_proxy_info()
                    self.proxy_info = {'ip': info['ip']}


                    config['proxy'] = {
                        'proxy_string': proxy_dict['raw'],
                        'ip': info['ip'],
                        'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
            else:
                raise Exception(f"PROXY_REQUIRED: No proxy available for {account_name}")


        if config.get('user_agent', {}).get('user_agent'):
            self.user_agent_data = config['user_agent']
        else:
            self.user_agent_data = UserAgentGenerator.generate()
            config['user_agent'] = self.user_agent_data


        cookies = config.get('credentials', {}).get('cookies', {})
        for k, v in cookies.items():
            if k != 'xsrf_token' and v:
                self.session.cookies.set(k, v, domain='.vkserfing.ru')


        xsrf_token = (
            config.get('credentials', {}).get('xsrf_token') or
            cookies.get('xsrf_token') or
            ''
        )


        user_agent = self.user_agent_data.get('user_agent', 'Mozilla/5.0 (Linux; Android 10) Chrome/142.0.0.0 Mobile Safari/537.36')

        self.session.headers.update({
            'User-Agent': user_agent,
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json',
            'X-XSRF-Token': xsrf_token,
            'X-Requested-With': 'XMLHttpRequest',
        })


        self.request_manager = AccountRequestManager(
            account_name=account_name or "unknown",
            session=self.session,
            smart_proxy=self.smart_proxy,
            config=config
        )

        self.vk = None
        self.vk_api_enabled = False
        vk = config.get('vk_api', {})
        if VK_AVAILABLE and vk.get('enabled'):
            try:

                primary_token = vk.get('access_token') or config.get('vk_token')
                alternative_token = vk.get('alternative_token') or config.get('vk_alternative_token')

                self.vk = VKApi(
                    access_token=primary_token,
                    user_id=vk['user_id'],
                    alternative_token=alternative_token
                )
                self.vk_api_enabled = True
            except: pass

        self.ig = None
        self.instagram_enabled = False
        ig = config.get('instagram', {})
        if ig.get('enabled'):
            self.ig = InstagramBot(config)

            alternative = ig.get('alternative')
            if self.ig.client:
                login_success = self.ig.login(ig['username'], ig['password'], alternative=alternative, account_name=self.account_name)
                if login_success:
                    self.instagram_enabled = True
                elif self.ig.otp_required:
                    self.instagram_enabled = True

        self.tg = None
        self.tg_client = None
        self.telegram_enabled = False
        
        # Load telegram blacklist
        self._tg_blacklist = set()
        self._load_telegram_blacklist()

        tg_config = config.get('telegram', {})


        has_session_string = tg_config.get('session_string') and tg_config.get('session_string') != 'null'
        has_session_file = tg_config.get('session') and tg_config.get('session') != 'null'
        is_bound = tg_config.get('bound', False)

        if is_bound and (has_session_string or has_session_file):
            self.telegram_enabled = True
            self.tg = self
            print(f"  {G}✓ Telegram enabled (session type: {'string' if has_session_string else 'file'}){W}")
        elif TG_AVAILABLE:
            try:
                self.tg = TelegramWrapper()
                self.telegram_enabled = self.tg.is_available()
            except: pass
    
    def _load_telegram_blacklist(self):
        """Load telegram blacklist from config file"""
        try:
            import os, json
            blacklist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'telegram_blacklist.json')
            if os.path.exists(blacklist_path):
                with open(blacklist_path, 'r') as f:
                    data = json.load(f)
                    self._tg_blacklist = set(data.get('blacklisted_usernames', []))
        except:
            self._tg_blacklist = set()
    
    def _save_telegram_blacklist(self):
        """Save telegram blacklist to config file"""
        try:
            import os, json
            blacklist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'telegram_blacklist.json')
            with open(blacklist_path, 'w') as f:
                json.dump({'blacklisted_usernames': sorted(list(self._tg_blacklist))}, f, indent=2)
        except Exception as e:
            print(f"{Y}⚠ Failed to save blacklist: {str(e)[:40]}{W}")

    def _tg_reconnect(self):
        """Reconnect Telegram client on session error"""
        try:
            if hasattr(self, 'tg_client') and self.tg_client:
                self.tg_client.disconnect()
            tg_config = self.config.get('telegram', {})
            session_string = tg_config.get('session_string')
            if session_string:
                from telethon.sync import TelegramClient
                from telethon.sessions import StringSession
                api_id = tg_config.get('api_id', 1724399)
                api_hash = tg_config.get('api_hash', '7f6c4af5220db320413ff672093ee102')
                self.tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)
                self.tg_client.connect()
                return True
        except:
            pass
        return False

    def _try_ig_relogin(self):
        """Try to relogin Instagram - DISABLED to prevent OTP triggers"""



        print(f"  {Y}[IG] Skipping re-login (prevents OTP trigger){W}")
        return False

    def _ensure_tg_client(self):
        """Lazy init telegram client when needed - support both session_string and session file with auto-fallback"""
        if hasattr(self, 'tg_client') and self.tg_client and self.tg_client.is_connected():
            return True

        tg_config = self.config.get('telegram', {})

        session_string = tg_config.get('session_string')
        session_file = tg_config.get('session')

        if not session_string and not session_file:
            return False

        try:
            import asyncio
            # Fix: Create event loop for thread
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())
            
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession
            api_id = int(tg_config.get('api_id', 1724399))
            api_hash = tg_config.get('api_hash', '7f6c4af5220db320413ff672093ee102')

            # Try session string first
            if session_string:
                try:
                    self.tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)
                    self.tg_client.connect()
                    if self.tg_client.is_user_authorized():
                        return True
                    
                    # String session invalid, try fallback
                    print(f"{Y}⚠ TG string session invalid, trying fallback...{W}")
                    self.tg_client.disconnect()
                    self.tg_client = None
                except Exception as e:
                    print(f"{Y}⚠ TG string session error: {str(e)[:40]}{W}")
                    if hasattr(self, 'tg_client') and self.tg_client:
                        try: self.tg_client.disconnect()
                        except: pass
                    self.tg_client = None

            # Fallback 1: Try specified session file
            if session_file:
                try:
                    import os
                    accounts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'accounts')
                    if hasattr(self, 'account_name') and self.account_name:
                        session_dir = os.path.join(accounts_dir, self.account_name)
                    else:
                        session_dir = '.'
                    session_path = os.path.join(session_dir, session_file.replace('.session', ''))
                    
                    self.tg_client = TelegramClient(session_path, api_id, api_hash)
                    self.tg_client.connect()
                    if self.tg_client.is_user_authorized():
                        print(f"{G}✓ TG loaded from session file{W}")
                        
                        # Auto-update config with new string session
                        try:
                            new_session_string = self.tg_client.session.save()
                            self.config['telegram']['session_string'] = new_session_string
                            print(f"{C}  → Auto-updated string session in config{W}")
                        except:
                            pass
                        
                        return True
                    
                    self.tg_client.disconnect()
                    self.tg_client = None
                except Exception as e:
                    print(f"{Y}⚠ Session file error: {str(e)[:40]}{W}")
                    if hasattr(self, 'tg_client') and self.tg_client:
                        try: self.tg_client.disconnect()
                        except: pass
                    self.tg_client = None

            # Fallback 2: Auto-detect session file by account name
            if hasattr(self, 'account_name') and self.account_name:
                try:
                    import os
                    accounts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'accounts')
                    session_dir = os.path.join(accounts_dir, self.account_name)
                    
                    # Look for telegram_*.session files
                    session_files = []
                    if os.path.exists(session_dir):
                        for f in os.listdir(session_dir):
                            if f.startswith('telegram_') and f.endswith('.session'):
                                session_files.append(f)
                    
                    if session_files:
                        # Try first session file found
                        session_file = session_files[0]
                        session_path = os.path.join(session_dir, session_file.replace('.session', ''))
                        
                        print(f"{C}  → Auto-detected session file: {session_file}{W}")
                        
                        self.tg_client = TelegramClient(session_path, api_id, api_hash)
                        self.tg_client.connect()
                        if self.tg_client.is_user_authorized():
                            print(f"{G}✓ TG loaded from auto-detected session{W}")
                            
                            # Auto-update config
                            try:
                                new_session_string = self.tg_client.session.save()
                                me = self.tg_client.get_me()
                                
                                self.config['telegram']['session_string'] = new_session_string
                                self.config['telegram']['session'] = session_file
                                self.config['telegram']['user_id'] = me.id
                                self.config['telegram']['username'] = me.username or ''
                                
                                print(f"{C}  → Auto-updated config (@{me.username}){W}")
                            except:
                                pass
                            
                            return True
                        
                        self.tg_client.disconnect()
                        self.tg_client = None
                except Exception as e:
                    print(f"{Y}⚠ Auto-detect failed: {str(e)[:40]}{W}")
                    if hasattr(self, 'tg_client') and self.tg_client:
                        try: self.tg_client.disconnect()
                        except: pass
                    self.tg_client = None

            return False
            
        except Exception as e:
            print(f"{Y}⚠ TG client init: {str(e)[:40]}{W}")
            if hasattr(self, 'tg_client') and self.tg_client:
                try: self.tg_client.disconnect()
                except: pass
            self.tg_client = None
            return False

    def _disconnect_tg_client(self):
        """Disconnect Telethon to free socket"""
        if hasattr(self, 'tg_client') and self.tg_client:
            try:
                self.tg_client.disconnect()
            except:
                pass
            self.tg_client = None

    def tg_join_channel(self, channel_link):
        """Join telegram channel"""
        if not self._ensure_tg_client():
            return False

        if getattr(self, '_tg_join_flood', 0) > __import__('time').time():
            return "FLOOD"
        try:
            from telethon.tl.functions.channels import JoinChannelRequest
            if 't.me/' in channel_link:
                channel = channel_link.split('t.me/')[-1].split('/')[0].split('?')[0]
            else:
                channel = channel_link
            
            # Check blacklist first
            username = channel.replace('@', '')
            if username in self._tg_blacklist:
                return "BLACKLISTED"

            self.tg_client(JoinChannelRequest(channel))
            return True
        except Exception as e:
            err = str(e)

            # Blacklist: Invalid usernames that cause repeated errors
            if any(x in err.lower() for x in ['no user has', 'nobody is using', 'username is unoccupied']):
                # Extract username from channel if possible
                username = channel.replace('@', '').replace('https://t.me/', '')
                self._tg_blacklist.add(username)
                self._save_telegram_blacklist()
                print(f" {Y}⚠ Blacklisted: {username}{W}")
                return "BLACKLISTED"  # Special return to skip error counting
            
            # Already joined/requested
            if 'successfully requested to join' in err.lower():
                return True  # Count as success
            
            if 'wait of' in err.lower() and 'seconds' in err.lower():
                import re, time
                match = re.search(r'wait of (\d+) seconds', err.lower())
                if match:
                    self._tg_join_flood = time.time() + int(match.group(1))
                print(f" {R}TG join FloodWait - skipping joins{W}")
                return "FLOOD"
            if 'session ID' in err or 'disconnected' in err.lower():
                if self._tg_reconnect():
                    try:
                        self.tg_client(JoinChannelRequest(channel))
                        return True
                    except:
                        pass
            print(f" {R}TG join error: {err[:50]}{W}")
            return False

    def tg_view_post(self, post_link):
        """View telegram post - always try even on rate limit"""
        if not self._ensure_tg_client():
            return False
        try:
            from telethon.tl.functions.messages import GetMessagesViewsRequest
            parts = post_link.rstrip('/').split('/')
            if len(parts) >= 2:
                channel = parts[-2]
                msg_id = int(parts[-1])
                self.tg_client(GetMessagesViewsRequest(peer=channel, id=[msg_id], increment=True))
            return True
        except Exception as e:
            err = str(e)

            if 'session ID' in err or 'disconnected' in err.lower():
                if self._tg_reconnect():
                    try:
                        self.tg_client(GetMessagesViewsRequest(peer=channel, id=[msg_id], increment=True))
                        return True
                    except:
                        pass

            if 'wait of' in err.lower() and 'seconds' in err.lower():
                return True
            print(f" {R}TG view error: {err[:50]}{W}")
            return False



    def _request_with_fallback(self, method, endpoint, **kwargs):
        """
        Make request using per-account state machine.

        State progression (per account, independent):
        READY → FALLBACK_TRIED → PROXY_ROTATED → ABORTED

        - Network errors progress state forward
        - Success resets state to READY
        - ABORTED state skips all remaining requests
        """
        global STOP_FLAG
        if STOP_FLAG:
            return None


        if self.request_manager.is_aborted():
            return None


        return self.request_manager.request(method, endpoint, **kwargs)

    def _apply_proxy_to_session(self):
        """Apply current proxy - now handled by request_manager"""

        self.session = self.request_manager.session
        info = self.smart_proxy.get_proxy_info()
        self.proxy_info = {'ip': info['ip']}

    def _send_banned_account_alert(self, task_counts):
        """Send Telegram alert when account receives zero tasks (likely banned)"""
        try:
            import urllib.request
            import urllib.parse


            account_name = getattr(self, 'account_name', 'Unknown')


            vk_info = "Not connected"
            if self.vk:
                vk_info = f"Connected (id: {self.vk_user_id if hasattr(self, 'vk_user_id') else 'unknown'})"


            ig_info = "Not connected"
            if self.ig and self.ig.username:
                ig_info = f"@{self.ig.username}"


            tg_info = "Not connected"
            if self.tg:
                tg_info = "Connected"


            vks_email = getattr(self, 'server_email', 'N/A')
            vks_id = getattr(self, 'vkserfing_user_id', 'N/A')
            balance = getattr(self, 'balance', 0.0)


            task_list = "\n".join([f"  • {task_type}: {count}" for task_type, count in task_counts.items()])


            message = f"""<b>🚫 ACCOUNT POTENTIALLY BANNED</b>

<b>⚠️ Account received ZERO tasks across all types!</b>

<b>Account Info:</b>
• Name: {account_name}
• VKSerfing ID: {vks_id}
• Email: <code>{vks_email}</code>
• Balance: {balance:.2f}₽

<b>Platform Status:</b>
• VK: {vk_info}
• Instagram: {ig_info}
• Telegram: {tg_info}

<b>Task Counts (All Zero):</b>
{task_list}

<b>🔍 Possible Causes:</b>
1. VKSerfing account banned/restricted
2. Cookie/token expired and auto-relogin failed
3. Account flagged for suspicious activity
4. Temporary server-side restriction

<b>📋 Recommended Actions:</b>
1. Login to VKSerfing website manually
2. Check account status and notifications
3. Update cookies if needed
4. Contact VKSerfing support if banned

<b>Note:</b> Bot will continue with other accounts.
This account will be skipped until issue is resolved."""


            TELEGRAM_BOT_TOKEN = "8442831261:AAEooy7Aeq_AlSGk3r-B46O_005xmNjhW-c"
            TELEGRAM_CHAT_ID = "7976183288"

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urllib.parse.urlencode({
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            }).encode('utf-8')

            req = urllib.request.Request(url, data=data)
            response = urllib.request.urlopen(req, timeout=10)
            print(f"{G}✓ Banned account alert sent to Telegram{W}")
            return True
        except Exception as e:
            print(f"{Y}⚠ Could not send banned account alert: {e}{W}")
            return False

    def get_settings_info(self):
        """Fetch user settings including registration date and email"""
        try:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10) Chrome/142.0.0.0 Mobile Safari/537.36',
            }
            r = self._request_with_fallback('GET', '/settings', headers=headers)

            if r and r.status_code == 200:
                html = r.text


                time_reg_match = re.search(r'time_reg:\s*(\d+)', html)
                if time_reg_match:
                    time_reg = int(time_reg_match.group(1))

                    from datetime import datetime
                    reg_date = datetime.fromtimestamp(time_reg).strftime('%Y-%m-%d %H:%M:%S')
                    self.registration_date = reg_date
                    self.registration_timestamp = time_reg


                email_match = re.search(r'email:\s*["\']([^"\']+)["\']', html)
                if email_match:
                    self.server_email = email_match.group(1)

                return True
        except Exception as e:
            pass
        return False

    def get_accounts_info(self):
        """Fetch and parse account information from server"""
        try:
            headers = {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10) Chrome/142.0.0.0 Mobile Safari/537.36',
            }


            self.get_settings_info()

            r = self._request_with_fallback('GET', '/accounts', headers=headers)

            if r and r.status_code == 200:
                html = r.text


                email_match = re.search(r'email:\s*["\']([^"\']+)["\']', html)
                if email_match:
                    self.server_email = email_match.group(1)
                else:

                    email_match = re.search(r'name:\s*["\']([^"\'@]+@[^"\']+)["\']', html)
                    if email_match:
                        self.server_email = email_match.group(1)


                self.server_accounts = {
                    'vk': None,
                    'instagram': None,
                    'telegram': None,
                    'tiktok': None,
                }



                account_pattern = r'\{"id":"(\d+)"[^}]*"name":"([^"]+)"[^}]*"platform_id":"([^"]+)"[^}]*"platform_alias":"([^"]*)"[^}]*"platform_url":"([^"]+)"[^}]*"platform":"([^"]+)"[^}]*"status":"([^"]+)"'

                for match in re.finditer(account_pattern, html):
                    acc_id = match.group(1)
                    name = match.group(2)
                    platform_id = match.group(3)
                    platform_alias = match.group(4)
                    platform_url = match.group(5)
                    platform = match.group(6)
                    status = match.group(7)

                    if status == 'active' and platform in self.server_accounts:
                        self.server_accounts[platform] = {
                            'id': acc_id,
                            'name': name,
                            'platform_id': platform_id,
                            'platform_alias': platform_alias,
                            'platform_url': platform_url,
                        }


                self.has_vk_account = self.server_accounts['vk'] is not None
                self.has_ig_account = self.server_accounts['instagram'] is not None
                self.has_tg_account = self.server_accounts['telegram'] is not None
                self.has_tiktok_account = self.server_accounts['tiktok'] is not None


                if any(self.server_accounts.values()):
                    return True
                else:

                    print(f"  {Y}No active accounts found on server{W}")
                    return False
        except Exception as e:
            print(f"{Y}Warning: Could not fetch account info: {e}{W}")
        return False

    def validate_accounts(self):
        """Validate local config accounts against server accounts"""

        balance_str = f"{self.balance:.2f}₽" if self.balance > 0 else "-"


        email_str = self.server_email or "-"
        reg_str = self.registration_date or "-"

        vk_acc = self.server_accounts.get('vk')
        vk_str = vk_acc.get('platform_alias', '-') if vk_acc else "-"

        ig_acc = self.server_accounts.get('instagram')
        ig_str = ig_acc.get('platform_alias', '-') if ig_acc else "-"

        tele_acc = self.server_accounts.get('telegram')
        tele_str = tele_acc.get('platform_alias', '-') if tele_acc else "-"

        tiktok_acc = self.server_accounts.get('tiktok')
        tiktok_str = tiktok_acc.get('platform_alias', '-') if tiktok_acc else "-"


        print(f"\n{C}Email   :{W} {email_str}")
        print(f"{C}Reg     :{W} {reg_str}")
        print(f"{C}IG      :{W} {ig_str}")
        print(f"{C}VK      :{W} {vk_str}")
        print(f"{C}Tele    :{W} {tele_str}")
        print(f"{C}Tiktok  :{W} {tiktok_str}")
        print(f"{C}Balance :{W} {balance_str}\n")

        return True

    def refresh_xsrf_token(self) -> bool:
        """
        Refresh XSRF token + sessid by requesting homepage
        This is much simpler than full re-login!

        Returns:
            True if token refreshed, False if failed
        """
        try:

            resp = self._request_with_fallback('GET', '', timeout=30)

            if not resp:
                return False

            resp.raise_for_status()

            html = resp.text


            token_match = re.search(r'TOKEN\s*[=:]\s*["\']([^"\']+)["\']', html)

            if token_match:
                new_token = token_match.group(1)


                new_sessid = None
                for cookie in self.session.cookies:
                    if cookie.name == 'sessid':
                        new_sessid = cookie.value
                        break


                self.session.headers['X-XSRF-Token'] = new_token


                if 'credentials' not in self.config:
                    self.config['credentials'] = {}
                if 'cookies' not in self.config['credentials']:
                    self.config['credentials']['cookies'] = {}

                self.config['credentials']['xsrf_token'] = new_token
                self.config['credentials']['cookies']['xsrf_token'] = new_token

                if new_sessid:
                    self.config['credentials']['cookies']['sessid'] = new_sessid


                save_config(self.config)

                return True
            else:
                return False

        except Exception as e:
            print(f"{R}✗ Failed to refresh token: {e}{W}")
            return False

    def check_auth_response(self, response):
        """
        Check if response indicates expired/invalid token or cookies

        Returns:
            True if valid, False if need refresh
        """

        if response.status_code == 401:
            return False

        if response.status_code == 403:
            return False


        if response.status_code == 302:
            location = response.headers.get('Location', '')
            if '/auth' in location or '/login' in location:
                return False


        content_type = response.headers.get('Content-Type', '')


        if 'text/html' in content_type:

            text_lower = response.text.lower()
            if any(keyword in text_lower for keyword in ['login', 'войти', 'authorization', 'войдите']):

                if '<form' in response.text and ('password' in text_lower or 'пароль' in text_lower):
                    return False


        if 'application/json' in content_type:
            try:
                data = response.json()


                if data.get('status') == 'error':
                    error_msg = data.get('message', '').lower()

                    if any(keyword in error_msg for keyword in [
                        'unauthorized', 'auth', 'token', 'session',
                        'csrf', 'xsrf', 'войдите', 'авторизуйтесь',
                        'forbidden', 'not authorized'
                    ]):
                        return False


                if data.get('error'):
                    return False

            except:

                return False

        return True

    def auto_relogin(self) -> bool:
        """
        Try to fix authentication:
        1. First try simple XSRF token refresh (fast, no captcha needed)
        2. If that fails, try full re-login with captcha (slow)

        Returns:
            True if fixed, False otherwise
        """

        if self.auto_login_attempts >= 3:
            print(f"{R}✗ Too many attempts, giving up{W}")
            return False

        self.auto_login_attempts += 1


        print(f"\n{Y}[Step 1/2] Trying simple XSRF token refresh...{W}")
        if self.refresh_xsrf_token():

            self.auto_login_attempts = 0
            self.cookies_expired = False
            return True


        print(f"\n{Y}[Step 2/2] XSRF refresh failed, trying full re-login...{W}")
        print(f"{Y}╔═══════════════════════════════════╗{W}")
        print(f"{Y}║   Cookie Expired - Auto Re-login  ║{W}")
        print(f"{Y}╚═══════════════════════════════════╝{W}\n")


        creds = self.config.get('credentials', {})
        email = creds.get('email', '')
        password = creds.get('password', '')

        if not email or not password:
            print(f"{R}✗ Email or password not configured!{W}")
            print(f"{Y}Tip: Only XSRF token refresh (no login) is possible without credentials{W}")
            print(f"{Y}Please setup credentials in Menu 4 if you want full auto-login{W}")
            return False


        captcha_cfg = self.config.get('captcha', {})
        if not captcha_cfg.get('enabled'):
            print(f"{R}✗ Captcha solver not configured!{W}")
            print(f"{Y}Please setup captcha solver in Menu 5{W}")
            return False

        try:

            from auth_manager import VKSerfingAuth, AuthError


            auth = VKSerfingAuth(email, password, captcha_cfg)


            new_cookies = auth.auto_login()


            for name, value in new_cookies.items():
                if name != 'xsrf_token':
                    self.session.cookies.set(name, value, domain='.vkserfing.ru')


            if 'xsrf_token' in new_cookies:
                self.session.headers['X-XSRF-Token'] = new_cookies['xsrf_token']


            if 'credentials' not in self.config:
                self.config['credentials'] = {}
            self.config['credentials']['cookies'] = new_cookies


            save_config(self.config)

            print(f"\n{G}✓ Full re-login successful!{W}\n")


            self.cookies_expired = False
            self.auto_login_attempts = 0

            return True

        except AuthError as e:
            print(f"\n{R}✗ Auto-login failed: {e}{W}\n")
            return False
        except ImportError:
            print(f"\n{R}✗ auth_manager module not found!{W}")
            print(f"{Y}Make sure auth_manager.py is in the same directory{W}\n")
            return False
        except Exception as e:
            print(f"\n{R}✗ Unexpected error during auto-login: {e}{W}\n")
            import traceback
            traceback.print_exc()
            return False

    def get_balance(self):
        try:
            r = self._request_with_fallback('GET', '/cashout', headers={'X-Ajax-Html': '1'})

            if not r:
                return self.balance


            if not self.check_auth_response(r):
                print(f"{Y}⚠ Token/cookies issue detected!{W}")
                self.cookies_expired = True
                if self.auto_relogin():

                    r = self._request_with_fallback('GET', '/cashout', headers={'X-Ajax-Html': '1'})
                    if not r:
                        return self.balance
                else:
                    return self.balance

            m = re.search(r'<span>([0-9.]+)</span>', r.json().get('html', ''))
            if m: self.balance = float(m.group(1))
        except: pass
        return self.balance

    def get_tasks(self, t):

        global STOP_FLAG
        if STOP_FLAG:
            return []

        if t.startswith('instagram_'):
            ep = t.replace('instagram_', '')
            if ep == 'follower': ep = 'followers'
            elif ep == 'like': ep = 'likes'
            elif ep == 'comment': ep = 'comments'
            elif ep == 'story': ep = 'history'
            endpoint = f"/assignments/instagram/{ep}"
        elif t.startswith('telegram_'):
            ep = 'followers' if 'follower' in t else 'views'
            endpoint = f"/assignments/telegram/{ep}"
        else:

            ep = t.replace('vk_', '') if t.startswith('vk_') else t
            endpoint = f"/assignments/vk/{ep}"

        try:
            r = self._request_with_fallback('GET', endpoint, headers={'X-Ajax-Partial-Html': '1'})

            if not r:

                return None


            if r.status_code == 404:

                return None


            if not self.check_auth_response(r):
                print(f"{Y}⚠ Token/cookies issue!{W}")
                self.cookies_expired = True
                if self.auto_relogin():

                    r = self._request_with_fallback('GET', endpoint, headers={'X-Ajax-Partial-Html': '1'})
                    if not r:
                        return None
                else:
                    return None

            html = r.json().get('html', '')
            tasks = []

            for block in re.findall(r'<active-assignment[\s\S]*?>', html):
                id_match = re.search(r':id=\\?"(\d+)\\?"', block)
                if not id_match:
                    continue


                plain_link = re.search(r'plain-link=\\?"([^"]+)\\?"', block)
                link_match = re.search(r'(?<!plain-)link=\\?"([^"]+)\\?"', block)

                task_link = None
                if plain_link:
                    task_link = plain_link.group(1).replace('\\/', '/')
                elif link_match:
                    task_link = link_match.group(1).replace('\\/', '/')

                tasks.append({'id': int(id_match.group(1)), 'link': task_link, 'type': t})
            return tasks
        except Exception as e:

            return None

    def begin(self, aid, retry_after_refresh=False):
        """
        Begin a task assignment.

        ERROR HANDLING:
        - None response = network error (proxy already rotated) → return SKIP
        - HTTP 401/403 with auth message = auth error → refresh token
        - Server error message = skip task (not auth issue)
        """
        global STOP_FLAG
        if STOP_FLAG:
            return None

        try:
            r = self._request_with_fallback('POST', f"/assignments/{aid}/begin")


            if not r:
                return "SKIP"


            if r.status_code == 401:
                if not retry_after_refresh:
                    print(f" {Y}(HTTP 401 - refreshing token...){W}", end="", flush=True)
                    if self.auto_relogin():
                        return self.begin(aid, retry_after_refresh=True)
                return "SKIP"

            if r.status_code == 403:

                try:
                    text = r.text.lower()
                    if any(kw in text for kw in ['unauthorized', 'token', 'csrf', 'xsrf', 'войдите']):
                        if not retry_after_refresh:
                            print(f" {Y}(HTTP 403 auth - refreshing...){W}", end="", flush=True)
                            if self.auto_relogin():
                                return self.begin(aid, retry_after_refresh=True)
                        return "SKIP"
                except:
                    pass

                return "SKIP"


            try:
                data = r.json()
            except:

                if 'login' in r.text.lower() or 'войти' in r.text.lower():
                    if not retry_after_refresh:
                        print(f" {Y}(login page - refreshing...){W}", end="", flush=True)
                        if self.auto_relogin():
                            return self.begin(aid, retry_after_refresh=True)
                return "SKIP"


            if data.get('status') == 'success':
                if 'data' in data:
                    self.balance = float(data['data'].get('balance', self.balance))
                return data.get('hash')


            msg = data.get('message', '').lower()


            auth_keywords = ['unauthorized', 'token', 'csrf', 'xsrf', 'войдите', 'авторизуйтесь', 'session expired']
            if any(kw in msg for kw in auth_keywords):
                if not retry_after_refresh:
                    print(f" {Y}(auth error in response - refreshing...){W}", end="", flush=True)
                    if self.auto_relogin():
                        return self.begin(aid, retry_after_refresh=True)
                return "SKIP"


            if 'произошла ошибка' in msg and not retry_after_refresh:
                if self.auto_relogin():
                    return self.begin(aid, retry_after_refresh=True)
                return "SKIP"


            if 'приостановлен' in msg or 'ошибка' in msg:
                return "SKIP"

            return "SKIP"

        except Exception as e:

            print(f" {R}(exception: {str(e)[:40]}){W}")
            return "SKIP"

    def beware(self, aid):
        try:
            r = self._request_with_fallback('POST', f"/assignments/{aid}/beware")
            if r:
                data = r.json()
                if data.get('status') == 'success':
                    return data
        except: pass
        return None

    def _beware(self, aid):
        """Get duration from beware endpoint for story tasks"""
        try:
            r = self._request_with_fallback('POST', f"/assignments/{aid}/beware")
            if r:
                data = r.json()
                if data.get('status') == 'success':
                    return data.get('data', {}).get('duration', 5)
        except: pass
        return 5

    def check(self, aid, h, cid=None, vid=None):
        """Check task completion. Network errors handled by _request_with_fallback."""
        global STOP_FLAG
        if STOP_FLAG:
            return False

        try:
            r = self._request_with_fallback('POST', f"/assignments/{aid}/check", json={"hash": h, "comment_id": cid, "vote_id": vid})


            if not r:
                self.failed_tasks += 1
                return False


            if r.status_code == 401:
                self.failed_tasks += 1
                return False

            try:
                data = r.json()
            except:
                self.failed_tasks += 1
                return False

            if data.get('status') == 'success':
                if 'data' in data:
                    self.balance = float(data['data'].get('balance', self.balance))
                self.completed_tasks += 1
                return True
            else:
                self.failed_tasks += 1
                return False
        except:
            self.failed_tasks += 1
            return False

    def get_url(self, aid):
        """Get task URL. Network errors handled by _request_with_fallback."""
        global STOP_FLAG
        if STOP_FLAG:
            return None

        try:
            r = self._request_with_fallback('GET', f"/assignments/{aid}/go", allow_redirects=False)

            if not r:
                return None

            if r.status_code in [301, 302]:
                return r.headers.get('Location')
        except:
            pass
        return None

    def do_vk(self, t, url, bw=None):
        global STOP_FLAG
        if STOP_FLAG:
            print(f"  {Y}[stopped]{W}")
            return False

        if not self.vk:
            print(f"  {R}VK API not configured!{W}")
            return False


        if hasattr(self, 'vk_flood_control_until'):
            if time.time() < self.vk_flood_control_until:
                remaining = int(self.vk_flood_control_until - time.time())
                print(f"  {Y}VK flood control active - cooldown: {remaining}s{W}")
                return "FLOOD_CONTROL"


        if self.vk_account_blocked:
            print(f"  {R}VK Account blocked - skipping task{W}")
            return "VK_ACCOUNT_BLOCKED"

        try:

            p = url.split('vk.com/')[-1].split('?')[0] if 'vk.com/' in url else url

            if t == 'friends':

                m = re.search(r'id(\d+)', p)
                if m:
                    user_id = m.group(1)
                    try:
                        result = self.vk.friends_add(user_id)
                        return True
                    except Exception as e:
                        if 'Error 15' in str(e) or 'already' in str(e).lower():

                            return True
                        raise
                else:

                    screen_name = p.strip('/')
                    try:
                        resolved = self.vk.utils_resolve_screen_name(screen_name)
                        if resolved and resolved.get('type') == 'user':
                            user_id = resolved['object_id']
                            try:
                                result = self.vk.friends_add(user_id)
                                return True
                            except Exception as e:
                                if 'Error 15' in str(e) or 'already' in str(e).lower():
                                    return True
                                raise
                        else:
                            return False
                    except Exception as e:
                        if 'Error 15' in str(e) or 'already' in str(e).lower():
                            return True
                        return False

            elif t == 'group':

                m = re.search(r'(club|public)(\d+)', p)
                if m:
                    group_id = m.group(2)
                    try:
                        result = self.vk.groups_join(group_id)
                        return True
                    except Exception as e:
                        if 'Error 15' in str(e):

                            return True
                        raise
                else:

                    screen_name = p.strip('/')
                    try:
                        resolved = self.vk.utils_resolve_screen_name(screen_name)
                        if resolved and resolved.get('type') == 'group':
                            group_id = resolved['object_id']
                            try:
                                result = self.vk.groups_join(group_id)
                                return True
                            except Exception as e:
                                if 'Error 15' in str(e):
                                    return True
                                raise
                        else:
                            return False
                    except Exception as e:
                        if 'Error 15' in str(e):
                            return True
                        return False

            elif t == 'likes':
                m = re.search(r'wall(-?\d+)_(\d+)', p)
                if m:
                    owner_id = m.group(1)
                    post_id = m.group(2)
                    try:
                        result = self.vk.likes_add(owner_id, post_id, 'post')
                        return True
                    except Exception as e:
                        if 'Error 15' in str(e) or 'already' in str(e).lower():

                            return True
                        raise

            elif t == 'repost':
                m = re.search(r'wall(-?\d+)_(\d+)', p)
                if m:
                    wall_id = f"wall{m.group(1)}_{m.group(2)}"
                    print(f"  [VK API] Reposting {wall_id}...", end=" ", flush=True)
                    try:
                        result = self.vk.wall_repost(wall_id)
                        print(f"{G}OK{W}")
                        return True
                    except Exception as repost_err:
                        error_str = str(repost_err)
                        if 'Error 15' in error_str or "can't publish" in error_str:
                            print(f"\n  {Y}[VK] Can't publish - Akun ini tidak bisa repost (permission issue){W}")
                            print(f"  {Y}[VK] Disable repost task untuk akun ini atau check VK settings{W}")
                            return "ERROR: VK Error 15 - Can't publish (no permission)"

                        raise

            elif t == 'poll' and bw:
                m = re.search(r'wall(-?\d+)_(\d+)', p)
                if m:
                    print(f"  [VK API] Getting poll data...", end=" ", flush=True)
                    post = self.vk._call_method('wall.getById', {'posts': f"{m.group(1)}_{m.group(2)}"})
                    if isinstance(post, list): post = post[0]
                    elif isinstance(post, dict): post = post.get('items', [{}])[0]
                    for a in post.get('attachments', []):
                        if a.get('type') == 'poll':
                            poll = a['poll']
                            idx = int(bw.get('vote', {}).get('index', 1)) - 1
                            ans = poll.get('answers', [])
                            if 0 <= idx < len(ans):
                                print(f"voting...", end=" ", flush=True)
                                self.vk.polls_vote(poll['id'], [ans[idx]['id']], poll['owner_id'])
                                print(f"{G}OK{W}")
                                return True

            elif t == 'video':


                print(f"  [VK] Opening video...", end=" ", flush=True)
                try:


                    response = self.session.get(url, timeout=10)
                    if response.status_code == 200:
                        print(f"{G}OK{W}")
                        return True
                    else:
                        print(f"{R}Failed (status: {response.status_code}){W}")
                        return False
                except Exception as e:
                    print(f"{R}Request failed: {str(e)[:40]}{W}")

                    return True

        except Exception as e:
            error_str = str(e)
            print(f"\n  {R}VK API Error: {error_str[:80]}{W}")


            if 'Error 5' in error_str and 'user is blocked' in error_str:
                self.vk_account_blocked = True
                print(f"  {R}⚠ VK Account is BLOCKED - skipping all VK tasks{W}")

                vk_task_types = ['friends', 'likes', 'repost', 'group', 'poll', 'video']
                for vk_task in vk_task_types:
                    self.task_type_skip.add(vk_task)
                return "VK_ACCOUNT_BLOCKED"


            if 'Error 14' in error_str or 'Captcha' in error_str:
                self.vk_captcha_required = True
                print(f"  {Y}⚠ VK Captcha required - skipping only group/channel tasks{W}")
                # Only skip group/channel tasks that trigger captcha
                self.task_type_skip.add('group')
                return "VK_CAPTCHA_REQUIRED"


            if 'Flood control' in error_str or 'Too many requests' in error_str or 'Error 6' in error_str:
                cooldown = 60
                self.vk_flood_control_until = time.time() + cooldown
                self.vk_flood_detected_this_cycle = True
                print(f"  {Y}⚠ VK Rate limit - skipping VK tasks this cycle{W}")
                vk_task_types = ['friends', 'likes', 'repost', 'group', 'poll', 'video']
                for vk_task in vk_task_types:
                    self.task_type_skip.add(vk_task)
                return "FLOOD_CONTROL"

            import traceback
            traceback.print_exc()
        return False

    def do_ig(self, t, link, bw=None):

        is_view_task = t in ['instagram_video', 'instagram_views', 'instagram_story']


        if getattr(self, '_ig_action_skip', False) and not is_view_task:
            return "IG_SKIP"


        if is_view_task:
            return True


        if not self.ig or not self.ig.ok:
            self._ig_action_skip = True
            return "IG_SKIP"


        if getattr(self.ig, 'otp_required', False):
            self._ig_action_skip = True
            return "IG_SKIP"

        try:
            if t == 'instagram_followers':
                username_match = re.search(r'instagram\.com/([A-Za-z0-9_.]+)', link)
                if username_match:
                    username = username_match.group(1).rstrip('/').split('?')[0]
                    print(f"  Following @{username}...", end=" ", flush=True)
                    result = self.ig.follow(username)


                    if isinstance(result, str) and result.startswith("ERROR:"):
                        err_lower = result.lower()
                        if any(x in err_lower for x in ['challenge', 'login_required', 'max retries',
                                'connection', 'feedback_required', 'otp', 'verification', 'checkpoint']):
                            self._ig_action_skip = True
                            return "IG_SKIP"
                        print(f"\n  {R}{result}{W}")
                        return False
                    return result
                else:
                    print(f"  {R}Invalid username format{W}")
                    return False

            elif t == 'instagram_likes':
                print(f"  Liking post...", end=" ", flush=True)
                result = self.ig.like(link)

                if isinstance(result, str) and result.startswith("ERROR:"):
                    err_lower = result.lower()
                    if any(x in err_lower for x in ['challenge', 'login_required', 'max retries',
                            'connection', 'feedback_required', 'otp', 'verification', 'checkpoint']):
                        self._ig_action_skip = True
                        return "IG_SKIP"
                    print(f"\n  {R}{result}{W}")
                    return False
                return result

            elif t == 'instagram_comments':
                txt = bw.get('comment', {}).get('text', '') if bw else ''
                if not txt:
                    emojis = ['🔥', '❤️', '👍', '😍', '💯', '✨', '👏', '💪', '🙌', '⭐']
                    motivations = ['Amazing!', 'Great!', 'Awesome!', 'Nice!', 'Beautiful!',
                                   'Love it!', 'Perfect!', 'Incredible!', 'Fantastic!', 'Wonderful!']
                    txt = random.choice(emojis) if random.random() < 0.5 else random.choice(motivations)

                print(f"  Commenting '{txt}'...", end=" ", flush=True)
                cid = self.ig.comment(link, txt)

                if isinstance(cid, str) and cid.startswith("ERROR:"):
                    err_lower = cid.lower()
                    if any(x in err_lower for x in ['challenge', 'login_required', 'max retries',
                            'connection', 'feedback_required', 'otp', 'verification', 'checkpoint']):
                        self._ig_action_skip = True
                        return "IG_SKIP"
                    print(f"\n  {R}{cid}{W}")
                    return False
                return cid if cid else False

        except Exception as e:
            error_msg = str(e).lower()


            skip_errors = ['challenge', 'checkpoint', 'login_required', 'max retries',
                          'connection', 'feedback_required', 'enter code', 'otp', 'verification',
                          'httpsconnectionpool', 'timeout', 'responseerror']
            if any(err in error_msg for err in skip_errors):
                print(f"  {Y}⚠ IG error - skipping IG action tasks{W}")
                self._ig_action_skip = True
                return "IG_SKIP"

            print(f"  {R}IG Error: {str(e)[:80]}{W}")
            return False

        return False

    def is_view_task(self, task_type):
        """Check if task is a VIEW type (requires extra delay before check)"""
        view_keywords = ['view', 'video', '_views']
        return any(kw in task_type.lower() for kw in view_keywords)

    def process(self, task):

        global STOP_FLAG
        if STOP_FLAG:
            return None

        aid, t, link = task['id'], task['type'], task.get('link')
        is_ig = t.startswith('instagram_')
        is_view = self.is_view_task(t)


        url = link if is_ig else self.get_url(aid)
        if not url:
            return None

        h = self.begin(aid)
        if h == "SKIP":
            return None
        if not h:
            print(f"  {R}Failed to begin{W}")
            return False

        bw = None
        if t in ['poll', 'instagram_comments']:
            bw = self.beware(aid)
            if bw:
                if 'comment' in bw: print(f"  Comment: {bw['comment'].get('text', '')[:30]}...")
                elif 'vote' in bw: print(f"  Vote: {bw['vote'].get('label', '')[:30]}...")

        ok = False
        action_result = None

        if is_ig:

            if self.ig and self.ig.otp_required:
                print(f" {Y}SKIP (IG verification required - check Telegram for details){W}")
                return None


            action_type = None
            if t == 'instagram_followers':
                action_type = 'follow'
            elif t == 'instagram_likes':
                action_type = 'like'
            elif t == 'instagram_comments':
                action_type = 'comment'

            if action_type and self.ig and action_type in self.ig.rate_limited_actions:
                if time.time() < self.ig.rate_limited_actions[action_type]:
                    remaining_min = int((self.ig.rate_limited_actions[action_type] - time.time()) / 60)
                    print(f"  {Y}Instagram {action_type} rate limited - cooldown: {remaining_min} minutes{W}")
                    print(f" {Y}SKIP ({action_type} blocked - tunggu {remaining_min} menit){W}")
                    return None
                else:

                    del self.ig.rate_limited_actions[action_type]

            action_result = self.do_ig(t, link, bw)
            ok = action_result is True or (isinstance(action_result, str) and not action_result.startswith("ERROR:"))
        elif t.startswith('telegram_') and self.telegram_enabled:
            try:
                if 'follower' in t:
                    action_result = self.tg_join_channel(url)
                    if action_result == "FLOOD":
                        return "TG_JOIN_FLOOD"
                    if action_result == "BLACKLISTED":
                        # Don't count as error - invalid username
                        return "BLACKLISTED"
                else:
                    action_result = self.tg_view_post(url)
                ok = action_result
            except Exception as e:
                print(f"\n  {R}Telegram error: {str(e)[:60]}{W}")
                ok = False
        elif t.startswith('tiktok_'):

            if not self.has_tiktok_account:
                print(f"  {R}TikTok account NOT connected on server{W}")
                ok = False
            else:

                print(f"  {Y}Manual task - please complete manually{W}")
                ok = True
        elif t in ['friends', 'group', 'likes', 'repost', 'poll', 'video']:
            action_result = self.do_vk(t, url, bw)
            ok = action_result
        else:

            action_result = self.do_vk(t, url, bw)
            ok = action_result


        if action_result == "FLOOD_CONTROL":
            print(f" {Y}⚠ VK Flood Control detected - stopping all VK tasks{W}")

            self.vk_flood_detected_this_cycle = True
            return "FLOOD_SKIP"
        
        # Blacklisted username - skip without counting as error
        if action_result == "BLACKLISTED":
            print(f" {Y}SKIP (invalid username - blacklisted){W}")
            return "BLACKLISTED"


        if ok:

            if t in self.task_type_errors:
                self.task_type_errors[t] = 0

                if t in self.task_type_skip:
                    self.task_type_skip.remove(t)
        else:

            if CLEAN_OUTPUT_AVAILABLE and isinstance(action_result, str) and len(action_result) > 0:
                CleanOutput.task_result(t, False, action_result[:50])


            if t not in self.task_type_errors:
                self.task_type_errors[t] = 0
            self.task_type_errors[t] += 1


            if self.task_type_errors[t] >= 3 and t not in self.task_type_skip:
                self.task_type_skip.add(t)
                print(f"  {R}⚠ Task type '{t}' has {self.task_type_errors[t]} consecutive errors{W}")
                print(f"  {Y}→ Skipping all '{t}' tasks until issue resolved{W}")


        if not ok:
            print(f" {Y}SKIP (action failed - task akan tetap dicoba oleh server){W}")
            return False





        if is_view:
            w = random.randint(20, 30)
            print(f"  Wait {w}s (view)...", end="", flush=True)
        elif t.startswith('vk_'):
            w = random.randint(4, 6)
            print(f"  Wait {w}s...", end="", flush=True)
        else:
            w = random.randint(3, 4)


        for i in range(w):
            if STOP_FLAG:
                return None
            time.sleep(1)


        if STOP_FLAG:
            return None

        cid = ok if t == 'instagram_comments' and isinstance(ok, str) else None
        vid = bw.get('vote', {}).get('id') if bw else None

        if self.check(aid, h, cid, vid):



            if is_ig:
                ig_delay = random.randint(20, 40)


                for i in range(ig_delay):
                    if STOP_FLAG:
                        print(f" {Y}[stopped]{W}")
                        return True
                    time.sleep(1)

                    if (i + 1) % 10 == 0 and (i + 1) < ig_delay:
                        print(f" {i + 1}s", end="", flush=True)

                print(f" {G}Done{W}")

            return True
        print(f" {R}✗{W}")
        return False

    def auto_process_all_tasks(self, max_tasks=None):
        global STOP_FLAG

        mapping = {
            'vk_friends': 'friends', 'vk_groups': 'group', 'vk_likes': 'likes',
            'vk_reposts': 'repost', 'vk_polls': 'poll', 'vk_videos': 'video',
            'instagram_followers': 'instagram_followers', 'instagram_likes': 'instagram_likes',
            'instagram_comments': 'instagram_comments', 'instagram_video': 'instagram_video',
            'instagram_views': 'instagram_views', 'instagram_story': 'instagram_story',
            'telegram_followers': 'telegram_followers', 'telegram_views': 'telegram_views',
            'tiktok_video': 'tiktok_video',
        }


        if self.task_type_skip:
            print(f"\n{R}⚠ Task types with consecutive errors (auto-skipped):{W}")
            for skip_type in self.task_type_skip:
                error_count = self.task_type_errors.get(skip_type, 0)
                print(f"  → {skip_type} ({error_count} consecutive errors)")
            print()


        ig_rate_limited_actions = {}
        if self.ig and self.ig.rate_limited_actions:
            for action, until_time in self.ig.rate_limited_actions.items():
                if time.time() < until_time:
                    remaining_min = int((until_time - time.time()) / 60)
                    ig_rate_limited_actions[action] = remaining_min
                    print(f"  {Y}⚠ Instagram {action.upper()} rate limited - cooldown: {remaining_min} minutes{W}")


        if self.vk_account_blocked:
            print(f"  {R}⚠ VK Account is BLOCKED - all VK tasks skipped{W}")


        vk_api_available = hasattr(self, 'vk') and self.vk is not None
        if not vk_api_available:
            print(f"  {Y}⚠ VK API not configured - VK tasks skipped{W}")

        enabled = []

        ig_view_tasks = ['instagram_video', 'instagram_story']
        for vt in ig_view_tasks:
            if vt not in [v for k, v in mapping.items() if self.config.get('task_types', {}).get(k)]:
                enabled.append(vt)

        for k, v in mapping.items():
            if self.config.get('task_types', {}).get(k):

                if v in self.task_type_skip:
                    print(f"  {Y}Skipping {v} - too many consecutive errors (will retry after success){W}")
                    continue


                vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
                if v in vk_task_types and (self.vk_account_blocked or not vk_api_available):
                    continue

                if v.startswith('instagram_'):

                    is_view_task = v in ['instagram_video', 'instagram_views', 'instagram_story']

                    if not self.instagram_enabled and not is_view_task:
                        continue


                    if self.ig and self.ig.otp_required and not is_view_task:
                        print(f"  {Y}Skipping Instagram {v} - OTP verification required (check Telegram){W}")
                        continue


                    action_type = None
                    if v == 'instagram_followers':
                        action_type = 'follow'
                    elif v == 'instagram_likes':
                        action_type = 'like'
                    elif v == 'instagram_comments':
                        action_type = 'comment'

                    if action_type and action_type in ig_rate_limited_actions:
                        print(f"  {Y}Skipping Instagram {v} - {action_type} rate limited{W}")
                        continue
                if v.startswith('telegram_') and not self.telegram_enabled:
                    print(f"  {R}[DEBUG] Skipping Telegram {v} - telegram_enabled={self.telegram_enabled}{W}")
                    tg_config = self.config.get('telegram', {})
                    print(f"  {R}[DEBUG] TG config: bound={tg_config.get('bound')}, has_session_string={bool(tg_config.get('session_string'))}{W}")
                    continue
                if v.startswith('tiktok_') and not self.has_tiktok_account:
                    print(f"  {Y}Skipping TikTok tasks - account not connected{W}")
                    continue


                vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
                if v in vk_task_types and self.vk_account_blocked:
                    print(f"  {Y}Skipping VK {v} - account blocked{W}")
                    continue

                enabled.append(v)

        all_tasks = []
        task_counts = {}
        skipped_types = []

        for t in enabled:
            if STOP_FLAG:
                break


            tasks = self.get_tasks(t)

            if tasks is None:

                skipped_types.append(t)
                continue

            task_count = len(tasks)
            task_counts[t] = task_count

            if task_count > 0:
                all_tasks.extend(tasks)


        if CLEAN_OUTPUT_AVAILABLE:
            CleanOutput.task_summary(task_counts)
        else:

            for t, count in task_counts.items():
                if count > 0:
                    print(f"  {t}: {G}{count}{W}")
                else:
                    print(f"  {t}: {Y}0 tasks{W}")
            print(f"\nTotal: {len(all_tasks)}\n")



        if len(all_tasks) == 0 and len(task_counts) > 0:

            all_zero = all(count == 0 for count in task_counts.values())

            if all_zero:
                if CLEAN_OUTPUT_AVAILABLE:
                    CleanOutput.warning("Account received ZERO tasks - possibly BANNED")
                else:
                    print(f"{R}⚠️  WARNING: Account received ZERO tasks across all types!{W}")
                    print(f"{R}   This usually indicates the account is BANNED or RESTRICTED.{W}\n")


                self.is_banned = True



        elif len(all_tasks) == 0 and len(task_counts) == 0 and len(skipped_types) > 0:

            if CLEAN_OUTPUT_AVAILABLE:
                CleanOutput.warning(f"All task types errored ({len(skipped_types)} skipped)")
            else:
                print(f"{Y}⚠ All {len(skipped_types)} task types returned errors - skipping{W}")

        done = 0
        total_tasks = len(all_tasks)



        view_task_types = ['instagram_video', 'instagram_story', 'telegram_views', 'video']
        view_tasks = [t for t in all_tasks if t.get('type') in view_task_types]
        action_tasks = [t for t in all_tasks if t.get('type') not in view_task_types]


        stats = {'view_ok': 0, 'view_fail': 0, 'action_ok': 0, 'action_fail': 0, 'action_skip': 0}


        story_tasks = [t for t in view_tasks if t.get('type') == 'instagram_story']
        regular_view_tasks = [t for t in view_tasks if t.get('type') != 'instagram_story']


        if story_tasks:
            print(f"{C}│ Processing {len(story_tasks)} story tasks...{W}")
            for i, task in enumerate(story_tasks):
                if STOP_FLAG:
                    break
                h = self.begin(task['id'])
                if h and h != "SKIP":

                    duration = self._beware(task['id'])
                    if duration:
                        wait = duration + 1
                        print(f"\r│ Story [{i+1}/{len(story_tasks)}] waiting {wait}s...", end="", flush=True)
                        time.sleep(wait)
                        result = self.check(task['id'], h)
                        if result:
                            done += 1
                            stats['view_ok'] += 1
                        else:
                            stats['view_fail'] += 1
                    else:
                        stats['view_fail'] += 1
                else:
                    stats['view_fail'] += 1
                time.sleep(random.uniform(1, 2))
            print()


        if regular_view_tasks:
            print(f"{C}│ Batch processing {len(regular_view_tasks)} view tasks...{W}")


            begun_tasks = []
            for task in regular_view_tasks:
                if STOP_FLAG:
                    break
                h = self.begin(task['id'])
                if h and h != "SKIP":
                    begun_tasks.append({'task': task, 'hash': h})
                print(f"\r│ [{len(begun_tasks)}/{len(regular_view_tasks)}] begun", end="", flush=True)
                time.sleep(random.uniform(0.3, 0.5))

            if begun_tasks:

                wait_time = random.randint(30, 32)
                print(f"\n{C}│ Waiting {wait_time}s for {len(begun_tasks)} tasks...{W}", end="", flush=True)
                for _ in range(wait_time):
                    if STOP_FLAG:
                        break
                    time.sleep(1)
                print()


                for i, bt in enumerate(begun_tasks):
                    if STOP_FLAG:
                        break
                    result = self.check(bt['task']['id'], bt['hash'])
                    if result:
                        done += 1
                        stats['view_ok'] += 1
                    else:
                        stats['view_fail'] += 1
                    print(f"\r│ [{i+1}/{len(begun_tasks)}] checked", end="", flush=True)
                print()

        if view_tasks:
            print(f"│ {G}View tasks: {stats['view_ok']} OK{W}, {R}{stats['view_fail']} failed{W}")


        for task in action_tasks:
            if STOP_FLAG:
                print(f"\n{Y}⏸ Stopping task processing...{W}")
                break


            if hasattr(self, 'vk_flood_detected_this_cycle') and self.vk_flood_detected_this_cycle:

                task_type = task.get('type', '')
                vk_task_types = ['friends', 'group', 'likes', 'repost', 'poll', 'video']
                if task_type in vk_task_types:
                    continue

            if max_tasks and done >= max_tasks:
                break


            if CLEAN_OUTPUT_AVAILABLE and total_tasks > 0:
                CleanOutput.task_progress(done, total_tasks)

            r = self.process(task)


            if r == "FLOOD_SKIP":
                if CLEAN_OUTPUT_AVAILABLE:
                    print(f"\n{Y}│ ⚠ VK Flood Control - skipping remaining VK tasks{W}")
                else:
                    print(f"{Y}  → Skipping remaining VK tasks this cycle{W}")
                continue


            if r == "TG_JOIN_FLOOD":
                print(f"\n{Y}│ ⚠ TG FloodWait - skipping join tasks{W}")
                continue


            if r == "IG_SKIP":
                print(f"\n{Y}│ ⚠ IG error - skipping action tasks (view/story still work){W}")
                continue

            if r is True:
                done += 1
                stats['action_ok'] += 1
                d = self.config.get('settings', {}).get('delay_between_tasks', 5)
                delay = random.randint(d, d + 5)

                for _ in range(delay):
                    if STOP_FLAG:
                        break
                    time.sleep(1)
            elif r is False:
                done += 1
                stats['action_fail'] += 1
            else:
                stats['action_skip'] += 1



        if action_tasks:
            print(f"│ {G}Action tasks: {stats['action_ok']} OK{W}, {R}{stats['action_fail']} fail{W}, {Y}{stats['action_skip']} skip{W}")


        if CLEAN_OUTPUT_AVAILABLE and total_tasks > 0:
            print()

    def run(self, max_tasks=None):
        """Run single cycle of tasks (no loop, no big delay)"""
        global STOP_FLAG


        print(f"{C}[CYCLE START] Refreshing XSRF token and session...{W}")
        if self.refresh_xsrf_token():
            print(f"{G}✓ Session refreshed{W}")
        else:
            print(f"{Y}⚠ Session refresh failed, using existing token{W}")


        current_ip = "Unknown"
        if hasattr(self, 'session') and self.session:
            try:

                proxy = self.session.proxies.get('http', '')
                if proxy and '@' in proxy:
                    current_ip = proxy.split('@')[1].split(':')[0]
                elif proxy:
                    current_ip = proxy.split('://')[1].split(':')[0]
                else:

                    resp = self.session.get('https://api.ipify.org', timeout=5)
                    current_ip = resp.text
            except:
                pass

        user_agent = self.config.get('user_agent', {}).get('user_agent', 'Unknown')


        if not self.get_accounts_info():
            print(f"{Y}Could not fetch account info from server{W}\n")
            return

        self.validate_accounts()


        start_balance = self.get_balance()


        if CLEAN_OUTPUT_AVAILABLE:
            CleanOutput.account_header(
                self.account_name or "Unknown",
                current_ip,
                user_agent,
                start_balance
            )
        else:

            print(f"\n{C}┌─ {self.account_name or 'Unknown'} {W}")
            print(f"{G}│ IP: {current_ip}{W}")
            print(f"{G}│ UA: {user_agent.split('(')[1].split(')')[0] if '(' in user_agent else 'Unknown'}{W}")
            print(f"{G}│ Balance: {start_balance:.2f}₽{W}")

        if STOP_FLAG:
            print(f"\n{Y}⏸ Stop requested{W}")
            return

        start = self.balance
        self.auto_process_all_tasks(max_tasks)


        self._disconnect_tg_client()


        self.earned = self.balance - start


        if CLEAN_OUTPUT_AVAILABLE:
            CleanOutput.account_footer(self.earned, self.balance)
        else:

            print(f"\n{G}│ Earned: +{self.earned:.2f}₽{W}")
            print(f"{G}└─ Final: {self.balance:.2f}₽{W}")


VKFullAutomation = VKSerfingBot
