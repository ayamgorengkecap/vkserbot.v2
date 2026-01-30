#!/usr/bin/env python3
"""
Bind Instagram session ke config.json
Auto-detect akun yang sudah connect Instagram di web tapi belum ada session
"""

import json
import os
import sys
import re
import html
import requests
import concurrent.futures

ACCOUNTS_DIR = 'accounts'
TIMEOUT = 10
MAX_WORKERS = 10

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def parse_proxy_string(proxy_str):
    """Parse proxy string to http://user:pass@ip:port format"""
    if not proxy_str:
        return None
    if proxy_str.startswith('http'):
        return proxy_str
    if proxy_str.count(':') == 3:
        parts = proxy_str.split(':')
        return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
    if proxy_str.count(':') == 1:
        return f"http://{proxy_str}"
    return proxy_str

def parse_settings_html(html_content):
    """Parse email, Instagram, and Telegram from /settings HTML"""
    email, ig_username, tg_username = None, None, None
    
    # Parse email
    init_match = re.search(r':init-data="([^"]+)"', html_content)
    if init_match:
        try:
            init_str = html.unescape(init_match.group(1))
            init_data = json.loads(init_str)
            email = init_data.get('email')
        except:
            pass
    
    # Parse Instagram
    ig_opts = re.findall(r'<option[^>]*data-(?:platform|icon)="instagram"[^>]*>', html_content)
    if ig_opts:
        alias = re.search(r'data-alias="@?([^"]+)"', ig_opts[0])
        if alias:
            ig_username = alias.group(1)
    
    # Parse Telegram
    tg_patterns = [
        r'data-platform="telegram"[^>]*data-alias="@?([^"]+)"',
        r'data-icon="telegram[^"]*"[^>]*data-alias="@?([^"]+)"',
    ]
    for pattern in tg_patterns:
        tg_match = re.search(pattern, html_content)
        if tg_match:
            tg_username = tg_match.group(1)
            break
    
    return email, ig_username, tg_username

def fetch_account_info(acc_name):
    """Fetch full account info from web (email, IG, Telegram)"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_name)
    config_file = os.path.join(acc_dir, "config.json")

    if not os.path.isfile(config_file):
        return {'account': acc_name, 'error': 'No config.json'}

    try:
        with open(config_file) as f:
            config = json.load(f)
    except:
        return {'account': acc_name, 'error': 'Invalid config.json'}

    creds = config.get('credentials', {})
    cookies = creds.get('cookies', {})
    xsrf = creds.get('xsrf_token', '')
    proxy_str = config.get('proxy', {}).get('proxy_string', '')
    proxy = parse_proxy_string(proxy_str)

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36',
        'X-XSRF-Token': xsrf,
        'X-Requested-With': 'XMLHttpRequest',
        'X-Ajax-Html': '1',
    }
    proxies = {'http': proxy, 'https': proxy} if proxy else None

    email = None
    ig_username = None
    tg_username = None

    for domain in ['https://vkserfing.com', 'https://vkserfing.ru']:
        try:
            resp = requests.get(f'{domain}/settings', 
                               cookies=cookies, headers=headers, 
                               proxies=proxies, timeout=TIMEOUT)
            if resp.status_code == 200:
                try:
                    html_content = resp.json().get('html', '')
                    email, ig_username, tg_username = parse_settings_html(html_content)
                except:
                    pass
            break
        except:
            continue

    # Fallback IG from config/session file
    if not ig_username:
        ig_username = config.get('instagram', {}).get('username')
        if not ig_username:
            try:
                for f in os.listdir(acc_dir):
                    if f.startswith('ig_session_') and f.endswith('.json'):
                        ig_username = f.replace('ig_session_', '').replace('.json', '')
                        break
            except:
                pass

    return {
        'account': acc_name,
        'email': email or '-',
        'ig_username': ig_username or '-',
        'tg_username': tg_username or '-',
    }

def has_instagram_session(acc_name):
    """Check if account already has instagram session file"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_name)
    try:
        for f in os.listdir(acc_dir):
            if f.startswith('ig_session_') and f.endswith('.json'):
                return True
    except:
        pass
    return False

def scan_accounts():
    """Scan all accounts and show full details"""
    folders = sorted([f for f in os.listdir(ACCOUNTS_DIR) 
                     if os.path.isdir(os.path.join(ACCOUNTS_DIR, f)) and f.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    print(f"{C}Scanning {len(folders)} accounts...{W}\n")
    print(f"{'Account':<15} | {'Email':<30} | {'IG':<20} | {'TG':<20} | {'Session'}")
    print("-" * 110)
    
    results = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_acc = {executor.submit(fetch_account_info, acc): acc for acc in folders}
        
        for future in concurrent.futures.as_completed(future_to_acc):
            try:
                info = future.result()
                
                if 'error' in info:
                    print(f"{R}{info['account']:<15}{W} | Error: {info['error']}")
                    continue
                
                acc = info['account']
                email = info['email']
                ig = info['ig_username']
                tg = info['tg_username']
                has_session = has_instagram_session(acc)
                
                # Determine status
                if ig != '-':
                    if has_session:
                        status = f"{G}✓ Has session{W}"
                    else:
                        status = f"{Y}⚠ NO SESSION{W}"
                        results.append(info)
                else:
                    status = f"{R}✗ No IG{W}"
                
                print(f"{acc:<15} | {email:<30} | {ig:<20} | {tg:<20} | {status}")
                    
            except Exception as e:
                print(f"{R}Error{W}: {e}")
    
    return results

def create_instagram_session(account_folder, ig_username, ig_password):
    """Create Instagram session using instagrapi"""
    
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    
    try:
        with open(config_path) as f:
            config = json.load(f)
    except:
        print(f"{R}Failed to load config{W}")
        return False
    
    # Import Instagram dependencies
    sys.path.insert(0, 'lib')
    from automation_core import InstagramBot, DeviceFingerprintGenerator
    
    print(f"\n{C}Creating Instagram session for {account_folder}...{W}")
    print(f"  Username: {ig_username}")
    
    # Initialize Instagram bot
    ig_bot = InstagramBot(config)
    
    if not ig_bot.client:
        print(f"{R}Failed to initialize Instagram client{W}")
        return False
    
    # Attempt login
    session_file = os.path.join(ACCOUNTS_DIR, account_folder, f'ig_session_{ig_username}.json')
    
    try:
        print(f"{C}Logging in...{W}")
        
        # Try initial login
        try:
            ig_bot.client.login(ig_username, ig_password)
            print(f"{G}✓ Login successful!{W}")
            
            # Save session
            ig_bot.client.dump_settings(session_file)
            
            # Update config
            if 'instagram' not in config:
                config['instagram'] = {}
            
            config['instagram']['enabled'] = True
            config['instagram']['username'] = ig_username
            config['instagram']['password'] = ig_password
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            print(f"{G}✓ Config updated{W}")
            print(f"{G}✓ Session saved: {session_file}{W}")
            return True
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # Check if it's a challenge that can be resolved
            if 'challenge' in error_msg or 'checkpoint' in error_msg or 'email' in error_msg or 'code' in error_msg:
                print(f"{Y}⚠ Challenge/Verification detected{W}")
                print(f"{C}Attempting to resolve challenge...{W}")
                
                # Try to get challenge
                try:
                    # Send challenge code
                    if hasattr(ig_bot.client, 'challenge_code_handler'):
                        code = input(f"\n{C}Enter verification code from email/SMS:{W} ").strip()
                        if code:
                            ig_bot.client.challenge_code_handler(ig_username, code)
                            print(f"{G}✓ Challenge resolved!{W}")
                            
                            # Save session
                            ig_bot.client.dump_settings(session_file)
                            
                            # Update config
                            if 'instagram' not in config:
                                config['instagram'] = {}
                            
                            config['instagram']['enabled'] = True
                            config['instagram']['username'] = ig_username
                            config['instagram']['password'] = ig_password
                            
                            with open(config_path, 'w') as f:
                                json.dump(config, f, indent=2)
                            
                            print(f"{G}✓ Config updated{W}")
                            print(f"{G}✓ Session saved: {session_file}{W}")
                            return True
                    
                    # Alternative: manual challenge resolution
                    print(f"\n{Y}Challenge resolution options:{W}")
                    print(f"  1. Enter verification code (if you received one)")
                    print(f"  2. Request email verification")
                    print(f"  3. Skip (manual login required)")
                    
                    choice = input(f"\n{C}Choice:{W} ").strip()
                    
                    if choice == '1':
                        code = input(f"{C}Enter code:{W} ").strip()
                        if code:
                            try:
                                # Try different challenge methods
                                if hasattr(ig_bot.client, 'challenge_resolve'):
                                    ig_bot.client.challenge_resolve(code)
                                elif hasattr(ig_bot.client, 'challenge_code_handler'):
                                    ig_bot.client.challenge_code_handler(ig_username, code)
                                
                                # Verify login
                                ig_bot.client.get_timeline_feed()
                                print(f"{G}✓ Challenge resolved!{W}")
                                
                                # Save session
                                ig_bot.client.dump_settings(session_file)
                                
                                # Update config
                                if 'instagram' not in config:
                                    config['instagram'] = {}
                                
                                config['instagram']['enabled'] = True
                                config['instagram']['username'] = ig_username
                                config['instagram']['password'] = ig_password
                                
                                with open(config_path, 'w') as f:
                                    json.dump(config, f, indent=2)
                                
                                print(f"{G}✓ Config updated{W}")
                                print(f"{G}✓ Session saved: {session_file}{W}")
                                return True
                            except Exception as resolve_err:
                                print(f"{R}✗ Failed to resolve: {resolve_err}{W}")
                    
                    elif choice == '2':
                        print(f"{Y}Please check your email and enter the code when received{W}")
                        code = input(f"{C}Enter code:{W} ").strip()
                        if code:
                            try:
                                if hasattr(ig_bot.client, 'challenge_resolve'):
                                    ig_bot.client.challenge_resolve(code)
                                
                                ig_bot.client.get_timeline_feed()
                                print(f"{G}✓ Challenge resolved!{W}")
                                
                                ig_bot.client.dump_settings(session_file)
                                
                                if 'instagram' not in config:
                                    config['instagram'] = {}
                                
                                config['instagram']['enabled'] = True
                                config['instagram']['username'] = ig_username
                                config['instagram']['password'] = ig_password
                                
                                with open(config_path, 'w') as f:
                                    json.dump(config, f, indent=2)
                                
                                print(f"{G}✓ Session saved{W}")
                                return True
                            except Exception as resolve_err:
                                print(f"{R}✗ Failed: {resolve_err}{W}")
                
                except Exception as challenge_err:
                    print(f"{R}✗ Challenge handling failed: {challenge_err}{W}")
                
                print(f"\n{Y}Manual action required:{W}")
                print(f"  1. Login via Instagram app/browser")
                print(f"  2. Complete verification")
                print(f"  3. Re-run this script")
                return False
            
            else:
                print(f"{R}✗ Login failed: {str(e)[:150]}{W}")
                return False
            
    except Exception as e:
        print(f"{R}✗ Error: {e}{W}")
        return False

def main():
    print(f"{C}{'='*60}{W}")
    print(f"{C}BIND INSTAGRAM SESSION TO CONFIG{W}")
    print(f"{C}{'='*60}{W}\n")
    
    print(f"{C}Step 1: Scanning accounts...{W}")
    accounts_without_session = scan_accounts()
    
    if not accounts_without_session:
        print(f"\n{G}✓ Semua akun dengan Instagram sudah punya session!{W}")
        return
    
    print(f"\n{Y}Found {len(accounts_without_session)} accounts without Instagram session{W}\n")
    
    print(f"{C}Step 2: Bind Instagram sessions{W}\n")
    print(f"Pilih opsi:")
    print(f"  1. Bind specific account")
    print(f"  2. Bind all accounts (batch)")
    print(f"  0. Cancel")
    
    choice = input(f"\n{C}Pilihan:{W} ").strip()
    
    if choice == '0':
        print(f"\n{Y}Cancelled{W}")
        return
    
    elif choice == '1':
        # Single account with loop
        while True:
            print(f"\n{C}Available accounts:{W}")
            for i, acc in enumerate(accounts_without_session, 1):
                print(f"  {i}. {acc['account']} - @{acc['ig_username']}")
            
            idx = input(f"\n{C}Select account number (0 to cancel):{W} ").strip()
            
            if idx == '0':
                print(f"\n{Y}Cancelled{W}")
                break
            
            try:
                idx = int(idx) - 1
                if idx < 0 or idx >= len(accounts_without_session):
                    print(f"{R}Invalid selection{W}")
                    continue
                
                acc_info = accounts_without_session[idx]
                ig_username = acc_info['ig_username']
                
                print(f"\n{C}Account:{W} {acc_info['account']}")
                print(f"{C}Instagram:{W} @{ig_username}")
                
                ig_password = input(f"\n{C}Enter Instagram password:{W} ").strip()
                
                if not ig_password:
                    print(f"{R}Password required{W}")
                    continue
                
                success = create_instagram_session(acc_info['account'], ig_username, ig_password)
                
                if success:
                    print(f"\n{G}✓ Successfully bound Instagram session!{W}")
                    # Remove from list
                    accounts_without_session.pop(idx)
                    
                    if not accounts_without_session:
                        print(f"\n{G}✓ All accounts bound!{W}")
                        break
                else:
                    print(f"\n{R}✗ Failed to bind Instagram session{W}")
                
                # Ask to continue
                cont = input(f"\n{C}Bind another account? (y/n):{W} ").strip().lower()
                if cont != 'y':
                    break
            
            except (ValueError, IndexError):
                print(f"{R}Invalid input{W}")
                continue
    
    elif choice == '2':
        # Batch mode
        print(f"\n{Y}Batch mode: You'll be prompted for password for each account{W}")
        print(f"{Y}Press Ctrl+C to skip an account{W}\n")
        
        confirm = input(f"Continue? (y/n): ").strip().lower()
        if confirm != 'y':
            print(f"\n{Y}Cancelled{W}")
            return
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        
        for acc_info in accounts_without_session:
            print(f"\n{C}{'='*60}{W}")
            print(f"{C}Account:{W} {acc_info['account']}")
            print(f"{C}Instagram:{W} @{acc_info['ig_username']}")
            
            try:
                ig_password = input(f"{C}Enter password (or press Enter to skip):{W} ").strip()
                
                if not ig_password:
                    print(f"{Y}Skipped{W}")
                    skipped_count += 1
                    continue
                
                success = create_instagram_session(acc_info['account'], acc_info['ig_username'], ig_password)
                
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                    
            except KeyboardInterrupt:
                print(f"\n{Y}Skipped{W}")
                skipped_count += 1
                continue
        
        print(f"\n{C}{'='*60}{W}")
        print(f"{C}Summary:{W}")
        print(f"  {G}Success:{W} {success_count}")
        print(f"  {R}Failed:{W} {failed_count}")
        print(f"  {Y}Skipped:{W} {skipped_count}")
        print(f"{C}{'='*60}{W}")
    
    else:
        print(f"{R}Invalid choice{W}")

if __name__ == '__main__':
    main()
