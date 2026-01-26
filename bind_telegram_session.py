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
    
    # Parse Telegram (try escaped quotes first)
    tg_match = re.search(r'data-platform=\\"telegram\\"[^>]*data-alias=\\"@([^"\\]+)\\"', html_content)
    if not tg_match:
        tg_match = re.search(r'data-platform="telegram"[^>]*data-alias="@([^"]+)"', html_content)
    if tg_match:
        tg_username = tg_match.group(1)
    
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

    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36',
        'X-XSRF-Token': xsrf,
        'X-Requested-With': 'XMLHttpRequest',
        'X-Ajax-Html': '1',
    }
    proxies = {'http': proxy_str, 'https': proxy_str} if proxy_str else None

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
    print("1. Single account")
    print("2. Batch (dari file)")
    print("3. Show list only (exit)")
    mode = input("\nPilihan (1/2/3): ").strip()
    
    if mode == '3':
        return
    
    if mode == '1':
        # Single mode - auto generate session
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
        # Batch mode
        print(f"\n{Y}Format file (JSON):{W}")
        print('[')
        print('  {')
        print('    "account": "account_72",')
        print('    "phone": "+628123456789"')
        print('  },')
        print('  {')
        print('    "account": "account_86",')
        print('    "phone": "+628987654321"')
        print('  }')
        print(']')
        
        file_path = input(f"\n{C}Path ke file JSON: {W}").strip()
        
        if not os.path.exists(file_path):
            print(f"{R}❌ File tidak ditemukan: {file_path}{W}")
            return
        
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            success = 0
            failed = 0
            
            for item in data:
                print(f"\n{C}{'='*60}{W}")
                result = generate_and_bind_session(item['account'], item['phone'])
                if result:
                    success += 1
                else:
                    failed += 1
            
            print(f"\n{C}{'='*60}{W}")
            print(f"{G}Selesai: {success} berhasil, {failed} gagal{W}")
            
        except Exception as e:
            print(f"{R}❌ Error membaca file: {e}{W}")
    
    else:
        print(f"{R}❌ Pilihan tidak valid!{W}")

if __name__ == '__main__':
    main()
