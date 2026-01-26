#!/usr/bin/env python3
"""
Check all proxies, find duplicates and dead ones, replace with new proxies from Webshare
"""

import json
import os
import requests
import concurrent.futures
from collections import defaultdict

ACCOUNTS_DIR = 'accounts'
CONFIG_FILE = 'config/api_keys.json'
TIMEOUT = 10
MAX_WORKERS = 20

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def load_api_keys():
    """Load Webshare API keys"""
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    return config['webshare']['api_keys']

def test_proxy(proxy_str):
    """Test if proxy is alive"""
    if not proxy_str:
        return False
    
    proxies = {'http': proxy_str, 'https': proxy_str}
    try:
        r = requests.get('https://api.ipify.org?format=json', 
                        proxies=proxies, timeout=TIMEOUT)
        return r.status_code == 200
    except:
        return False

def get_proxy_ip(proxy_str):
    """Extract IP from proxy string"""
    if not proxy_str:
        return None
    if '@' in proxy_str:
        return proxy_str.split('@')[1].split(':')[0]
    return proxy_str.split(':')[0].replace('http://', '').replace('https://', '')

def fetch_webshare_proxies(api_key):
    """Fetch available proxies from Webshare API"""
    url = f"https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"
    headers = {'Authorization': f'Token {api_key}'}
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            proxies = []
            for p in data.get('results', []):
                proxy_str = f"http://{p['username']}:{p['password']}@{p['proxy_address']}:{p['port']}"
                proxies.append({
                    'proxy_string': proxy_str,
                    'ip': p['proxy_address'],
                    'port': str(p['port']),
                    'username': p['username'],
                    'password': p['password']
                })
            return proxies
        return []
    except Exception as e:
        print(f"{R}Error fetching from Webshare: {e}{W}")
        return []

def scan_all_proxies():
    """Scan all account proxies and find issues"""
    folders = sorted([f for f in os.listdir(ACCOUNTS_DIR) 
                     if os.path.isdir(os.path.join(ACCOUNTS_DIR, f)) and f.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    print(f"{C}Scanning {len(folders)} accounts...{W}\n")
    
    ip_to_accounts = defaultdict(list)
    account_proxies = {}
    
    # Collect all proxies
    for acc in folders:
        config_path = os.path.join(ACCOUNTS_DIR, acc, 'config.json')
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            proxy_str = config.get('proxy', {}).get('proxy_string', '')
            if proxy_str:
                ip = get_proxy_ip(proxy_str)
                if ip:
                    ip_to_accounts[ip].append(acc)
                    account_proxies[acc] = {
                        'proxy_string': proxy_str,
                        'ip': ip,
                        'config_path': config_path
                    }
        except:
            pass
    
    # Find duplicates
    duplicates = {ip: accs for ip, accs in ip_to_accounts.items() if len(accs) > 1}
    
    print(f"{Y}Found {len(duplicates)} duplicate IPs:{W}")
    for ip, accs in duplicates.items():
        print(f"  {ip}: {', '.join(accs)}")
    
    # Test all proxies
    print(f"\n{C}Testing {len(account_proxies)} proxies...{W}")
    dead_accounts = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_acc = {executor.submit(test_proxy, info['proxy_string']): acc 
                        for acc, info in account_proxies.items()}
        
        for future in concurrent.futures.as_completed(future_to_acc):
            acc = future_to_acc[future]
            is_alive = future.result()
            ip = account_proxies[acc]['ip']
            
            if is_alive:
                print(f"{G}✓{W} {acc:<15} {ip:<15} - OK")
            else:
                print(f"{R}✗{W} {acc:<15} {ip:<15} - DEAD")
                dead_accounts.append(acc)
    
    return duplicates, dead_accounts, account_proxies

def replace_proxies(accounts_to_replace, account_proxies, api_keys):
    """Replace proxies for specified accounts"""
    print(f"\n{C}Fetching new proxies from Webshare...{W}")
    
    # Fetch available proxies from all API keys
    all_available = []
    for api_key in api_keys:
        proxies = fetch_webshare_proxies(api_key)
        print(f"  Fetched {len(proxies)} proxies from API key {api_key[:10]}...")
        all_available.extend(proxies)
    
    if not all_available:
        print(f"{R}No proxies available from Webshare!{W}")
        return
    
    # Get currently used IPs
    used_ips = set(info['ip'] for info in account_proxies.values())
    
    # Filter available proxies (exclude already used)
    available = [p for p in all_available if p['ip'] not in used_ips]
    
    print(f"\n{C}Available new proxies: {len(available)}{W}")
    print(f"{Y}Accounts to replace: {len(accounts_to_replace)}{W}\n")
    
    if len(available) < len(accounts_to_replace):
        print(f"{R}Warning: Not enough proxies! Need {len(accounts_to_replace)}, have {len(available)}{W}")
    
    # Replace proxies
    replaced = 0
    for i, acc in enumerate(accounts_to_replace):
        if i >= len(available):
            print(f"{R}✗{W} {acc:<15} - No more proxies available")
            break
        
        new_proxy = available[i]
        config_path = account_proxies[acc]['config_path']
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            old_ip = account_proxies[acc]['ip']
            config['proxy'] = new_proxy
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"{G}✓{W} {acc:<15} {old_ip:<15} → {new_proxy['ip']}")
            replaced += 1
            used_ips.add(new_proxy['ip'])
            
        except Exception as e:
            print(f"{R}✗{W} {acc:<15} - Error: {e}")
    
    return replaced

def main():
    print("=" * 70)
    print("PROXY CHECKER & REPLACER")
    print("=" * 70)
    
    # Load API keys
    api_keys = load_api_keys()
    print(f"\n{C}Loaded {len(api_keys)} Webshare API keys{W}")
    
    # Scan all proxies
    duplicates, dead_accounts, account_proxies = scan_all_proxies()
    
    # Collect accounts that need replacement
    accounts_to_replace = set()
    
    # Add duplicate IPs (keep first, replace others)
    for ip, accs in duplicates.items():
        accounts_to_replace.update(accs[1:])  # Skip first account
    
    # Add dead proxies
    accounts_to_replace.update(dead_accounts)
    
    accounts_to_replace = sorted(list(accounts_to_replace), 
                                 key=lambda x: int(x.split('_')[1]) if '_' in x else 0)
    
    print(f"\n{Y}{'='*70}{W}")
    print(f"{Y}Summary:{W}")
    print(f"  Duplicate IPs: {len(duplicates)} (affecting {sum(len(accs)-1 for accs in duplicates.values())} accounts)")
    print(f"  Dead proxies: {len(dead_accounts)}")
    print(f"  Total to replace: {len(accounts_to_replace)}")
    print(f"{Y}{'='*70}{W}")
    
    if not accounts_to_replace:
        print(f"\n{G}✓ All proxies are OK!{W}")
        return
    
    print(f"\n{Y}Accounts to replace:{W}")
    for acc in accounts_to_replace:
        reason = []
        if acc in dead_accounts:
            reason.append("DEAD")
        for ip, accs in duplicates.items():
            if acc in accs[1:]:
                reason.append(f"DUP:{ip}")
        print(f"  {acc:<15} - {', '.join(reason)}")
    
    confirm = input(f"\n{C}Replace these proxies? (y/n): {W}").strip().lower()
    if confirm != 'y':
        print(f"{Y}Cancelled{W}")
        return
    
    # Replace proxies
    replaced = replace_proxies(accounts_to_replace, account_proxies, api_keys)
    
    print(f"\n{G}{'='*70}{W}")
    print(f"{G}Done! Replaced {replaced}/{len(accounts_to_replace)} proxies{W}")
    print(f"{G}{'='*70}{W}")

if __name__ == '__main__':
    main()
