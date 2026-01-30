#!/usr/bin/env python3
"""
Bind Telegram string session ke config.json
Auto-detect akun yang sudah connect Telegram di web tapi belum ada session
"""

import json
import os
import sys
import re
import html
import requests
import concurrent.futures

ACCOUNTS_DIR = 'accounts'
DEFAULT_API_ID = 1724399
DEFAULT_API_HASH = '7f6c4af5220db320413ff672093ee102'
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
    
    # Parse email from init-data
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
    
    # Parse Telegram - look for data-platform="telegram" with any icon
    tg_patterns = [
        r'data-platform=\\"telegram\\"[^>]*data-alias=\\"@?([^"\\]+)\\"',
        r'data-platform="telegram"[^>]*data-alias="@?([^"]+)"',
        r'data-icon=\\"telegram[^"\\]*\\"[^>]*data-alias=\\"@?([^"\\]+)\\"',
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
    proxy_failed = False

    for domain in ['https://vkserfing.com', 'https://vkserfing.ru']:
        try:
            resp = requests.get(f'{domain}/settings', 
                               cookies=cookies, headers=headers, 
                               proxies=proxies, timeout=TIMEOUT)
            if resp.status_code == 200:
                try:
                    html_content = resp.json().get('html', '')
                    email, ig_username, tg_username = parse_settings_html(html_content)
                except Exception as e:
                    # Failed to parse JSON/HTML
                    pass
            break
        except (requests.exceptions.ProxyError, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            proxy_failed = True
            continue
        except Exception as e:
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
        'proxy_failed': proxy_failed
    }

def has_telegram_session(acc_name):
    """Check if account already has telegram session in config"""
    config_file = os.path.join(ACCOUNTS_DIR, acc_name, "config.json")
    try:
        with open(config_file) as f:
            config = json.load(f)
        return 'telegram' in config and config['telegram'].get('session_string')
    except:
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
                has_session = has_telegram_session(acc)
                
                # Determine status
                if tg != '-':
                    # Detected from web
                    if has_session:
                        status = f"{G}✓ Has session{W}"
                    else:
                        status = f"{Y}⚠ NO SESSION{W}"
                        results.append({'account': acc, 'telegram': tg, 'email': email, 'ig': ig})
                else:
                    # Not detected from web, check config
                    if has_session:
                        # Has session in config but not detected from web
                        config_file = os.path.join(ACCOUNTS_DIR, acc, "config.json")
                        try:
                            with open(config_file) as f:
                                cfg = json.load(f)
                            tg_from_config = cfg.get('telegram', {}).get('username', '')
                            if tg_from_config:
                                tg = tg_from_config
                                status = f"{C}✓ Config only{W}"
                            else:
                                status = f"{R}✗ No TG{W}"
                        except:
                            status = f"{R}✗ No TG{W}"
                    else:
                        status = f"{R}✗ No TG{W}"
                
                print(f"{acc:<15} | {email:<30} | {ig:<20} | {tg:<20} | {status}")
                    
            except Exception as e:
                print(f"{R}Error{W}: {e}")
    
    return results

def auto_rebind_from_session_files():
    """Auto-rebind accounts yang punya session file tapi belum ada string session di config"""
    
    print(f"\n{C}Scanning for existing session files...{W}\n")
    
    folders = sorted([f for f in os.listdir(ACCOUNTS_DIR) 
                     if os.path.isdir(os.path.join(ACCOUNTS_DIR, f)) and f.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    rebind_candidates = []
    
    for acc in folders:
        acc_dir = os.path.join(ACCOUNTS_DIR, acc)
        config_file = os.path.join(acc_dir, 'config.json')
        
        if not os.path.exists(config_file):
            continue
        
        try:
            with open(config_file) as f:
                config = json.load(f)
        except:
            continue
        
        # Check if already has valid string session
        tg_config = config.get('telegram', {})
        has_string_session = tg_config.get('session_string') and tg_config.get('session_string') != 'null'
        
        if has_string_session:
            continue  # Already bound
        
        # Look for .session files in account folder
        session_files = []
        try:
            for f in os.listdir(acc_dir):
                if f.endswith('.session'):
                    session_files.append(os.path.join(acc_dir, f))
        except:
            continue
        
        if session_files:
            rebind_candidates.append({
                'account': acc,
                'session_files': session_files
            })
    
    if not rebind_candidates:
        print(f"{G}✓ No accounts need rebinding{W}")
        return
    
    print(f"{Y}Found {len(rebind_candidates)} accounts with session files but no string session:{W}\n")
    for item in rebind_candidates:
        print(f"  {item['account']:<15} - {len(item['session_files'])} session file(s)")
        for sf in item['session_files']:
            print(f"    → {os.path.basename(sf)}")
    
    print(f"\n{C}Auto-rebind these accounts? (y/n):{W} ", end='')
    confirm = input().strip().lower()
    
    if confirm != 'y':
        print(f"{Y}Cancelled{W}")
        return
    
    success = 0
    failed = 0
    
    for item in rebind_candidates:
        account = item['account']
        # Use first session file found
        session_file = item['session_files'][0]
        
        print(f"\n{C}{'='*60}{W}")
        print(f"{C}Rebinding {account} from {os.path.basename(session_file)}...{W}")
        
        result = import_session_file(account, session_file)
        
        if result:
            success += 1
        else:
            failed += 1
    
    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Success: {success}{W} | {R}Failed: {failed}{W}")
    print(f"{C}{'='*60}{W}")

def import_session_file(account_folder, session_file_path):
    """Import existing Telegram session file (.session) ke config"""
    
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    
    if not os.path.exists(config_path):
        print(f"{R}❌ Config tidak ditemukan: {config_path}{W}")
        return False
    
    if not os.path.exists(session_file_path):
        print(f"{R}❌ Session file tidak ditemukan: {session_file_path}{W}")
        return False
    
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        
        print(f"\n{C}Importing session dari {session_file_path}...{W}")
        
        # Load session file
        session_name = session_file_path.replace('.session', '')
        client = TelegramClient(session_name, DEFAULT_API_ID, DEFAULT_API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            print(f"{R}❌ Session tidak valid atau expired{W}")
            client.disconnect()
            return False
        
        # Get user info
        me = client.get_me()
        
        # Convert to string session
        session_string = client.session.save()
        
        print(f"\n{G}✓ Session valid!{W}")
        print(f"  User: {me.first_name} (@{me.username})")
        print(f"  ID: {me.id}")
        
        # Update config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['telegram'] = {
            'bound': True,
            'api_id': DEFAULT_API_ID,
            'api_hash': DEFAULT_API_HASH,
            'phone': me.phone or '',
            'session_string': session_string,
            'user_id': me.id,
            'username': me.username or '',
            'first_name': me.first_name or ''
        }
        
        if 'task_types' not in config:
            config['task_types'] = {}
        config['task_types']['telegram_followers'] = True
        config['task_types']['telegram_views'] = True
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"{G}✓ Session berhasil di-import ke {account_folder}/config.json{W}")
        print(f"{C}  Telegram tasks auto-enabled{W}")
        
        client.disconnect()
        return True
        
    except ImportError:
        print(f"{R}❌ Module telethon tidak ditemukan!{W}")
        print(f"{Y}Install dengan: pip install telethon{W}")
        return False
    except Exception as e:
        print(f"{R}❌ Error: {e}{W}")
        import traceback
        traceback.print_exc()
        return False

def generate_and_bind_session(account_folder, phone):
    """Generate Telegram session dari phone number dan bind ke config"""
    
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    
    if not os.path.exists(config_path):
        print(f"{R}❌ Config tidak ditemukan: {config_path}{W}")
        return False
    
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import SessionPasswordNeededError
        
        print(f"\n{C}Generating session untuk {phone}...{W}")
        
        client = TelegramClient(StringSession(), DEFAULT_API_ID, DEFAULT_API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            print(f"{Y}Mengirim kode ke {phone}...{W}")
            client.send_code_request(phone)
            
            # Retry loop for OTP
            max_attempts = 3
            for attempt in range(max_attempts):
                code = input(f"{C}Masukkan kode OTP (attempt {attempt+1}/{max_attempts}): {W}").strip()
                
                try:
                    client.sign_in(phone, code)
                    break  # Success, exit loop
                except SessionPasswordNeededError:
                    # Need 2FA password
                    for pwd_attempt in range(max_attempts):
                        password = input(f"{Y}Masukkan 2FA Password (attempt {pwd_attempt+1}/{max_attempts}): {W}").strip()
                        try:
                            client.sign_in(password=password)
                            break  # Success
                        except Exception as e:
                            if pwd_attempt < max_attempts - 1:
                                print(f"{R}❌ Password salah, coba lagi...{W}")
                            else:
                                print(f"{R}❌ Gagal setelah {max_attempts} percobaan{W}")
                                raise
                    break  # Exit OTP loop after 2FA
                except Exception as e:
                    if 'PhoneCodeInvalid' in str(e) or 'phone code' in str(e).lower():
                        if attempt < max_attempts - 1:
                            print(f"{R}❌ Kode OTP salah, coba lagi...{W}")
                        else:
                            print(f"{R}❌ Gagal setelah {max_attempts} percobaan{W}")
                            raise
                    else:
                        raise
        
        me = client.get_me()
        session_string = client.session.save()
        
        print(f"\n{G}✓ Login berhasil!{W}")
        print(f"  User: {me.first_name} (@{me.username})")
        print(f"  ID: {me.id}")
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['telegram'] = {
            'bound': True,
            'api_id': DEFAULT_API_ID,
            'api_hash': DEFAULT_API_HASH,
            'phone': phone,
            'session_string': session_string,
            'user_id': me.id,
            'username': me.username or '',
            'first_name': me.first_name or ''
        }
        
        if 'task_types' not in config:
            config['task_types'] = {}
        config['task_types']['telegram_followers'] = True
        config['task_types']['telegram_views'] = True
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"{G}✓ Session berhasil disimpan ke {account_folder}/config.json{W}")
        print(f"{C}  Telegram tasks auto-enabled{W}")
        
        client.disconnect()
        return True
        
    except ImportError:
        print(f"{R}❌ Module telethon tidak ditemukan!{W}")
        print(f"{Y}Install dengan: pip install telethon{W}")
        return False
    except Exception as e:
        print(f"{R}❌ Error: {e}{W}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("BIND TELEGRAM SESSION TO CONFIG")
    print("=" * 60)
    
    # Scan dulu
    print(f"\n{C}Step 1: Scanning accounts...{W}")
    missing_sessions = scan_accounts()
    
    if not missing_sessions:
        print(f"\n{G}✓ Semua akun dengan Telegram sudah punya session!{W}")
        return
    
    print(f"\n{Y}{'='*60}{W}")
    print(f"{Y}Found {len(missing_sessions)} accounts dengan Telegram tapi belum ada session:{W}")
    print(f"{Y}{'='*60}{W}")
    for item in missing_sessions:
        print(f"  {item['account']:<15} | Email: {item['email']:<30} | IG: {item['ig']:<15} | TG: @{item['telegram']}")
    print(f"{Y}{'='*60}{W}")
    
    print(f"\n{C}Step 2: Bind sessions{W}")
    
    # Input mode
    print("\nPilih mode:")
    print("1. Generate new session (phone + OTP)")
    print("2. Import existing session file (.session)")
    print("3. Auto-rebind from existing session files")
    print("4. Show list only (exit)")
    mode = input("\nPilihan (1/2/3/4): ").strip()
    
    if mode == '4':
        return
    
    if mode == '1':
        # Generate new session
        account = input(f"\n{C}Nama folder account (contoh: account_72): {W}").strip()
        phone = input(f"{C}Nomor HP (contoh: +628123456789): {W}").strip()
        
        if not account or not phone:
            print(f"{R}❌ Account dan phone harus diisi!{W}")
            return
        
        if not phone.startswith('+'):
            print(f"{Y}⚠ Phone number harus diawali dengan + (contoh: +628123456789){W}")
            confirm = input(f"{Y}Lanjutkan? (y/n): {W}").strip().lower()
            if confirm != 'y':
                return
        
        generate_and_bind_session(account, phone)
        
    elif mode == '2':
        # Import existing session file
        account = input(f"\n{C}Nama folder account (contoh: account_10): {W}").strip()
        session_file = input(f"{C}Path ke session file (contoh: telegram_account_1.session): {W}").strip()
        
        if not account or not session_file:
            print(f"{R}❌ Account dan session file harus diisi!{W}")
            return
        
        import_session_file(account, session_file)
    
    elif mode == '3':
        # Auto-rebind from existing session files
        auto_rebind_from_session_files()
    
    else:
        print(f"{R}❌ Pilihan tidak valid!{W}")

if __name__ == '__main__':
    main()
