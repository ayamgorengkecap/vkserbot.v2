#!/usr/bin/env python3
"""
Generate audit report only - no deletion/modification
"""

import json
import os
import sys

# Import from audit_cleanup
sys.path.insert(0, '/root/vkserbot.v2')
from audit_cleanup import (
    load_all_accounts, find_duplicates, resolve_duplicates,
    audit_proxies, load_webshare_keys, fetch_webshare_proxies
)

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def main():
    print("=" * 70)
    print("AUDIT REPORT - READ ONLY")
    print("=" * 70)
    
    # Load accounts
    accounts = load_all_accounts()
    print(f"\n{C}Total accounts: {len(accounts)}{W}")
    
    # Find duplicates
    duplicates, account_data = find_duplicates(accounts)
    to_delete, to_keep = resolve_duplicates(duplicates, account_data)
    
    print(f"\n{Y}DUPLICATE ANALYSIS:{W}")
    print(f"  Duplicate groups found: {len(duplicates)}")
    print(f"  Accounts to delete: {len(to_delete)}")
    print(f"  Accounts to keep: {len(accounts) - len(to_delete)}")
    
    # Audit proxies
    proxy_status, duplicate_ips, dead_ips = audit_proxies(accounts)
    
    accounts_need_proxy_fix = set()
    for ip, accs in duplicate_ips.items():
        accounts_need_proxy_fix.update(accs[1:])
    for ip, info in dead_ips.items():
        accounts_need_proxy_fix.update(info['accounts'])
    accounts_need_proxy_fix -= to_delete
    
    print(f"\n{Y}PROXY ANALYSIS:{W}")
    print(f"  Total unique IPs: {len(proxy_status)}")
    print(f"  Duplicate IPs: {len(duplicate_ips)}")
    print(f"  Dead IPs: {len(dead_ips)}")
    print(f"  Accounts need proxy fix: {len(accounts_need_proxy_fix)}")
    
    # Check Webshare availability
    api_keys = load_webshare_keys()
    available_proxies = fetch_webshare_proxies(api_keys)
    
    print(f"\n{Y}WEBSHARE API:{W}")
    print(f"  API keys: {len(api_keys)}")
    print(f"  Available proxies: {len(available_proxies)}")
    print(f"  Sufficient for replacement: {G if len(available_proxies) >= len(accounts_need_proxy_fix) else R}{'YES' if len(available_proxies) >= len(accounts_need_proxy_fix) else 'NO'}{W}")
    
    # Final summary
    print(f"\n{C}{'='*70}{W}")
    print(f"{C}FINAL SUMMARY:{W}")
    print(f"{C}{'='*70}{W}")
    print(f"Current accounts: {len(accounts)}")
    print(f"After cleanup: {len(accounts) - len(to_delete)}")
    print(f"Accounts to delete: {len(to_delete)}")
    print(f"Proxies to replace: {len(accounts_need_proxy_fix)}")
    print(f"{C}{'='*70}{W}")
    
    print(f"\n{Y}To execute cleanup, run:{W}")
    print(f"  python3 audit_cleanup.py")

if __name__ == '__main__':
    main()
