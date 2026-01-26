#!/usr/bin/env python3
"""
PRODUCTION DATA AUDIT & CLEANUP
- Scan all accounts
- Find duplicates based on VK/IG/TG identifiers
- Keep most complete account
- Replace duplicate/dead proxies with Webshare API
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

# ============================================================
# 1. ACCOUNT DISCOVERY & CONFIG VALIDATION
# ============================================================

def load_all_accounts():
    """Load all account configs"""
    folders = sorted([f for f in os.listdir(ACCOUNTS_DIR) 
                     if os.path.isdir(os.path.join(ACCOUNTS_DIR, f)) and f.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    accounts = {}
    for folder in folders:
        config_path = os.path.join(ACCOUNTS_DIR, folder, 'config.json')
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            accounts[folder] = config
        except Exception as e:
            print(f"{R}✗ {folder}: Failed to load config - {e}{W}")
    
    return accounts

def extract_identifiers(account_name, config):
    """Extract unique identifiers from config"""
    identifiers = {
        'account_name': account_name,
        'vk_user_id': None,
        'ig_username': None,
        'ig_user_id': None,
        'tg_user_id': None,
        'tg_username': None,
        'proxy_ip': None,
        'has_ig_session': False,
        'has_tg_session': False,
        'completeness_score': 0
    }
    
    # VK
    vk = config.get('vk_api', {})
    if vk.get('enabled') and vk.get('user_id'):
        identifiers['vk_user_id'] = str(vk['user_id'])
    
    # Instagram
    ig = config.get('instagram', {})
    if ig.get('enabled'):
        identifiers['ig_username'] = ig.get('username')
        identifiers['ig_user_id'] = ig.get('ds_user_id')
        # Check if session file exists
        session_file = ig.get('session_file')
        if session_file:
            session_path = os.path.join(ACCOUNTS_DIR, account_name, session_file)
            identifiers['has_ig_session'] = os.path.exists(session_path)
    
    # Telegram
    tg = config.get('telegram', {})
    if tg.get('session_string'):
        identifiers['tg_user_id'] = tg.get('user_id')
        identifiers['tg_username'] = tg.get('username')
        identifiers['has_tg_session'] = True
    
    # Proxy
    proxy = config.get('proxy', {})
    identifiers['proxy_ip'] = proxy.get('ip')
    
    # Completeness score
    score = 0
    if identifiers['vk_user_id']: score += 1
    if identifiers['ig_username']: score += 1
    if identifiers['has_ig_session']: score += 2  # Session lebih penting
    if identifiers['tg_user_id']: score += 1
    if identifiers['has_tg_session']: score += 2
    identifiers['completeness_score'] = score
    
    return identifiers

# ============================================================
# 2. DUPLICATE ACCOUNT ANALYSIS
# ============================================================

def find_duplicates(accounts):
    """Find duplicate accounts based on identifiers"""
    
    # Group by VK user_id
    vk_groups = defaultdict(list)
    # Group by IG username
    ig_groups = defaultdict(list)
    # Group by TG user_id
    tg_groups = defaultdict(list)
    
    account_data = {}
    
    for acc_name, config in accounts.items():
        identifiers = extract_identifiers(acc_name, config)
        account_data[acc_name] = identifiers
        
        if identifiers['vk_user_id']:
            vk_groups[identifiers['vk_user_id']].append(acc_name)
        if identifiers['ig_username']:
            ig_groups[identifiers['ig_username']].append(acc_name)
        if identifiers['tg_user_id']:
            tg_groups[identifiers['tg_user_id']].append(acc_name)
    
    # Find duplicates
    duplicates = []
    
    # VK duplicates
    for vk_id, accs in vk_groups.items():
        if len(accs) > 1:
            duplicates.append({
                'type': 'VK',
                'identifier': vk_id,
                'accounts': accs
            })
    
    # IG duplicates
    for ig_user, accs in ig_groups.items():
        if len(accs) > 1:
            duplicates.append({
                'type': 'IG',
                'identifier': ig_user,
                'accounts': accs
            })
    
    # TG duplicates
    for tg_id, accs in tg_groups.items():
        if len(accs) > 1:
            duplicates.append({
                'type': 'TG',
                'identifier': tg_id,
                'accounts': accs
            })
    
    return duplicates, account_data

# ============================================================
# 3. DUPLICATE RESOLUTION
# ============================================================

def resolve_duplicates(duplicates, account_data):
    """Resolve duplicates - keep most complete account"""
    
    to_delete = set()
    to_keep = {}
    
    for dup in duplicates:
        accs = dup['accounts']
        
        # Sort by completeness score (highest first)
        sorted_accs = sorted(accs, key=lambda x: account_data[x]['completeness_score'], reverse=True)
        
        keep = sorted_accs[0]
        delete = sorted_accs[1:]
        
        dup_key = f"{dup['type']}_{str(dup['identifier'])}"
        to_keep[dup_key] = {
            'keep': keep,
            'delete': delete,
            'reason': f"Completeness: {account_data[keep]['completeness_score']} vs {[account_data[d]['completeness_score'] for d in delete]}"
        }
        
        to_delete.update(delete)
    
    return to_delete, to_keep

# ============================================================
# 4. PROXY VALIDATION
# ============================================================

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

def audit_proxies(accounts):
    """Audit all proxies"""
    
    ip_to_accounts = defaultdict(list)
    proxy_status = {}
    
    # Collect all proxies
    for acc_name, config in accounts.items():
        proxy = config.get('proxy', {})
        ip = proxy.get('ip')
        proxy_str = proxy.get('proxy_string')
        
        if ip:
            ip_to_accounts[ip].append(acc_name)
            if ip not in proxy_status:
                proxy_status[ip] = {
                    'proxy_string': proxy_str,
                    'accounts': [],
                    'alive': None
                }
            proxy_status[ip]['accounts'].append(acc_name)
    
    # Test proxies in parallel
    print(f"\n{C}Testing {len(proxy_status)} unique proxies...{W}")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_ip = {executor.submit(test_proxy, info['proxy_string']): ip 
                       for ip, info in proxy_status.items()}
        
        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            is_alive = future.result()
            proxy_status[ip]['alive'] = is_alive
    
    # Find issues
    duplicate_ips = {ip: accs for ip, accs in ip_to_accounts.items() if len(accs) > 1}
    dead_ips = {ip: info for ip, info in proxy_status.items() if not info['alive']}
    
    return proxy_status, duplicate_ips, dead_ips

# ============================================================
# 5. PROXY ROTATION (WEBSHARE API)
# ============================================================

def load_webshare_keys():
    """Load Webshare API keys"""
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    return config['webshare']['api_keys']

def fetch_webshare_proxies(api_keys):
    """Fetch proxies from Webshare API"""
    all_proxies = []
    
    for api_key in api_keys:
        url = "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=100"
        headers = {'Authorization': f'Token {api_key}'}
        
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                for p in data.get('results', []):
                    proxy_str = f"http://{p['username']}:{p['password']}@{p['proxy_address']}:{p['port']}"
                    all_proxies.append({
                        'proxy_string': proxy_str,
                        'ip': p['proxy_address'],
                        'port': str(p['port']),
                        'username': p['username'],
                        'password': p['password']
                    })
                print(f"{G}✓ Fetched {len(data.get('results', []))} proxies from API key {api_key[:10]}...{W}")
        except Exception as e:
            print(f"{R}✗ Failed to fetch from {api_key[:10]}...: {e}{W}")
    
    return all_proxies

def replace_proxies(accounts_to_fix, accounts, api_keys):
    """Replace proxies for accounts with duplicate/dead IPs"""
    
    print(f"\n{C}Fetching new proxies from Webshare...{W}")
    available_proxies = fetch_webshare_proxies(api_keys)
    
    if not available_proxies:
        print(f"{R}No proxies available from Webshare!{W}")
        return {}
    
    # Get currently used IPs
    used_ips = set()
    for config in accounts.values():
        ip = config.get('proxy', {}).get('ip')
        if ip:
            used_ips.add(ip)
    
    # Filter available proxies (exclude already used)
    new_proxies = [p for p in available_proxies if p['ip'] not in used_ips]
    
    print(f"{C}Available new proxies: {len(new_proxies)}{W}")
    print(f"{Y}Accounts to fix: {len(accounts_to_fix)}{W}\n")
    
    if len(new_proxies) < len(accounts_to_fix):
        print(f"{R}Warning: Not enough proxies! Need {len(accounts_to_fix)}, have {len(new_proxies)}{W}")
    
    # Replace proxies
    replacements = {}
    for i, acc_name in enumerate(sorted(accounts_to_fix)):
        if i >= len(new_proxies):
            print(f"{R}✗ {acc_name}: No more proxies available{W}")
            break
        
        new_proxy = new_proxies[i]
        config_path = os.path.join(ACCOUNTS_DIR, acc_name, 'config.json')
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            old_ip = config.get('proxy', {}).get('ip', 'N/A')
            config['proxy'] = new_proxy
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            replacements[acc_name] = {
                'old_ip': old_ip,
                'new_ip': new_proxy['ip']
            }
            
            print(f"{G}✓ {acc_name}: {old_ip} → {new_proxy['ip']}{W}")
            used_ips.add(new_proxy['ip'])
            
        except Exception as e:
            print(f"{R}✗ {acc_name}: Error - {e}{W}")
    
    return replacements

# ============================================================
# 6. DELETE DUPLICATE ACCOUNTS
# ============================================================

def delete_accounts(to_delete):
    """Delete duplicate accounts"""
    import shutil
    
    deleted = []
    failed = []
    
    for acc_name in sorted(to_delete):
        acc_path = os.path.join(ACCOUNTS_DIR, acc_name)
        try:
            shutil.rmtree(acc_path)
            deleted.append(acc_name)
            print(f"{G}✓ Deleted: {acc_name}{W}")
        except Exception as e:
            failed.append((acc_name, str(e)))
            print(f"{R}✗ Failed to delete {acc_name}: {e}{W}")
    
    return deleted, failed

# ============================================================
# 7. MAIN AUDIT PROCESS
# ============================================================

def main():
    print("=" * 70)
    print("PRODUCTION DATA AUDIT & CLEANUP")
    print("=" * 70)
    
    # Step 1: Load all accounts
    print(f"\n{C}[STEP 1] Loading all accounts...{W}")
    accounts = load_all_accounts()
    print(f"{G}✓ Loaded {len(accounts)} accounts{W}")
    
    # Step 2: Find duplicates
    print(f"\n{C}[STEP 2] Analyzing duplicates...{W}")
    duplicates, account_data = find_duplicates(accounts)
    print(f"{Y}Found {len(duplicates)} duplicate groups{W}")
    
    if duplicates:
        for dup in duplicates:
            print(f"\n  {dup['type']} duplicate: {dup['identifier']}")
            for acc in dup['accounts']:
                score = account_data[acc]['completeness_score']
                has_ig = "✓ IG" if account_data[acc]['has_ig_session'] else "✗ IG"
                has_tg = "✓ TG" if account_data[acc]['has_tg_session'] else "✗ TG"
                print(f"    - {acc} (score: {score}, {has_ig}, {has_tg})")
    
    # Step 3: Resolve duplicates
    print(f"\n{C}[STEP 3] Resolving duplicates...{W}")
    to_delete, to_keep = resolve_duplicates(duplicates, account_data)
    print(f"{R}To delete: {len(to_delete)} accounts{W}")
    print(f"{G}To keep: {len(to_keep)} groups{W}")
    
    # Step 4: Audit proxies
    print(f"\n{C}[STEP 4] Auditing proxies...{W}")
    proxy_status, duplicate_ips, dead_ips = audit_proxies(accounts)
    print(f"{Y}Duplicate IPs: {len(duplicate_ips)}{W}")
    print(f"{R}Dead IPs: {len(dead_ips)}{W}")
    
    # Collect accounts that need proxy replacement
    accounts_need_proxy_fix = set()
    
    # Add accounts with duplicate IPs (keep first, fix others)
    for ip, accs in duplicate_ips.items():
        accounts_need_proxy_fix.update(accs[1:])  # Skip first account
    
    # Add accounts with dead IPs
    for ip, info in dead_ips.items():
        accounts_need_proxy_fix.update(info['accounts'])
    
    # Remove accounts that will be deleted
    accounts_need_proxy_fix -= to_delete
    
    print(f"{Y}Accounts need proxy fix: {len(accounts_need_proxy_fix)}{W}")
    
    # Step 5: Confirm actions
    print(f"\n{Y}{'='*70}{W}")
    print(f"{Y}SUMMARY:{W}")
    print(f"  Accounts to delete: {len(to_delete)}")
    print(f"  Accounts to fix proxy: {len(accounts_need_proxy_fix)}")
    print(f"{Y}{'='*70}{W}")
    
    confirm = input(f"\n{C}Proceed with cleanup? (yes/no): {W}").strip().lower()
    if confirm != 'yes':
        print(f"{Y}Cancelled{W}")
        return
    
    # Step 6: Delete duplicates
    if to_delete:
        print(f"\n{C}[STEP 5] Deleting duplicate accounts...{W}")
        deleted, failed = delete_accounts(to_delete)
        print(f"{G}✓ Deleted: {len(deleted)}{W}")
        if failed:
            print(f"{R}✗ Failed: {len(failed)}{W}")
    
    # Step 7: Replace proxies
    if accounts_need_proxy_fix:
        print(f"\n{C}[STEP 6] Replacing proxies...{W}")
        api_keys = load_webshare_keys()
        # Reload accounts after deletion
        accounts = load_all_accounts()
        replacements = replace_proxies(accounts_need_proxy_fix, accounts, api_keys)
        print(f"{G}✓ Replaced: {len(replacements)} proxies{W}")
    
    # Final report
    print(f"\n{G}{'='*70}{W}")
    print(f"{G}AUDIT COMPLETE{W}")
    print(f"{G}{'='*70}{W}")
    print(f"Accounts deleted: {len(deleted) if to_delete else 0}")
    print(f"Proxies replaced: {len(replacements) if accounts_need_proxy_fix else 0}")
    print(f"Remaining accounts: {len(accounts) - len(deleted) if to_delete else len(accounts)}")
    print(f"{G}{'='*70}{W}")

if __name__ == '__main__':
    main()
