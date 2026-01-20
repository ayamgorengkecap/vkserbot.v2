#!/usr/bin/env python3
"""
VKSerfing Multi-Account Manager
Menjalankan multiple akun secara sequential (satu per satu)
"""

import os
import sys
import json
import time
import signal
import random
import re
import requests
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'lib'))

from automation_core import VKSerfingBot, Colors, clear, DeviceFingerprintGenerator


G, R, Y, C, W = Colors.GREEN, Colors.RED, Colors.YELLOW, Colors.CYAN, Colors.RESET


STOP_FLAG = False

def signal_handler(sig, frame):
    global STOP_FLAG
    if STOP_FLAG:

        print(f"\n\n{R}⏹ Force exit!{W}")
        sys.exit(0)
    print(f"\n\n{Y}⏸ Stopping... (Ctrl+C detected){W}")
    STOP_FLAG = True

signal.signal(signal.SIGINT, signal_handler)


MAX_WORKERS = 10
REQUEST_TIMEOUT = 15

def process_accounts_parallel(accounts, process_func, desc="Processing"):
    """
    Generic parallel processor for accounts.

    Args:
        accounts: list of account names or (account_name, config) tuples
        process_func: function(account_name, config) -> dict with 'status', 'data', etc
        desc: description for logging

    Returns:
        list of results from process_func
    """
    global STOP_FLAG
    results = []
    total = len(accounts)

    print(f"\n{C}[INFO] {desc} {total} accounts (parallel, workers={MAX_WORKERS}){W}\n")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:

        futures = {}
        for acc in accounts:
            if STOP_FLAG:
                break
            if isinstance(acc, tuple):
                acc_name, config = acc
            else:
                acc_name = acc
                config = load_account_config(acc_name)

            if config:
                futures[executor.submit(process_func, acc_name, config)] = acc_name


        done = 0
        for future in as_completed(futures):
            if STOP_FLAG:
                break
            acc_name = futures[future]
            done += 1
            try:
                result = future.result(timeout=30)
                results.append(result)


                status = result.get('status', 'unknown')
                if status == 'success':
                    print(f"  [{done}/{total}] {G}[OK]{W} {acc_name} - {result.get('message', '')}")
                elif status == 'skip':
                    print(f"  [{done}/{total}] {Y}[SKIP]{W} {acc_name} - {result.get('message', '')}")
                else:
                    print(f"  [{done}/{total}] {R}[FAIL]{W} {acc_name} - {result.get('message', '')}")

            except Exception as e:
                results.append({'account': acc_name, 'status': 'error', 'message': str(e)})
                print(f"  [{done}/{total}] {R}[ERROR]{W} {acc_name} - {str(e)[:50]}")

    return results

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


TELEGRAM_BOT_TOKEN = "8442831261:AAEooy7Aeq_AlSGk3r-B46O_005xmNjhW-c"
TELEGRAM_CHAT_ID = "7976183288"
TELEGRAM_LAST_UPDATE_ID = 0

def send_telegram_message(message, parse_mode='HTML'):
    """Send message to Telegram"""
    try:
        import urllib.request
        import urllib.parse

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': parse_mode
        }).encode('utf-8')

        req = urllib.request.Request(url, data=data)
        response = urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as e:
        print(f"{R}✗ Gagal kirim Telegram: {e}{W}")
        return False

def send_telegram_report(account_name, vk_id, ig_username, telegram_username, balance, success_count, error_count):
    """Send report to Telegram with monospace format"""
    message = f"""<pre>
━━━━━━━━━━━━━━━━━━━━━━
  ACCOUNT REPORT
━━━━━━━━━━━━━━━━━━━━━━

Account : {account_name}
VK ID   : {vk_id if vk_id else '-'}
IG      : {ig_username if ig_username else '-'}
Email   : -
Tele    : {telegram_username if telegram_username else '-'}
Saldo   : {balance:.2f}₽
Success : {success_count}
Error   : {error_count}

━━━━━━━━━━━━━━━━━━━━━━
</pre>"""
    return send_telegram_message(message)

def send_telegram_otp_alert(account_name, username, password, error_msg):
    """Send OTP/Verification alert to Telegram with account details"""


    is_phone_challenge = 'submit_phone' in error_msg or 'ChallengeResolve' in error_msg

    if is_phone_challenge:
        message = f"""<b>📱 Instagram PHONE VERIFICATION Required</b>

<b>Account:</b> {account_name}
<b>Username/Email:</b> <code>{username}</code>
<b>Password:</b> <code>{password}</code>

<b>Error Type:</b> Phone Number Challenge
{error_msg[:250]}

<b>🚨 CRITICAL Action Required:</b>
1. Login via Instagram app/browser
2. Instagram akan minta NOMOR HP untuk verifikasi
3. Submit nomor HP yang valid
4. Verifikasi dengan SMS code
5. Setelah selesai, bot akan normal lagi

<b>Note:</b> IG tasks akan di-skip sampai verifikasi selesai. VK tasks tetap jalan."""
    else:
        message = f"""<b>🔐 Instagram Verification Required</b>

<b>Account:</b> {account_name}
<b>Username/Email:</b> <code>{username}</code>
<b>Password:</b> <code>{password}</code>

<b>Error:</b>
{error_msg[:200]}

<b>⚠️ Action Required:</b>
1. Check email for OTP/verification code
2. Login manual via browser/app
3. Bot akan retry otomatis setelah berhasil

<b>Note:</b> IG tasks akan di-skip sampai verification selesai. VK tasks tetap jalan."""

    return send_telegram_message(message)

def send_account_to_telegram(folder_name, config):
    """Send account data to Telegram"""

    cookies = config.get('credentials', {}).get('cookies', {})
    xsrf = config.get('credentials', {}).get('xsrf_token', '')

    cookie_lines = []
    if xsrf:
        cookie_lines.append(f"x-xsrf-token: {xsrf}")
    for key, value in cookies.items():
        cookie_lines.append(f"cookie: {key}={value}")

    cookie_text = '\n'.join(cookie_lines) if cookie_lines else 'NONE'


    vk_api = config.get('vk_api', {})
    vk_url = None
    if vk_api.get('enabled') and vk_api.get('access_token'):
        vk_url = f"https://oauth.vk.com/blank.html#access_token={vk_api['access_token']}&user_id={vk_api['user_id']}"


    ig = config.get('instagram', {})
    ig_user = ig.get('username') if ig.get('enabled') else None
    ig_pass = ig.get('password') if ig.get('enabled') else None
    ig_session = 'NONE'


    if ig_user:
        import base64
        import json
        session_file = os.path.join(ACCOUNTS_DIR, folder_name, f'ig_session_{ig_user}.json')
        if os.path.exists(session_file):
            try:
                with open(session_file, 'r') as f:
                    session_data = json.load(f)

                session_json = json.dumps(session_data)
                ig_session = base64.b64encode(session_json.encode()).decode()
            except:
                ig_session = 'NONE'


    message = f"""<pre>
━━━━━━━━━━━━━━━━━━━━━━
  ACCOUNT DATA
━━━━━━━━━━━━━━━━━━━━━━

Kirim balik message ini untuk mengupdate akun

[ACCOUNT_NAME]
{folder_name}
[/ACCOUNT_NAME]

[COOKIE]
{cookie_text}
[/COOKIE]

[VK_TOKEN]
{vk_url if vk_url else 'NONE'}
[/VK_TOKEN]

[INSTAGRAM]
{ig_user if ig_user else 'NONE'}
{ig_pass if ig_pass else 'NONE'}
[/INSTAGRAM]

[IG_SESSION]
{ig_session}
[/IG_SESSION]

━━━━━━━━━━━━━━━━━━━━━━
</pre>"""
    return send_telegram_message(message)

def parse_account_data(text):
    """Parse account data from Telegram message"""
    import re

    data = {
        'account_name': None,
        'cookie': None,
        'vk_url': None,
        'ig_user': None,
        'ig_pass': None,
        'ig_session': None
    }


    name_match = re.search(r'\[ACCOUNT_NAME\](.*?)\[/ACCOUNT_NAME\]', text, re.DOTALL)
    if name_match:
        data['account_name'] = name_match.group(1).strip()


    cookie_match = re.search(r'\[COOKIE\](.*?)\[/COOKIE\]', text, re.DOTALL)
    if cookie_match:
        data['cookie'] = cookie_match.group(1).strip()


    vk_match = re.search(r'\[VK_TOKEN\](.*?)\[/VK_TOKEN\]', text, re.DOTALL)
    if vk_match:
        vk_text = vk_match.group(1).strip()
        if vk_text != 'NONE':
            data['vk_url'] = vk_text


    ig_match = re.search(r'\[INSTAGRAM\](.*?)\[/INSTAGRAM\]', text, re.DOTALL)
    if ig_match:
        ig_text = ig_match.group(1).strip()
        if ig_text != 'NONE\nNONE':
            lines = ig_text.split('\n')
            if len(lines) >= 2:
                data['ig_user'] = lines[0].strip() if lines[0] != 'NONE' else None
                data['ig_pass'] = lines[1].strip() if lines[1] != 'NONE' else None


    ig_session_match = re.search(r'\[IG_SESSION\](.*?)\[/IG_SESSION\]', text, re.DOTALL)
    if ig_session_match:
        ig_session_text = ig_session_match.group(1).strip()
        if ig_session_text != 'NONE':
            data['ig_session'] = ig_session_text

    return data

def create_account_from_telegram_data(data):
    """Create or update account from Telegram data"""
    try:

        if data['account_name']:
            folder_name = data['account_name']
            folder_path = os.path.join(ACCOUNTS_DIR, folder_name)


            if os.path.exists(folder_path):

                existing_config = load_account_config(folder_name)


                has_update = False


                if data['cookie']:
                    new_cookies = {}
                    new_xsrf = ""
                    for line in data['cookie'].split('\n'):
                        line = line.strip()
                        if line.lower().startswith('x-xsrf-token:'):
                            new_xsrf = line.split(':', 1)[1].strip()
                        if line.lower().startswith('cookie:'):
                            cookie_part = line.split(':', 1)[1].strip()
                            for pair in cookie_part.split(';'):
                                if '=' in pair:
                                    parts = pair.strip().split('=', 1)
                                    if len(parts) == 2:
                                        new_cookies[parts[0].strip()] = parts[1].strip()

                    old_cookies = existing_config.get('credentials', {}).get('cookies', {})
                    if new_cookies.get('vkstoken') != old_cookies.get('vkstoken'):
                        has_update = True


                if data['vk_url']:
                    import re
                    token_match = re.search(r'access_token=([^&\s]+)', data['vk_url'])
                    if token_match:
                        new_token = token_match.group(1)
                        old_token = existing_config.get('vk_api', {}).get('access_token', '')
                        if new_token != old_token:
                            has_update = True


                if data['ig_user']:
                    old_ig = existing_config.get('instagram', {}).get('username', '')
                    if data['ig_user'] != old_ig:
                        has_update = True

                if not has_update:
                    return None
            else:

                pass
        else:

            folders = get_account_folders()
            if folders:
                last_num = max([int(f.split('_')[1]) for f in folders if '_' in f])
                next_num = last_num + 1
            else:
                next_num = 1

            folder_name = f"account_{next_num}"

        folder_path = os.path.join(ACCOUNTS_DIR, folder_name)


        os.makedirs(folder_path, exist_ok=True)


        config = {
            "credentials": {
                "cookies": {},
                "xsrf_token": ""
            },
            "settings": {
                "wait_time_min": 11,
                "wait_time_max": 21,
                "delay_between_tasks": 5,
                "auto_mode": True
            },
            "task_types": {
                "vk_friends": True,
                "vk_groups": True,
                "vk_likes": True,
                "vk_reposts": True,
                "vk_polls": True,
                "vk_videos": True,
                "vk_views": True,
                "telegram_followers": False,
                "telegram_views": False,
                "instagram_followers": True,
                "instagram_likes": True,
                "instagram_comments": True,
                "instagram_videos": True
            },
            "vk_api": {
                "enabled": False,
                "access_token": "",
                "user_id": ""
            },
            "instagram": {
                "enabled": False,
                "username": "",
                "password": ""
            }
        }


        if data['cookie']:
            cookies = {}
            xsrf = ""

            for line in data['cookie'].split('\n'):
                line = line.strip()

                if line.lower().startswith('x-xsrf-token:'):
                    xsrf = line.split(':', 1)[1].strip()

                if line.lower().startswith('cookie:'):
                    cookie_part = line.split(':', 1)[1].strip()
                    for pair in cookie_part.split(';'):
                        if '=' in pair:
                            parts = pair.strip().split('=', 1)
                            if len(parts) == 2:
                                cookies[parts[0].strip()] = parts[1].strip()

            if cookies.get('vkstoken'):
                config['credentials']['cookies'] = cookies
                config['credentials']['xsrf_token'] = xsrf


        if data['vk_url']:
            import re
            token_match = re.search(r'access_token=([^&\s]+)', data['vk_url'])
            user_id_match = re.search(r'user_id=(\d+)', data['vk_url'])
            if token_match and user_id_match:
                config['vk_api']['enabled'] = True
                config['vk_api']['access_token'] = token_match.group(1)
                config['vk_api']['user_id'] = user_id_match.group(1)


        if data['ig_user'] and data['ig_pass']:
            config['instagram']['enabled'] = True
            config['instagram']['username'] = data['ig_user']
            config['instagram']['password'] = data['ig_pass']


            if data['ig_session']:
                import base64
                import json
                try:

                    session_json = base64.b64decode(data['ig_session']).decode()
                    session_data = json.loads(session_json)


                    session_file = os.path.join(folder_path, f"ig_session_{data['ig_user']}.json")
                    with open(session_file, 'w') as f:
                        json.dump(session_data, f, indent=4)

                    print(f"{G}  ✓ Instagram session restored{W}")
                except Exception as e:
                    print(f"{Y}  ⚠ Gagal restore IG session: {e}{W}")


        save_account_config(folder_name, config)

        return folder_name
    except Exception as e:
        print(f"{R}✗ Error create account: {e}{W}")
        return None

def check_telegram_updates():
    """Check Telegram for account data messages"""
    global TELEGRAM_LAST_UPDATE_ID

    try:
        import urllib.request
        import json

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        url += f"?offset={TELEGRAM_LAST_UPDATE_ID + 1}&timeout=1"

        req = urllib.request.Request(url)
        response = urllib.request.urlopen(req, timeout=5)
        result = json.loads(response.read().decode('utf-8'))

        if result.get('ok') and result.get('result'):
            for update in result['result']:
                TELEGRAM_LAST_UPDATE_ID = update['update_id']

                message = update.get('message', {})


                text = message.get('text', '')


                if not text:
                    text = message.get('caption', '')


                if '[ACCOUNT_NAME]' in text:
                    print(f"\n{C}[Telegram] Menerima data akun...{W}")


                if '[ACCOUNT_NAME]' in text and '[COOKIE]' in text:

                    data = parse_account_data(text)

                    if data['cookie']:

                        print(f"{C}[Telegram] Memproses akun: {data.get('account_name', 'baru')}...{W}")
                        folder_name = create_account_from_telegram_data(data)

                        if folder_name:
                            if data['account_name']:
                                msg = f"✅ Akun <b>{folder_name}</b> berhasil diupdate!\n\n"
                                msg += f"Cookie: {'Updated' if data['cookie'] else 'No change'}\n"
                                msg += f"VK Token: {'Updated' if data['vk_url'] else 'No change'}\n"
                                msg += f"Instagram: {'Updated' if data['ig_user'] else 'No change'}\n\n"
                                msg += f"Akun akan dijalankan pada cycle berikutnya."
                                send_telegram_message(msg)
                            else:
                                send_telegram_message(f"✅ Akun baru berhasil ditambahkan: <b>{folder_name}</b>\n\nAkun akan dijalankan pada cycle berikutnya.")
                            print(f"{G}[Telegram] ✓ Akun {folder_name} berhasil diproses{W}")
                            return folder_name
                        elif folder_name is None and data['account_name']:
                            send_telegram_message(f"ℹ️ Akun <b>{data['account_name']}</b> tidak ada perubahan.\n\nData sudah sama dengan yang ada di server.")
                            print(f"{Y}[Telegram] ℹ Akun {data['account_name']} tidak ada perubahan{W}")
                        else:
                            send_telegram_message("❌ Gagal membuat/update akun. Periksa format data.")
                            print(f"{R}[Telegram] ✗ Gagal memproses akun{W}")
                    else:
                        send_telegram_message("❌ Data cookie tidak ditemukan atau tidak valid.\n\nPastikan message berisi tag [COOKIE]...[/COOKIE]")
                        print(f"{R}[Telegram] ✗ Cookie tidak valid{W}")

        return None
    except Exception as e:

        if str(e):
            print(f"{R}[Telegram] Error polling: {e}{W}")
        return None


ACCOUNTS_DIR = "accounts"
LIB_DIR = "lib"

def get_account_folders():
    """Get all account folders sorted"""
    if not os.path.exists(ACCOUNTS_DIR):
        return []

    folders = []
    for item in os.listdir(ACCOUNTS_DIR):
        path = os.path.join(ACCOUNTS_DIR, item)
        if os.path.isdir(path) and os.path.exists(os.path.join(path, 'config.json')):
            folders.append(item)


    folders.sort(key=lambda x: int(x.split('_')[1]) if '_' in x else 0)
    return folders

def load_account_config(account_folder):
    """Load config.json from account folder"""
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    if not os.path.exists(config_path):
        return None

    with open(config_path, 'r') as f:
        return json.load(f)

def save_account_config(account_folder, config):
    """Save config.json to account folder"""
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)

def get_account_info(config, account_folder=None):
    """Extract account info from config"""
    info = {}


    vk = config.get('vk_api', {})
    if vk.get('enabled'):
        info['vk'] = f"id{vk.get('user_id', '?')}"


    ig = config.get('instagram', {})
    if ig.get('enabled'):
        info['ig'] = f"@{ig.get('username', '?')}"


    if account_folder:
        tg_session = os.path.join(ACCOUNTS_DIR, account_folder, 'telegram_session.json')
        if os.path.exists(tg_session):
            try:
                with open(tg_session, 'r') as f:
                    tg_data = json.load(f)

                    for key, sess in tg_data.items():
                        if sess.get('valid'):
                            info['tg'] = f"@{sess.get('username', '?')}"
                            break
            except:
                pass

    return info

def type_text(text, delay=0.03):
    """Print text with typing effect"""
    import sys
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def show_loading_bar(length=50, delay=0.02):
    """Show animated loading bar"""
    import sys
    sys.stdout.write(f"{Y}[{W}")
    for i in range(length):
        sys.stdout.write("━")
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(f"{Y}]{W} {G}100%{W}\n")
    sys.stdout.flush()

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
    print(f"{C}│{W}  {Y}▶{W} Multi-Account Automation Framework {Y}v2.0{W}             {C}│{W}")
    print(f"{C}│{W}  {Y}▶{W} VK · Instagram · Telegram Multi-Platform            {C}│{W}")
    print(f"{C}│{W}  {Y}▶{W} Status: {G}[ONLINE]{W} {Y}|{W} Mode: {C}[MULTI-ACCOUNT]{W}             {C}│{W}")
    print(f"{C}└{'─' * 58}┘{W}\n")

def show_startup():
    """Show startup banner"""
    clear()


    print(f"{C}┌{'─' * 58}┐{W}")
    print(f"{C}│{W}  {G}██╗   ██╗{C}██╗  ██╗{R}███████╗{W}███████╗██████╗ ███████╗  {C}│{W}")
    print(f"{C}│{W}  {G}██║   ██║{C}██║ ██╔╝{R}██╔════╝{W}██╔════╝██╔══██╗██╔════╝  {C}│{W}")
    print(f"{C}│{W}  {G}██║   ██║{C}█████╔╝ {R}███████╗{W}█████╗  ██████╔╝█████╗    {C}│{W}")
    print(f"{C}│{W}  {G}╚██╗ ██╔╝{C}██╔═██╗ {R}╚════██║{W}██╔══╝  ██╔══██╗██╔══╝    {C}│{W}")
    print(f"{C}│{W}   {G}╚████╔╝ {C}██║  ██╗{R}███████║{W}███████╗██║  ██║██║       {C}│{W}")
    print(f"{C}│{W}    {G}╚═══╝  {C}╚═╝  ╚═╝{R}╚══════╝{W}╚══════╝╚═╝  ╚═╝╚═╝       {C}│{W}")
    print(f"{C}├{'─' * 58}┤{W}")
    print(f"{C}│{W}  {Y}▶{W} Multi-Account Automation Framework {Y}v2.0{W}             {C}│{W}")
    print(f"{C}│{W}  {Y}▶{W} VK · Instagram · Telegram Multi-Platform            {C}│{W}")
    print(f"{C}└{'─' * 58}┘{W}\n")

def show_accounts_list():
    """Display all accounts with their info"""
    folders = get_account_folders()

    if not folders:
        print(f"{Y}Tidak ada akun tersedia.{W}\n")
        return folders

    print(f"{C}Daftar Akun:{W}\n")

    for idx, folder in enumerate(folders, 1):
        config = load_account_config(folder)
        if not config:
            continue

        info = get_account_info(config, folder)


        print(f"  {idx}. {G}{folder}{W}")

        platforms = []
        if info.get('vk'):
            platforms.append(f"VK: {info['vk']}")
        if info.get('ig'):
            platforms.append(f"IG: {info['ig']}")
        if info.get('tg'):
            platforms.append(f"TG: {info['tg']}")

        if platforms:
            print(f"     {' | '.join(platforms)}")
        else:
            print(f"     {Y}(tidak ada platform aktif){W}")

        print()

    return folders

def run_selected_accounts():
    """Run selected accounts"""
    global STOP_FLAG


    used_ips = {}

    show_header()
    print(f"{C}[Pilih & Jalankan Akun]{W}\n")

    folders = show_accounts_list()

    if not folders:
        print(f"{Y}Tidak ada akun untuk dijalankan.{W}")
        input("\nEnter untuk kembali...")
        return

    print(f"\n{Y}Pilih akun yang mau dijalankan:{W}")
    print(f"  • Pisahkan dengan koma: 1,3,5")
    print(f"  • Range: 1-5")
    print(f"  • Semua: all atau *")
    print(f"  • Batal: 0\n")

    choice = input("Pilih: ").strip()

    if choice == '0':
        return


    selected_indices = set()

    if choice.lower() in ['all', '*', '']:
        selected_indices = set(range(len(folders)))
    else:
        try:
            parts = choice.split(',')
            for part in parts:
                part = part.strip()
                if '-' in part:

                    start, end = part.split('-')
                    start = int(start.strip()) - 1
                    end = int(end.strip())
                    selected_indices.update(range(start, end))
                else:

                    selected_indices.add(int(part) - 1)
        except:
            print(f"\n{R}✗ Format tidak valid!{W}")
            input("\nEnter untuk kembali...")
            return


    selected_indices = [i for i in selected_indices if 0 <= i < len(folders)]

    if not selected_indices:
        print(f"\n{Y}Tidak ada akun yang dipilih.{W}")
        input("\nEnter untuk kembali...")
        return


    selected_folders = [folders[i] for i in sorted(selected_indices)]

    print(f"\n{C}Akun yang akan dijalankan:{W}")
    for i, folder in enumerate(selected_folders, 1):
        print(f"  {i}. {G}{folder}{W}")

    print(f"\n{Y}Mode: Sequential (satu per satu dalam loop){W}")
    print(f"{Y}Tekan Ctrl+C untuk menghentikan.{W}\n")

    input("Enter untuk mulai...")

    cycle = 0
    grand_total_earned = 0.0


    STOP_FLAG = False


    while not STOP_FLAG:

        all_folders = get_account_folders()


        selected_folders = [f for f in selected_folders if f in all_folders]

        if not selected_folders:
            print(f"\n{Y}Tidak ada akun. Menunggu 30 detik...{W}")

            for _ in range(30):
                if STOP_FLAG:
                    break
                time.sleep(1)
            continue


        try:
            new_account = check_telegram_updates()
            if new_account and new_account not in selected_folders:
                print(f"\n{C}[Telegram] Akun baru ditambahkan: {new_account}{W}")
                print(f"{Y}Gunakan menu untuk menambahkan ke daftar yang dijalankan{W}")
        except Exception as e:

            pass

        cycle += 1

        print(f"\n{'='*50}")
        print(f"{C}[CYCLE #{cycle}]{W}")
        print(f"{'='*50}\n")

        cycle_earned = 0.0
        success_count = 0
        account_balances = {}
        banned_accounts = []
        rate_limited_accounts = []
        used_ips = {}

        for idx, folder in enumerate(selected_folders, 1):
            if STOP_FLAG:
                print(f"\n{Y}⏸ Dihentikan oleh user{W}")
                break

            print(f"\n{'='*50}")
            print(f"{C}[{idx}/{len(selected_folders)}] {folder}{W}")
            print(f"{'='*50}\n")


            config = load_account_config(folder)
            if not config:
                print(f"{R}✗ Gagal load config{W}")
                continue


            account_path = os.path.join(ACCOUNTS_DIR, folder)
            original_cwd = os.getcwd()


            account_success = 0
            account_error = 0

            try:
                os.chdir(account_path)


                bot = VKSerfingBot(config, account_name=folder)


                current_ip = None
                is_account_1 = (folder == 'account_1')

                if bot.proxy_info:
                    current_ip = bot.proxy_info.get('ip')
                else:

                    from automation_core import get_ip_location
                    direct_info = get_ip_location(timeout=5)
                    if direct_info:
                        current_ip = direct_info.get('ip')


                if current_ip and current_ip in used_ips and not (account_name == 'account_1' and not bot.proxy_info):
                    other_account = used_ips[current_ip]
                    print(f"{R}⚠️  IP COLLISION DETECTED!{W}")
                    print(f"{R}   IP {current_ip} sudah digunakan oleh {other_account}{W}")
                    print(f"{Y}   Fetching new proxy untuk {folder}...{W}\n")


                    if hasattr(bot, 'proxy_manager') and bot.proxy_manager:

                        exclude_ips = set(used_ips.keys())

                        print(f"{C}[Auto-Fetch] Mencari proxy baru (exclude {len(exclude_ips)} IPs)...{W}")


                        exclude_proxies = set()
                        for existing_folder in folders[:idx]:
                            existing_config = load_account_config(existing_folder)
                            if existing_config and existing_config.get('proxy'):
                                proxy_str = existing_config['proxy'].get('proxy_string')
                                if proxy_str:
                                    exclude_proxies.add(proxy_str)


                        success, new_proxy_dict, new_ip_info = bot.proxy_manager.auto_discover_proxy(
                            exclude_proxies=exclude_proxies,
                            protocol='http'
                        )

                        if success and new_proxy_dict and new_ip_info:

                            bot.proxy_dict = new_proxy_dict
                            bot.proxy_info = new_ip_info
                            current_ip = new_ip_info.get('ip')


                            config['proxy'] = {
                                'proxy_string': new_proxy_dict['raw'],
                                'ip': new_ip_info['ip'],
                                'country': new_ip_info.get('country', 'Unknown'),
                                'country_code': new_ip_info.get('country_code', ''),
                                'city': new_ip_info.get('city', 'Unknown'),
                                'region': new_ip_info.get('region', ''),
                                'isp': new_ip_info.get('isp', ''),
                                'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                            }

                            print(f"{G}✓ New proxy bound: {new_ip_info['ip']} ({new_ip_info['country']}){W}\n")
                        else:
                            print(f"{R}✗ Failed to get new proxy, skipping {folder}{W}\n")
                            os.chdir(original_cwd)
                            continue
                    else:
                        print(f"{R}✗ No proxy manager available, skipping {folder}{W}\n")
                        os.chdir(original_cwd)
                        continue


                if current_ip:
                    used_ips[current_ip] = folder
                    if is_account_1:
                        print(f"{Y}[IP TRACKING] {current_ip} → {folder} (Direct Connection){W}")
                    else:
                        print(f"{C}[IP TRACKING] {current_ip} → {folder}{W}")


                if bot.proxy_info:
                    from automation_core import format_ip_location
                    ip_display = format_ip_location(bot.proxy_info, detailed=True)
                    proxy_status = f"{C}[PROXY]{W}"
                else:

                    from automation_core import get_ip_location, format_ip_location
                    direct_info = get_ip_location(timeout=10)
                    if direct_info:
                        ip_display = format_ip_location(direct_info, detailed=True)
                    else:
                        ip_display = f"🌍 Unknown"
                    proxy_status = f"{Y}[DIRECT]{W}"

                print(f"{proxy_status} {ip_display}")


                if hasattr(bot, 'user_agent_data') and bot.user_agent_data:
                    from automation_core import UserAgentGenerator
                    device_info = UserAgentGenerator.get_device_info(bot.user_agent_data)
                    print(f"{C}[DEVICE]{W} {device_info}")

                print()


                try:
                    original_run = bot.run
                    def run_with_stop_check():
                        if STOP_FLAG:
                            return
                        return original_run()
                    bot.run = run_with_stop_check
                    bot.run()


                    if hasattr(bot, 'is_banned') and bot.is_banned:
                        banned_accounts.append({
                            'name': folder,
                            'balance': bot.balance,
                            'vks_email': getattr(bot, 'server_email', 'N/A')
                        })


                    rate_limit_info = {}


                    if hasattr(bot, 'vk_flood_control_until'):
                        if time.time() < bot.vk_flood_control_until:
                            remaining = int(bot.vk_flood_control_until - time.time())
                            rate_limit_info['vk_flood'] = f"{remaining}s"


                    if hasattr(bot, 'ig') and bot.ig and hasattr(bot.ig, 'rate_limited_actions'):
                        for action, until_time in bot.ig.rate_limited_actions.items():
                            if time.time() < until_time:
                                remaining_min = int((until_time - time.time()) / 60)
                                rate_limit_info[f'ig_{action}'] = f"{remaining_min}m"


                    if rate_limit_info:
                        rate_limited_accounts.append({
                            'name': folder,
                            'limits': rate_limit_info
                        })
                except KeyboardInterrupt:
                    raise
                except Exception as run_error:
                    print(f"{R}✗ Error saat run: {run_error}{W}")
                    account_error += 1

                if STOP_FLAG:
                    os.chdir(original_cwd)
                    break


                balance_after = bot.balance
                earned = bot.earned
                cycle_earned += earned


                if hasattr(bot, 'completed_tasks'):
                    account_success = bot.completed_tasks
                if hasattr(bot, 'failed_tasks'):
                    account_error = bot.failed_tasks

                success_count += 1


                ig_username = config.get('instagram', {}).get('username', 'N/A')
                account_balances[folder] = {
                    'ig_name': ig_username,
                    'balance': balance_after,
                    'earned': earned
                }


                if earned > 0:
                    print(f"\n{G}✓ {folder} selesai (+{earned:.2f}₽){W}\n")
                elif earned < 0:
                    print(f"\n{Y}✓ {folder} selesai ({earned:.2f}₽){W}\n")
                else:
                    print(f"\n{Y}✓ {folder} selesai (±0.00₽){W}\n")


                info = get_account_info(config, folder)
                vk_id = info.get('vk', '').replace('id', '') if info.get('vk') else None
                ig_user = info.get('ig', '').replace('@', '') if info.get('ig') else None
                tg_user = info.get('tg', '').replace('@', '') if info.get('tg') else None


                if cycle % 10 == 0:
                    print(f"{C}Mengirim laporan ke Telegram (cycle #{cycle})...{W}")
                    if send_telegram_report(folder, vk_id, ig_user, tg_user, balance_after, account_success, account_error):
                        print(f"{G}✓ Laporan terkirim{W}\n")
                    else:
                        print(f"{Y}⚠ Laporan gagal dikirim{W}\n")
                else:
                    print(f"{Y}ℹ Report disimpan (akan dikirim di cycle #{((cycle // 10) + 1) * 10}){W}\n")


                os.chdir(original_cwd)
                save_account_config(folder, config)


                if idx < len(selected_folders) and not STOP_FLAG:
                    delay = 5
                    print(f"Delay {delay} detik sebelum akun berikutnya...")
                    time.sleep(delay)

            except KeyboardInterrupt:
                os.chdir(original_cwd)
                STOP_FLAG = True
                break
            except Exception as e:
                print(f"\n{R}✗ Error pada {folder}: {e}{W}")
                import traceback
                traceback.print_exc()

            finally:
                os.chdir(original_cwd)


        grand_total_earned += cycle_earned

        print(f"\n{'='*60}")
        print(f"{C}[Ringkasan Cycle #{cycle}]{W}")
        print(f"{'='*60}")
        print(f"Akun dijalankan: {success_count}/{len(selected_folders)}")
        print(f"Pendapatan cycle ini: {G}+{cycle_earned:.2f}₽{W}")
        print(f"Total keseluruhan: {G}+{grand_total_earned:.2f}₽{W}")
        print(f"{'='*60}\n")


        if account_balances:
            print(f"{C}[Rekap Balance per Akun]{W}")
            print(f"{'='*70}")
            print(f"{Y}{'Akun':<15} {'IG Username':<20} {'Balance':>12} {'Naik':>12}{W}")
            print(f"{'-'*70}")
            for acc_name, acc_data in account_balances.items():
                ig_name = acc_data['ig_name'] if acc_data['ig_name'] != 'N/A' else '-'
                balance = acc_data['balance']
                earned = acc_data['earned']


                if earned > 0:
                    earned_display = f"{G}+{earned:.2f}₽{W}"
                elif earned < 0:
                    earned_display = f"{R}{earned:.2f}₽{W}"
                else:
                    earned_display = f"{Y}±0.00₽{W}"

                print(f"{acc_name:<15} {ig_name:<20} {balance:>10.2f}₽ {earned_display}")
            print(f"{'='*70}\n")


        if banned_accounts:
            print(f"{R}[⚠️  AKUN POTENTIALLY BANNED - Zero Tasks Detected]{W}")
            print(f"{'='*60}")
            print(f"{Y}{'Akun':<20} {'Email':<30} {'Balance':>8}{W}")
            print(f"{'-'*60}")
            for acc in banned_accounts:
                print(f"{R}{acc['name']:<20}{W} {acc['vks_email']:<30} {acc['balance']:>6.2f}₽")
            print(f"{'='*60}")
            print(f"{Y}⚠️  Total {len(banned_accounts)} akun terdeteksi banned/restricted{W}")
            print(f"{Y}📱 Alert sudah dikirim ke Telegram untuk setiap akun{W}")
            print(f"{Y}📋 Silakan cek manual dan update cookies jika perlu{W}\n")


        if rate_limited_accounts:
            print(f"{Y}[⏱  AKUN DENGAN RATE LIMIT - VK/Instagram]{W}")
            print(f"{'='*70}")
            print(f"{Y}{'Akun':<20} {'Limit Type':<30} {'Cooldown':>18}{W}")
            print(f"{'-'*70}")
            for acc in rate_limited_accounts:
                acc_name = acc['name']
                for limit_type, cooldown in acc['limits'].items():

                    if limit_type == 'vk_flood':
                        limit_display = 'VK Flood Control'
                    elif limit_type.startswith('ig_'):
                        action = limit_type.replace('ig_', '').title()
                        limit_display = f'Instagram {action}'
                    else:
                        limit_display = limit_type

                    print(f"{Y}{acc_name:<20}{W} {limit_display:<30} {cooldown:>18}")
                    acc_name = ""
            print(f"{'='*70}")
            print(f"{Y}⏱  Total {len(rate_limited_accounts)} akun kena rate limit{W}")
            print(f"{Y}⏰  Akun akan otomatis skip tasks yang di-limit sampai cooldown habis{W}")
            print(f"{Y}📊  Rate limit adalah normal dan akan reset otomatis{W}\n")

        if STOP_FLAG:
            break


        delay_minutes = random.randint(30, 60)
        delay_seconds = delay_minutes * 60

        print(f"{C}Semua akun selesai. Jeda {delay_minutes} menit sebelum cycle berikutnya...{W}")
        print(f"{Y}(Cycle baru akan dimulai pada: {time.strftime('%H:%M:%S', time.localtime(time.time() + delay_seconds))}){W}\n")


        for remaining_minutes in range(delay_minutes, 0, -1):
            if STOP_FLAG:
                break
            print(f"⏳ Sisa waktu: {remaining_minutes} menit...", end='\r')

            for _ in range(60):
                if STOP_FLAG:
                    break
                time.sleep(1)

        if not STOP_FLAG:
            print(f"\n{G}✓ Jeda selesai! Memulai cycle baru...{W}\n")
            time.sleep(2)


    print(f"\n{'='*50}")
    print(f"{C}[FINAL SUMMARY]{W}")
    print(f"{'='*50}")
    print(f"Total cycles: {cycle}")
    print(f"Total pendapatan: {G}+{grand_total_earned:.2f}₽{W}")
    print(f"{'='*50}\n")

    input("Enter untuk kembali...")

def fetch_all_balances():
    """Fetch balances - direct HTTP, parallel, parses email/IG/TG from /settings HTML"""
    import concurrent.futures
    import html as html_module

    def parse_settings_html(html_content):
        """Parse email, Instagram, and Telegram from /settings HTML"""
        email, ig_username, tg_username = None, None, None
        init_match = re.search(r':init-data="([^"]+)"', html_content)
        if init_match:
            try:
                init_str = html_module.unescape(init_match.group(1))
                init_data = json.loads(init_str)
                email = init_data.get('email')
            except:
                pass


        ig_opts = re.findall(r'<option[^>]*data-(?:platform|icon)="instagram"[^>]*>', html_content)
        if ig_opts:
            alias = re.search(r'data-alias="@?([^"]+)"', ig_opts[0])
            if alias:
                ig_username = alias.group(1)


        tg_match = re.search(r'data-platform=\\"telegram\\"[^>]*data-alias=\\"@([^"\\]+)\\"', html_content)
        if not tg_match:
            tg_match = re.search(r'data-platform="telegram"[^>]*data-alias="@([^"]+)"', html_content)
        if tg_match:
            tg_username = tg_match.group(1)

        return email, ig_username, tg_username

    def get_proxy_ip(proxy_str):
        """Extract IP from proxy string"""
        if not proxy_str:
            return '-'
        if '@' in proxy_str:
            return proxy_str.split('@')[1].split(':')[0]
        return proxy_str.split(':')[0].replace('http://', '')

    def fetch_one(acc):
        acc_dir = os.path.join(ACCOUNTS_DIR, acc)
        config_file = os.path.join(acc_dir, "config.json")
        if not os.path.isfile(config_file):
            return None
        try:
            with open(config_file) as f:
                config = json.load(f)
        except:
            return None

        creds = config.get('credentials', {})
        cookies = creds.get('cookies', {})
        xsrf = creds.get('xsrf_token', '')
        proxy_str = config.get('proxy', {}).get('proxy_string', '')
        proxy_ip = get_proxy_ip(proxy_str)
        proxy = parse_proxy_string(proxy_str)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Mobile Safari/537.36',
            'X-XSRF-Token': xsrf,
            'X-Requested-With': 'XMLHttpRequest',
            'X-Ajax-Html': '1',
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None

        balance, email, ig_user, tg_user = 0.0, '-', None, None
        for domain in ['https://vkserfing.com', 'https://vkserfing.ru']:
            try:
                resp = requests.get(f'{domain}/cashout', headers=headers, cookies=cookies, proxies=proxies, timeout=10)
                if resp.status_code == 200:
                    html_content = resp.json().get('html', '')
                    m = re.search(r'<span>([0-9.]+)</span>', html_content)
                    if m:
                        balance = float(m.group(1))

                resp2 = requests.get(f'{domain}/settings', headers=headers, cookies=cookies, proxies=proxies, timeout=10)
                if resp2.status_code == 200:
                    html_content = resp2.json().get('html', '')
                    email, ig_user, tg_user = parse_settings_html(html_content)
                    email = email or '-'
                break
            except:
                continue

        if not ig_user:
            ig_user = config.get('instagram', {}).get('username')
            if not ig_user:
                try:
                    for f in os.listdir(acc_dir):
                        if f.startswith('ig_session_') and f.endswith('.json'):
                            ig_user = f.replace('ig_session_', '').replace('.json', '')
                            break
                except:
                    pass

        return {'account': acc, 'balance': balance, 'ig_user': ig_user, 'tg_user': tg_user, 'email': email, 'proxy_ip': proxy_ip}

    folders = get_account_folders()
    results = []

    print(f"\nFetching {len(folders)} accounts (parallel)...\n")
    print(f"{'Account':<12} | {'Balance':>8} | {'Proxy IP':<15} | {'IG':<16} | {'TG':<16} | {'Email':<20}")
    print("-" * 105)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_one, acc): acc for acc in folders}
        for future in concurrent.futures.as_completed(futures):
            r = future.result()
            if not r:
                continue
            results.append(r)
            b = r['balance']
            color, mark = (G, '✓') if b >= 100 else (Y, '●') if b >= 50 else (W, ' ')
            ig_display = f"@{r['ig_user']}" if r['ig_user'] else '-'
            tg_display = f"@{r['tg_user']}" if r['tg_user'] else '-'
            print(f"[{mark}] {r['account']:<10} | {color}{b:>6.2f}₽{W} | {r['proxy_ip']:<15} | {C}{ig_display:<16}{W} | {C}{tg_display:<16}{W} | {r['email']:<20}")

    print("\n" + "=" * 105)
    print("SUMMARY (50+₽):")
    print("=" * 105)
    for r in sorted(results, key=lambda x: -x['balance']):
        if r['balance'] < 50:
            continue
        color = G if r['balance'] >= 100 else Y
        ig_display = f"@{r['ig_user']}" if r['ig_user'] else '-'
        tg_display = f"@{r['tg_user']}" if r['tg_user'] else '-'
        print(f"  {r['account']:<12} | {color}{r['balance']:>6.2f}₽{W} | {r['proxy_ip']:<15} | {C}{ig_display:<16}{W} | {C}{tg_display:<16}{W} | {r['email']}")

    with_ig = len([r for r in results if r['ig_user']])
    with_tg = len([r for r in results if r['tg_user']])
    print(f"\n{G}100+₽:{W} {len([r for r in results if r['balance'] >= 100])} accounts")
    print(f"{Y}50-99₽:{W} {len([r for r in results if 50 <= r['balance'] < 100])} accounts")
    print(f"{C}With IG:{W} {with_ig} | {C}With TG:{W} {with_tg} | {R}Without IG:{W} {len(results) - with_ig}")
    print(f"Total: {sum(r['balance'] for r in results):.2f}₽")
    input("\nEnter untuk kembali...")

def run_parallel_accounts():
    """Run accounts in parallel (10 at a time)"""
    global STOP_FLAG
    import concurrent.futures
    import threading

    folders = get_account_folders()
    if not folders:
        print(f"{R}Tidak ada akun!{W}")
        return

    BATCH_SIZE = 10
    print(f"\n{C}Parallel Mode: {BATCH_SIZE} akun sekaligus{W}")
    print(f"Total akun: {len(folders)}")
    print(f"Tekan Ctrl+C untuk stop\n")
    input("Enter untuk mulai...")

    lock = threading.Lock()

    def process_account(acc_name):
        if STOP_FLAG:
            return None
        try:
            config_file = os.path.join(ACCOUNTS_DIR, acc_name, "config.json")
            with open(config_file) as f:
                config = json.load(f)

            bot = VKSerfingBot(config, account_name=acc_name, quiet_mode=True)
            start_bal = bot.get_balance()
            bot.run()
            end_bal = bot.get_balance()
            earned = end_bal - start_bal

            with lock:
                print(f"  {G}✓{W} {acc_name}: {end_bal:.2f}₽ (+{earned:.2f}₽)")

            return {'account': acc_name, 'balance': end_bal, 'earned': earned}
        except Exception as e:
            with lock:
                print(f"  {R}✗{W} {acc_name}: {str(e)[:40]}")
            return {'account': acc_name, 'balance': 0, 'earned': 0, 'error': str(e)[:40]}

    cycle = 1
    total_all_cycles = 0

    while not STOP_FLAG:
        print(f"\n{'='*60}")
        print(f"[CYCLE #{cycle}] - {BATCH_SIZE} akun parallel")
        print(f"{'='*60}\n")

        cycle_results = []


        for i in range(0, len(folders), BATCH_SIZE):
            if STOP_FLAG:
                break

            batch = folders[i:i+BATCH_SIZE]
            print(f"\n{C}Batch {i//BATCH_SIZE + 1}/{(len(folders)-1)//BATCH_SIZE + 1}: {len(batch)} akun{W}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=BATCH_SIZE) as executor:
                futures = {executor.submit(process_account, acc): acc for acc in batch}
                for future in concurrent.futures.as_completed(futures):
                    if STOP_FLAG:
                        break
                    result = future.result()
                    if result:
                        cycle_results.append(result)


        cycle_earned = sum(r.get('earned', 0) for r in cycle_results)
        total_all_cycles += cycle_earned

        print(f"\n{'='*65}")
        print(f"[SUMMARY CYCLE #{cycle}]")
        print(f"{'='*65}")
        print(f"{'No':<4} | {'Account':<15} | {'Balance':>10} | {'Earned':>10}")
        print(f"{'-'*65}")


        sorted_results = sorted(cycle_results, key=lambda x: int(x['account'].split('_')[1]) if '_' in x['account'] else 0)

        for i, r in enumerate(sorted_results, 1):
            bal = r.get('balance', 0)
            earn = r.get('earned', 0)
            err = r.get('error', '')
            if err:
                print(f"{i:<4} | {r['account']:<15} | {R}ERROR{W}")
            else:

                if bal == 0:
                    bal_color = R
                elif bal >= 100:
                    bal_color = G
                elif bal >= 50:
                    bal_color = Y
                else:
                    bal_color = W

                earn_str = f"{G}+{earn:.2f}₽{W}" if earn > 0 else f"+{earn:.2f}₽"
                print(f"{i:<4} | {r['account']:<15} | {bal_color}{bal:>9.2f}₽{W} | {earn_str}")

        print(f"{'-'*65}")
        print(f"{'':4} | {'TOTAL':<15} | {sum(r.get('balance',0) for r in cycle_results):>9.2f}₽ | {G}+{cycle_earned:.2f}₽{W}")
        print(f"\n{Y}Total semua cycle: +{total_all_cycles:.2f}₽{W}")

        cycle += 1

        if STOP_FLAG:
            break


        wait_min = random.randint(30, 45)
        print(f"\nJeda {wait_min} menit...")
        for _ in range(wait_min * 60):
            if STOP_FLAG:
                break
            time.sleep(1)

def run_all_accounts():
    """Run all accounts sequentially in loop"""
    global STOP_FLAG


    used_ips = {}

    show_header()
    print(f"{C}[Menjalankan Semua Akun - Loop Mode]{W}\n")

    folders = get_account_folders()

    if not folders:
        print(f"{Y}Tidak ada akun untuk dijalankan.{W}")
        input("\nEnter untuk kembali...")
        return

    print(f"Total akun: {len(folders)}\n")
    print(f"{Y}Akun akan dijalankan satu per satu dalam loop.{W}")
    print(f"{Y}Setelah akun terakhir selesai, akan mulai lagi dari akun pertama.{W}")
    print(f"{Y}Tekan Ctrl+C untuk menghentikan.{W}\n")

    input("Enter untuk mulai...")

    cycle = 0
    grand_total_earned = 0.0


    STOP_FLAG = False


    while not STOP_FLAG:

        folders = get_account_folders()


        try:
            new_account = check_telegram_updates()
            if new_account:
                print(f"\n{G}[Telegram] Akun ditambahkan/diupdate: {new_account}{W}")

                folders = get_account_folders()
        except Exception as e:

            pass

        if not folders:
            print(f"\n{Y}Tidak ada akun. Menunggu 30 detik...{W}")
            time.sleep(30)
            continue

        cycle += 1

        print(f"\n{'='*50}")
        print(f"{C}[CYCLE #{cycle}]{W}")
        print(f"{'='*50}\n")

        cycle_earned = 0.0
        success_count = 0
        account_balances = {}
        banned_accounts = []
        rate_limited_accounts = []
        used_ips = {}

        for idx, folder in enumerate(folders, 1):
            if STOP_FLAG:
                print(f"\n{Y}⏸ Dihentikan oleh user{W}")
                break

            print(f"\n{'='*50}")
            print(f"{C}[{idx}/{len(folders)}] {folder}{W}")
            print(f"{'='*50}\n")


            config = load_account_config(folder)
            if not config:
                print(f"{R}✗ Gagal load config{W}")
                continue


            account_path = os.path.join(ACCOUNTS_DIR, folder)
            original_cwd = os.getcwd()


            account_success = 0
            account_error = 0

            try:
                os.chdir(account_path)


                bot = VKSerfingBot(config, account_name=folder)


                current_ip = None
                is_account_1 = (folder == 'account_1')

                if bot.proxy_info:
                    current_ip = bot.proxy_info.get('ip')
                else:

                    from automation_core import get_ip_location
                    direct_info = get_ip_location(timeout=5)
                    if direct_info:
                        current_ip = direct_info.get('ip')


                if current_ip and current_ip in used_ips and not (account_name == 'account_1' and not bot.proxy_info):
                    other_account = used_ips[current_ip]
                    print(f"{R}⚠️  IP COLLISION DETECTED!{W}")
                    print(f"{R}   IP {current_ip} sudah digunakan oleh {other_account}{W}")
                    print(f"{Y}   Fetching new proxy untuk {folder}...{W}\n")


                    if hasattr(bot, 'proxy_manager') and bot.proxy_manager:

                        exclude_ips = set(used_ips.keys())

                        print(f"{C}[Auto-Fetch] Mencari proxy baru (exclude {len(exclude_ips)} IPs)...{W}")


                        exclude_proxies = set()
                        for existing_folder in folders[:idx]:
                            existing_config = load_account_config(existing_folder)
                            if existing_config and existing_config.get('proxy'):
                                proxy_str = existing_config['proxy'].get('proxy_string')
                                if proxy_str:
                                    exclude_proxies.add(proxy_str)


                        success, new_proxy_dict, new_ip_info = bot.proxy_manager.auto_discover_proxy(
                            exclude_proxies=exclude_proxies,
                            protocol='http'
                        )

                        if success and new_proxy_dict and new_ip_info:

                            bot.proxy_dict = new_proxy_dict
                            bot.proxy_info = new_ip_info
                            current_ip = new_ip_info.get('ip')


                            config['proxy'] = {
                                'proxy_string': new_proxy_dict['raw'],
                                'ip': new_ip_info['ip'],
                                'country': new_ip_info.get('country', 'Unknown'),
                                'country_code': new_ip_info.get('country_code', ''),
                                'city': new_ip_info.get('city', 'Unknown'),
                                'region': new_ip_info.get('region', ''),
                                'isp': new_ip_info.get('isp', ''),
                                'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                            }

                            print(f"{G}✓ New proxy bound: {new_ip_info['ip']} ({new_ip_info['country']}){W}\n")
                        else:
                            print(f"{R}✗ Failed to get new proxy, skipping {folder}{W}\n")
                            os.chdir(original_cwd)
                            continue
                    else:
                        print(f"{R}✗ No proxy manager available, skipping {folder}{W}\n")
                        os.chdir(original_cwd)
                        continue


                if current_ip:
                    used_ips[current_ip] = folder
                    if is_account_1:
                        print(f"{Y}[IP TRACKING] {current_ip} → {folder} (Direct Connection){W}")
                    else:
                        print(f"{C}[IP TRACKING] {current_ip} → {folder}{W}")


                if bot.proxy_info:
                    from automation_core import format_ip_location
                    ip_display = format_ip_location(bot.proxy_info, detailed=True)
                    proxy_status = f"{C}[PROXY]{W}"
                else:

                    from automation_core import get_ip_location, format_ip_location
                    direct_info = get_ip_location(timeout=10)
                    if direct_info:
                        ip_display = format_ip_location(direct_info, detailed=True)
                    else:
                        ip_display = f"🌍 Unknown"
                    proxy_status = f"{Y}[DIRECT]{W}"

                print(f"{proxy_status} {ip_display}")


                if hasattr(bot, 'user_agent_data') and bot.user_agent_data:
                    from automation_core import UserAgentGenerator
                    device_info = UserAgentGenerator.get_device_info(bot.user_agent_data)
                    print(f"{C}[DEVICE]{W} {device_info}")

                print()


                try:

                    original_run = bot.run
                    def run_with_stop_check():
                        if STOP_FLAG:
                            return
                        return original_run()
                    bot.run = run_with_stop_check
                    bot.run()


                    if hasattr(bot, 'is_banned') and bot.is_banned:
                        banned_accounts.append({
                            'name': folder,
                            'balance': bot.balance,
                            'vks_email': getattr(bot, 'server_email', 'N/A')
                        })


                    rate_limit_info = {}


                    if hasattr(bot, 'vk_flood_control_until'):
                        if time.time() < bot.vk_flood_control_until:
                            remaining = int(bot.vk_flood_control_until - time.time())
                            rate_limit_info['vk_flood'] = f"{remaining}s"


                    if hasattr(bot, 'ig') and bot.ig and hasattr(bot.ig, 'rate_limited_actions'):
                        for action, until_time in bot.ig.rate_limited_actions.items():
                            if time.time() < until_time:
                                remaining_min = int((until_time - time.time()) / 60)
                                rate_limit_info[f'ig_{action}'] = f"{remaining_min}m"


                    if rate_limit_info:
                        rate_limited_accounts.append({
                            'name': folder,
                            'limits': rate_limit_info
                        })
                except KeyboardInterrupt:
                    raise
                except Exception as run_error:
                    print(f"{R}✗ Error saat run: {run_error}{W}")
                    account_error += 1

                if STOP_FLAG:
                    os.chdir(original_cwd)
                    break


                balance_after = bot.balance
                earned = bot.earned
                cycle_earned += earned


                if hasattr(bot, 'completed_tasks'):
                    account_success = bot.completed_tasks
                if hasattr(bot, 'failed_tasks'):
                    account_error = bot.failed_tasks

                success_count += 1


                ig_username = config.get('instagram', {}).get('username', 'N/A')
                account_balances[folder] = {
                    'ig_name': ig_username,
                    'balance': balance_after,
                    'earned': earned
                }


                if earned > 0:
                    print(f"\n{G}✓ {folder} selesai (+{earned:.2f}₽){W}\n")
                elif earned < 0:
                    print(f"\n{Y}✓ {folder} selesai ({earned:.2f}₽){W}\n")
                else:
                    print(f"\n{Y}✓ {folder} selesai (±0.00₽){W}\n")


                info = get_account_info(config, folder)
                vk_id = info.get('vk', '').replace('id', '') if info.get('vk') else None
                ig_user = info.get('ig', '').replace('@', '') if info.get('ig') else None
                tg_user = info.get('tg', '').replace('@', '') if info.get('tg') else None


                if cycle % 10 == 0:
                    print(f"{C}Mengirim laporan ke Telegram (cycle #{cycle})...{W}")
                    if send_telegram_report(folder, vk_id, ig_user, tg_user, balance_after, account_success, account_error):
                        print(f"{G}✓ Laporan terkirim{W}\n")
                    else:
                        print(f"{Y}⚠ Laporan gagal dikirim{W}\n")
                else:
                    print(f"{Y}ℹ Report disimpan (akan dikirim di cycle #{((cycle // 10) + 1) * 10}){W}\n")


                os.chdir(original_cwd)
                save_account_config(folder, config)


                if idx < len(folders) and not STOP_FLAG:
                    delay = 5
                    print(f"Delay {delay} detik sebelum akun berikutnya...")
                    time.sleep(delay)

            except KeyboardInterrupt:
                os.chdir(original_cwd)
                STOP_FLAG = True
                break
            except Exception as e:
                print(f"\n{R}✗ Error pada {folder}: {e}{W}")
                import traceback
                traceback.print_exc()

            finally:
                os.chdir(original_cwd)


        grand_total_earned += cycle_earned

        print(f"\n{'='*60}")
        print(f"{C}[Ringkasan Cycle #{cycle}]{W}")
        print(f"{'='*60}")
        print(f"Akun dijalankan: {success_count}/{len(folders)}")
        print(f"Pendapatan cycle ini: {G}+{cycle_earned:.2f}₽{W}")
        print(f"Total keseluruhan: {G}+{grand_total_earned:.2f}₽{W}")
        print(f"{'='*60}\n")


        if account_balances:
            print(f"{C}[Rekap Balance per Akun]{W}")
            print(f"{'='*70}")
            print(f"{Y}{'Akun':<15} {'IG Username':<20} {'Balance':>12} {'Naik':>12}{W}")
            print(f"{'-'*70}")
            for acc_name, acc_data in account_balances.items():
                ig_name = acc_data['ig_name'] if acc_data['ig_name'] != 'N/A' else '-'
                balance = acc_data['balance']
                earned = acc_data['earned']


                if earned > 0:
                    earned_display = f"{G}+{earned:.2f}₽{W}"
                elif earned < 0:
                    earned_display = f"{R}{earned:.2f}₽{W}"
                else:
                    earned_display = f"{Y}±0.00₽{W}"

                print(f"{acc_name:<15} {ig_name:<20} {balance:>10.2f}₽ {earned_display}")
            print(f"{'='*70}\n")


        if banned_accounts:
            print(f"{R}[⚠️  AKUN POTENTIALLY BANNED - Zero Tasks Detected]{W}")
            print(f"{'='*60}")
            print(f"{Y}{'Akun':<20} {'Email':<30} {'Balance':>8}{W}")
            print(f"{'-'*60}")
            for acc in banned_accounts:
                print(f"{R}{acc['name']:<20}{W} {acc['vks_email']:<30} {acc['balance']:>6.2f}₽")
            print(f"{'='*60}")
            print(f"{Y}⚠️  Total {len(banned_accounts)} akun terdeteksi banned/restricted{W}")
            print(f"{Y}📱 Alert sudah dikirim ke Telegram untuk setiap akun{W}")
            print(f"{Y}📋 Silakan cek manual dan update cookies jika perlu{W}\n")


        if rate_limited_accounts:
            print(f"{Y}[⏱  AKUN DENGAN RATE LIMIT - VK/Instagram]{W}")
            print(f"{'='*70}")
            print(f"{Y}{'Akun':<20} {'Limit Type':<30} {'Cooldown':>18}{W}")
            print(f"{'-'*70}")
            for acc in rate_limited_accounts:
                acc_name = acc['name']
                for limit_type, cooldown in acc['limits'].items():

                    if limit_type == 'vk_flood':
                        limit_display = 'VK Flood Control'
                    elif limit_type.startswith('ig_'):
                        action = limit_type.replace('ig_', '').title()
                        limit_display = f'Instagram {action}'
                    else:
                        limit_display = limit_type

                    print(f"{Y}{acc_name:<20}{W} {limit_display:<30} {cooldown:>18}")
                    acc_name = ""
            print(f"{'='*70}")
            print(f"{Y}⏱  Total {len(rate_limited_accounts)} akun kena rate limit{W}")
            print(f"{Y}⏰  Akun akan otomatis skip tasks yang di-limit sampai cooldown habis{W}")
            print(f"{Y}📊  Rate limit adalah normal dan akan reset otomatis{W}\n")

        if STOP_FLAG:
            break


        delay_minutes = random.randint(30, 60)
        delay_seconds = delay_minutes * 60

        print(f"{C}Semua akun selesai. Jeda {delay_minutes} menit sebelum cycle berikutnya...{W}")
        print(f"{Y}(Cycle baru akan dimulai pada: {time.strftime('%H:%M:%S', time.localtime(time.time() + delay_seconds))}){W}\n")


        for remaining_minutes in range(delay_minutes, 0, -1):
            if STOP_FLAG:
                break
            print(f"⏳ Sisa waktu: {remaining_minutes} menit...", end='\r')
            time.sleep(60)

        if not STOP_FLAG:
            print(f"\n{G}✓ Jeda selesai! Memulai cycle baru...{W}\n")
            time.sleep(2)


    print(f"\n{'='*50}")
    print(f"{C}[FINAL SUMMARY]{W}")
    print(f"{'='*50}")
    print(f"Total cycles: {cycle}")
    print(f"Total pendapatan: {G}+{grand_total_earned:.2f}₽{W}")
    print(f"{'='*50}\n")

    input("Enter untuk kembali...")

def create_new_account():
    """Create a new account"""
    show_header()
    print(f"{C}[Buat Akun Baru]{W}\n")


    folders = get_account_folders()
    if folders:
        last_num = max([int(f.split('_')[1]) for f in folders if '_' in f])
        next_num = last_num + 1
    else:
        next_num = 1

    folder_name = f"account_{next_num}"
    folder_path = os.path.join(ACCOUNTS_DIR, folder_name)

    print(f"Folder: {G}{folder_name}{W}\n")


    os.makedirs(folder_path, exist_ok=True)


    config = {
        "credentials": {
            "cookies": {},
            "xsrf_token": ""
        },
        "settings": {
            "wait_time_min": 11,
            "wait_time_max": 21,
            "delay_between_tasks": 5,
            "auto_mode": True
        },
        "task_types": {
            "vk_friends": True,
            "vk_groups": True,
            "vk_likes": True,
            "vk_reposts": True,
            "vk_polls": True,
            "vk_videos": True,
            "vk_views": True,
            "telegram_followers": False,
            "telegram_views": False,
            "instagram_followers": True,
            "instagram_likes": True,
            "instagram_comments": True,
            "instagram_videos": True
        },
        "vk_api": {
            "enabled": False,
            "access_token": "",
            "user_id": ""
        },
        "instagram": {
            "enabled": False,
            "username": "",
            "password": ""
        }
    }

    print(f"{Y}Setup akun baru:{W}\n")


    print("1. Cookie VKSerfing")
    print("   Paste HTTP request dari browser DevTools:")
    print("   (Network tab > klik request > Copy request headers)")
    print("   Ketik 'END' dan Enter setelah selesai paste.\n")

    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == 'END':
                break
            lines.append(line)
    except:
        pass

    text = '\n'.join(lines)

    if text:
        cookies = {}
        xsrf = ""

        for line in text.split('\n'):
            line = line.strip()

            if line.lower().startswith('x-xsrf-token:'):
                xsrf = line.split(':', 1)[1].strip()




            if line.lower().startswith('cookie:'):
                cookie_part = line.split(':', 1)[1].strip()

                for pair in cookie_part.split(';'):
                    if '=' in pair:
                        parts = pair.strip().split('=', 1)
                        if len(parts) == 2:
                            cookies[parts[0].strip()] = parts[1].strip()

        if cookies.get('vkstoken'):
            config['credentials']['cookies'] = cookies
            config['credentials']['xsrf_token'] = xsrf
            print(f"\n   {G}✓ Cookie tersimpan!{W}")
            print(f"   vkstoken: ...{cookies['vkstoken'][-15:]}")
            print(f"   sessid: {cookies.get('sessid', 'N/A')}")
            print(f"   vksid: ...{cookies.get('vksid', 'N/A')[-15:]}")
        else:
            print(f"\n   {R}✗ vkstoken tidak ditemukan! Akun tidak akan berfungsi.{W}")
    else:
        print(f"\n   {Y}Cookie tidak disetup. Akun tidak akan berfungsi.{W}")


    print(f"\n2. VK API (optional)")
    print("   Paste URL OAuth VK (access_token=...&user_id=...)")
    vk_url = input("   URL (enter untuk skip): ").strip()
    if vk_url:
        import re
        token_match = re.search(r'access_token=([^&\s]+)', vk_url)
        user_id_match = re.search(r'user_id=(\d+)', vk_url)
        if token_match and user_id_match:
            config['vk_api']['enabled'] = True
            config['vk_api']['access_token'] = token_match.group(1)
            config['vk_api']['user_id'] = user_id_match.group(1)
            print(f"   {G}✓ VK API tersimpan{W}")
        else:
            print(f"   {R}✗ Format URL tidak valid{W}")


    print(f"\n3. Instagram (optional)")
    ig_user = input("   Username (enter untuk skip): ").strip()
    if ig_user:
        ig_pass = input("   Password: ")
        if ig_pass:
            config['instagram']['enabled'] = True
            config['instagram']['username'] = ig_user
            config['instagram']['password'] = ig_pass
            print(f"   {G}✓ Instagram tersimpan{W}")


    if next_num > 1:
        print(f"\n4. Proxy (optional)")
        print("   Format: host:port:username:password")
        print(f"   Contoh: 142.111.48.253:7030:axfgqegu:ijqvkb0vxazy")
        proxy_input = input("   Proxy (enter untuk skip): ").strip()

        if proxy_input:

            from automation_core import parse_proxy, get_ip_location, format_ip_location


            proxy_config = parse_proxy(proxy_input)
            if proxy_config:
                print(f"   {C}Mengecek proxy location...{W}", end=" ", flush=True)
                proxy_info = get_ip_location(proxy_dict=proxy_config, timeout=15)

                if proxy_info:
                    print(f"{G}✓{W}")

                    location_display = format_ip_location(proxy_info, detailed=True)
                    print(f"   {location_display}")


                    config['proxy'] = {
                        'proxy_string': proxy_input,
                        'ip': proxy_info['ip'],
                        'country': proxy_info.get('country', 'Unknown'),
                        'country_code': proxy_info.get('country_code', ''),
                        'city': proxy_info.get('city', 'Unknown'),
                        'region': proxy_info.get('region', ''),
                        'isp': proxy_info.get('isp', ''),
                        'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    print(f"   {G}✓ Proxy tersimpan dan terverifikasi{W}")
                else:
                    print(f"{R}✗ Gagal verifikasi proxy{W}")
                    print(f"   {Y}Proxy tidak disimpan (mungkin proxy mati atau timeout){W}")
            else:
                print(f"   {R}✗ Format proxy tidak valid{W}")
    else:
        print(f"\n4. Proxy")
        print(f"   {Y}⚠ Account 1 tidak menggunakan proxy (direct connection){W}")


    from automation_core import UserAgentGenerator
    print(f"\n5. User Agent")
    print(f"   {C}Generating realistic user agent...{W}", end=" ", flush=True)
    ua_data = UserAgentGenerator.generate()
    config['user_agent'] = ua_data
    print(f"{G}✓{W}")
    print(f"   Device  : {ua_data['device']}")
    print(f"   Android : {ua_data['android_version']}")
    print(f"   Chrome  : {ua_data['chrome_version']}")


    save_account_config(folder_name, config)

    print(f"\n{G}✓ Akun {folder_name} berhasil dibuat!{W}")

    input("\nEnter untuk kembali...")

def edit_account():
    """Edit existing account"""
    show_header()
    print(f"{C}[Edit Akun]{W}\n")

    folders = show_accounts_list()

    if not folders:
        input("Enter untuk kembali...")
        return

    print(f"Pilih akun untuk diedit (1-{len(folders)}, 0=batal):")
    choice = input("Nomor: ").strip()

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(folders):
        print(f"{Y}Dibatalkan{W}")
        time.sleep(1)
        return

    folder_name = folders[int(choice) - 1]
    config = load_account_config(folder_name)

    if not config:
        print(f"{R}Gagal load config{W}")
        input("\nEnter untuk kembali...")
        return

    while True:
        show_header()
        print(f"{C}[Edit: {folder_name}]{W}\n")


        print("Status saat ini:")
        info = get_account_info(config, folder_name)

        vk_status = f"{G}✓ {info.get('vk', '')}{W}" if info.get('vk') else f"{R}✗ Tidak aktif{W}"
        ig_status = f"{G}✓ {info.get('ig', '')}{W}" if info.get('ig') else f"{R}✗ Tidak aktif{W}"
        tg_status = f"{G}✓ {info.get('tg', '')}{W}" if info.get('tg') else f"{R}✗ Tidak aktif{W}"

        print(f"  VK API    : {vk_status}")
        print(f"  Instagram : {ig_status}")
        print(f"  Telegram  : {tg_status}")

        cookie = config.get('credentials', {}).get('cookies', {}).get('vkstoken')
        cookie_status = f"{G}✓ Set{W}" if cookie else f"{R}✗ Belum set{W}"
        print(f"  Cookie    : {cookie_status}")


        proxy_data = config.get('proxy', {})
        if proxy_data.get('proxy_string'):
            from automation_core import get_country_flag
            flag = get_country_flag(proxy_data.get('country_code') or proxy_data.get('country'))
            proxy_ip = proxy_data.get('ip', 'Unknown')
            proxy_country = proxy_data.get('country', 'Unknown')
            proxy_city = proxy_data.get('city', '')

            if proxy_city and proxy_city != 'Unknown':
                print(f"  Proxy     : {G}✓ {flag} {proxy_ip} ({proxy_city}, {proxy_country}){W}")
            else:
                print(f"  Proxy     : {G}✓ {flag} {proxy_ip} ({proxy_country}){W}")
        else:
            print(f"  Proxy     : {Y}🌍 No Proxy (Direct){W}")


        ua_data = config.get('user_agent', {})
        if ua_data.get('device'):
            from automation_core import UserAgentGenerator
            ua_info = UserAgentGenerator.get_device_info(ua_data)
            print(f"  Device    : {C}{ua_info}{W}")

        print(f"\nMenu:")
        print(f"  1. Setup Cookie VKSerfing")
        print(f"  2. Setup VK API")
        print(f"  3. Setup Instagram")
        print(f"  4. Setup Telegram Session")
        print(f"  5. Setup Proxy")
        print(f"  6. Regenerate User Agent")
        print(f"  7. Regenerate Device Fingerprint (Instagram)")
        print(f"  8. Lihat Task Types")
        print(f"  0. Kembali")

        ch = input("\nPilih: ").strip()

        if ch == '0':
            break
        elif ch == '1':
            setup_cookie(folder_name, config)
        elif ch == '2':
            setup_vk_api(folder_name, config)
        elif ch == '3':
            setup_instagram(folder_name, config)
        elif ch == '4':
            setup_telegram_session(folder_name, config)
        elif ch == '5':
            setup_proxy(folder_name, config)
        elif ch == '6':
            regenerate_user_agent(folder_name, config)
        elif ch == '7':
            regenerate_device_fingerprint(folder_name, config)
        elif ch == '8':
            show_task_types(config)


        save_account_config(folder_name, config)

def setup_cookie(folder_name, config):
    """Setup VKSerfing cookie"""
    show_header()
    print(f"{C}[Setup Cookie - {folder_name}]{W}\n")

    print("Paste HTTP request dari browser DevTools:")
    print("(Network tab > klik request > Copy request headers)")
    print("Ketik 'END' dan Enter setelah selesai paste.\n")

    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == 'END':
                break
            lines.append(line)
    except:
        pass

    text = '\n'.join(lines)

    if text:
        cookies = {}
        xsrf = ""

        for line in text.split('\n'):
            line = line.strip()

            if line.lower().startswith('x-xsrf-token:'):
                xsrf = line.split(':', 1)[1].strip()




            if line.lower().startswith('cookie:'):
                cookie_part = line.split(':', 1)[1].strip()

                for pair in cookie_part.split(';'):
                    if '=' in pair:
                        parts = pair.strip().split('=', 1)
                        if len(parts) == 2:
                            cookies[parts[0].strip()] = parts[1].strip()

        if cookies.get('vkstoken'):
            if 'credentials' not in config:
                config['credentials'] = {}
            config['credentials']['cookies'] = cookies
            config['credentials']['xsrf_token'] = xsrf

            save_account_config(folder_name, config)

            print(f"\n{G}✓ Cookie tersimpan!{W}")
            print(f"  vkstoken: ...{cookies.get('vkstoken','')[-15:]}")
            print(f"  sessid: {cookies.get('sessid', 'N/A')}")
            print(f"  vksid: ...{cookies.get('vksid', 'N/A')[-15:]}")
        else:
            print(f"\n{R}✗ vkstoken tidak ditemukan!{W}")
    else:
        print(f"\n{Y}Dibatalkan{W}")

    input("\nEnter untuk kembali...")

def setup_vk_api(folder_name, config):
    """Setup VK API"""
    show_header()
    print(f"{C}[Setup VK API - {folder_name}]{W}\n")

    current = config.get('vk_api', {})
    if current.get('access_token'):
        print(f"Token saat ini: ...{current['access_token'][-20:]}")
        print(f"User ID: {current.get('user_id', '?')}\n")

    print("Paste URL OAuth VK:")
    print("(https://oauth.vk.com/blank.html#access_token=...&user_id=...)")
    url = input("\nURL (enter untuk disable): ").strip()

    if url:
        import re
        token_match = re.search(r'access_token=([^&\s]+)', url)
        user_id_match = re.search(r'user_id=(\d+)', url)

        if token_match and user_id_match:
            config['vk_api'] = {
                'enabled': True,
                'access_token': token_match.group(1),
                'user_id': user_id_match.group(1)
            }
            save_account_config(folder_name, config)
            print(f"\n{G}✓ VK API tersimpan!{W}")
        else:
            print(f"\n{R}✗ Format URL tidak valid{W}")
    else:
        config['vk_api']['enabled'] = False
        save_account_config(folder_name, config)
        print(f"\n{Y}VK API disabled{W}")

    input("\nEnter untuk kembali...")

def setup_telegram_session(folder_name, config):
    """Setup Telegram Session"""
    show_header()
    print(f"{C}[Setup Telegram Session - {folder_name}]{W}\n")


    DEFAULT_API_ID = "1724399"
    DEFAULT_API_HASH = "7f6c4af5220db320413ff672093ee102"

    current = config.get('telegram', {})
    if current.get('phone'):
        print(f"Phone saat ini: {current['phone']}")
    if current.get('session_string'):
        print(f"Session: {G}✓ Active{W}\n")
    else:
        print(f"Session: {R}✗ Not set{W}\n")

    print("Pilih metode:")
    print("  1. Login dengan Phone Number (OTP)")
    print("  2. Import Session String")
    print("  3. Import Session File (.session)")
    print("  0. Batal")

    ch = input("\nPilih: ").strip()

    if ch == '0':
        return

    elif ch == '1':

        print(f"\n{C}Menggunakan API credentials default{W}")
        print(f"  API ID: {DEFAULT_API_ID}")
        print(f"  API Hash: {DEFAULT_API_HASH[:20]}...\n")

        phone = input("Phone Number (+62xxx): ").strip()

        if not phone:
            print(f"{R}Phone number kosong!{W}")
            time.sleep(1)
            return

        try:
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession

            print(f"\n{C}Connecting to Telegram...{W}")

            session_path = os.path.join(ACCOUNTS_DIR, folder_name, 'telegram_session')

            with TelegramClient(session_path, int(DEFAULT_API_ID), DEFAULT_API_HASH) as client:
                if not client.is_user_authorized():
                    client.send_code_request(phone)
                    code = input(f"\n{Y}Masukkan OTP dari Telegram: {W}").strip()

                    try:
                        client.sign_in(phone, code)
                    except Exception as e:
                        if 'Two-steps verification' in str(e) or '2FA' in str(e) or 'password' in str(e).lower():
                            password = input(f"{Y}Masukkan 2FA Password: {W}").strip()
                            client.sign_in(password=password)
                        else:
                            raise e


                session_string = StringSession.save(client.session)


                me = client.get_me()


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

                print(f"\n{G}✓ Login berhasil!{W}")
                print(f"  User: {me.first_name} (@{me.username})")
                print(f"  ID: {me.id}")
                print(f"  {C}Telegram tasks auto-enabled{W}")

        except ImportError:
            print(f"{R}✗ Module telethon not found!{W}")
            print(f"{Y}Install dengan: pip install telethon{W}")
        except Exception as e:
            print(f"{R}✗ Error: {e}{W}")

        input("\nEnter untuk lanjut...")

    elif ch == '2':

        print(f"\n{C}Paste Session String:{W}")
        session_string = input().strip()

        if not session_string:
            print(f"{R}Session string kosong!{W}")
            time.sleep(1)
            return

        try:
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession

            print(f"\n{C}Validating session...{W}")

            with TelegramClient(StringSession(session_string), int(DEFAULT_API_ID), DEFAULT_API_HASH) as client:
                me = client.get_me()

                config['telegram'] = {
                    'api_id': DEFAULT_API_ID,
                    'api_hash': DEFAULT_API_HASH,
                    'session_string': session_string,
                    'user_id': me.id,
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'phone': me.phone or ''
                }


                if 'task_types' not in config:
                    config['task_types'] = {}
                config['task_types']['telegram_followers'] = True
                config['task_types']['telegram_views'] = True

                print(f"\n{G}✓ Session valid!{W}")
                print(f"  User: {me.first_name} (@{me.username})")
                print(f"  {C}Telegram tasks auto-enabled{W}")

        except ImportError:
            print(f"{R}✗ Module telethon not found!{W}")
            print(f"{Y}Install dengan: pip install telethon{W}")
        except Exception as e:
            print(f"{R}✗ Session invalid: {e}{W}")

        input("\nEnter untuk lanjut...")

    elif ch == '3':

        print(f"\n{C}Path ke file .session:{W}")
        session_file = input().strip()

        if not os.path.exists(session_file):
            print(f"{R}File tidak ditemukan!{W}")
            time.sleep(1)
            return

        try:
            import shutil
            from telethon.sync import TelegramClient
            from telethon.sessions import StringSession


            dest_session = os.path.join(ACCOUNTS_DIR, folder_name, 'telegram_session.session')
            shutil.copy(session_file, dest_session)

            session_name = dest_session.replace('.session', '')

            print(f"\n{C}Validating session...{W}")

            with TelegramClient(session_name, int(DEFAULT_API_ID), DEFAULT_API_HASH) as client:
                me = client.get_me()


                session_string = StringSession.save(client.session)

                config['telegram'] = {
                    'api_id': DEFAULT_API_ID,
                    'api_hash': DEFAULT_API_HASH,
                    'session_string': session_string,
                    'session_file': dest_session,
                    'user_id': me.id,
                    'username': me.username or '',
                    'first_name': me.first_name or '',
                    'phone': me.phone or ''
                }


                if 'task_types' not in config:
                    config['task_types'] = {}
                config['task_types']['telegram_followers'] = True
                config['task_types']['telegram_views'] = True

                print(f"\n{G}✓ Session imported!{W}")
                print(f"  User: {me.first_name} (@{me.username})")
                print(f"  {C}Telegram tasks auto-enabled{W}")

        except ImportError:
            print(f"{R}✗ Module telethon not found!{W}")
            print(f"{Y}Install dengan: pip install telethon{W}")
        except Exception as e:
            print(f"{R}✗ Error: {e}{W}")

        input("\nEnter untuk lanjut...")

def setup_instagram(folder_name, config):
    """Setup Instagram"""
    show_header()
    print(f"{C}[Setup Instagram - {folder_name}]{W}\n")

    current = config.get('instagram', {})
    if current.get('username'):
        print(f"Username saat ini: @{current['username']}\n")

    username = input("Username/Email (enter untuk disable): ").strip()

    if username:
        password = input("Password: ")

        if password:

            is_email = '@' in username
            input_type = "email" if is_email else "username"


            test = input(f"\n{Y}Test login & create session? (y/n):{W} ").strip().lower()

            if test == 'y':
                print(f"\n{C}Testing Instagram login...{W}")
                try:

                    try:
                        from instagrapi import Client
                    except ImportError:
                        print(f"{R}✗ Module instagrapi not found!{W}")
                        print(f"{Y}Install dengan: pip install instagrapi{W}")
                        test = 'n'

                    if test == 'y':

                        device_gen = DeviceFingerprintGenerator(config)


                        fingerprint = device_gen.generate()


                        config['device_fingerprint'] = fingerprint


                        is_existing = config.get('device_fingerprint') == fingerprint
                        status = f"{G}(existing){W}" if is_existing else f"{Y}(new){W}"
                        print(f"{C}[Device] {status} {device_gen.get_display_info()}{W}")


                        cl = Client()
                        cl.delay_range = [2, 5]


                        cl.set_device({
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
                        cl.set_user_agent(fingerprint['user_agent'])

                        login_success = False
                        session_file = None
                        successful_credential = username
                        alternative_credential = None
                        current_fingerprint = fingerprint


                        print(f"{C}[1/2] Trying login with {input_type}: {username}{W}")
                        try:
                            cl.login(username, password)
                            login_success = True
                            print(f"{G}✓ Login berhasil dengan {input_type}!{W}")
                        except Exception as e:
                            error_msg = str(e)
                            print(f"{R}✗ Login gagal: {error_msg[:120]}{W}")


                            if is_email:
                                print(f"\n{Y}Login via email gagal. Coba dengan username?{W}")
                                alt_username = input(f"Username Instagram (atau enter untuk skip): ").strip()
                                if alt_username:
                                    print(f"\n{C}[2/2] Trying login with username: {alt_username}{W}")
                                    try:

                                        alt_fingerprint = device_gen.rotate()
                                        print(f"{C}[Device] {device_gen.get_display_info()}{W}")

                                        cl2 = Client()
                                        cl2.delay_range = [2, 5]


                                        cl2.set_device({
                                            'app_version': alt_fingerprint['app_version'],
                                            'android_version': alt_fingerprint['android_version'],
                                            'android_release': alt_fingerprint['android_release'],
                                            'dpi': alt_fingerprint['dpi'],
                                            'resolution': alt_fingerprint['resolution'],
                                            'manufacturer': alt_fingerprint['manufacturer'],
                                            'device': alt_fingerprint['device'],
                                            'model': alt_fingerprint['model'],
                                            'cpu': alt_fingerprint['cpu'],
                                            'version_code': alt_fingerprint['version_code']
                                        })
                                        cl2.set_user_agent(alt_fingerprint['user_agent'])

                                        cl2.login(alt_username, password)
                                        cl = cl2
                                        login_success = True
                                        successful_credential = alt_username
                                        alternative_credential = username
                                        current_fingerprint = alt_fingerprint
                                        print(f"{G}✓ Login berhasil dengan username!{W}")
                                    except Exception as e2:
                                        print(f"{R}✗ Login dengan username juga gagal: {str(e2)[:120]}{W}")
                            else:
                                print(f"\n{Y}Login via username gagal. Coba dengan email?{W}")
                                alt_email = input(f"Email Instagram (atau enter untuk skip): ").strip()
                                if alt_email:
                                    print(f"\n{C}[2/2] Trying login with email: {alt_email}{W}")
                                    try:

                                        alt_fingerprint = device_gen.rotate()
                                        print(f"{C}[Device] {device_gen.get_display_info()}{W}")

                                        cl2 = Client()
                                        cl2.delay_range = [2, 5]


                                        cl2.set_device({
                                            'app_version': alt_fingerprint['app_version'],
                                            'android_version': alt_fingerprint['android_version'],
                                            'android_release': alt_fingerprint['android_release'],
                                            'dpi': alt_fingerprint['dpi'],
                                            'resolution': alt_fingerprint['resolution'],
                                            'manufacturer': alt_fingerprint['manufacturer'],
                                            'device': alt_fingerprint['device'],
                                            'model': alt_fingerprint['model'],
                                            'cpu': alt_fingerprint['cpu'],
                                            'version_code': alt_fingerprint['version_code']
                                        })
                                        cl2.set_user_agent(alt_fingerprint['user_agent'])

                                        cl2.login(alt_email, password)
                                        cl = cl2
                                        login_success = True
                                        successful_credential = alt_email
                                        alternative_credential = username
                                        current_fingerprint = alt_fingerprint
                                        print(f"{G}✓ Login berhasil dengan email!{W}")
                                    except Exception as e2:
                                        print(f"{R}✗ Login dengan email juga gagal: {str(e2)[:120]}{W}")

                        if login_success:

                            account_path = os.path.join(ACCOUNTS_DIR, folder_name)

                            clean_id = successful_credential.replace('@', '_at_').replace('.', '_')
                            session_file = os.path.join(account_path, f"ig_session_{clean_id}.json")


                            cl.dump_settings(session_file)


                            try:
                                with open(session_file, 'r') as f:
                                    session_data = json.load(f)
                                session_data['device_fingerprint'] = current_fingerprint
                                with open(session_file, 'w') as f:
                                    json.dump(session_data, f, indent=2)
                                print(f"{G}✓ Session file created with device fingerprint{W}")
                            except Exception:
                                print(f"{G}✓ Session file created: ig_session_{clean_id}.json{W}")


                            config['instagram'] = {
                                'enabled': True,
                                'username': successful_credential,
                                'password': password
                            }


                            if alternative_credential:
                                config['instagram']['alternative'] = alternative_credential
                                print(f"{G}✓ Alternative credential saved for fallback{W}")

                            save_account_config(folder_name, config)
                            print(f"\n{G}✓ Instagram tersimpan!{W}")
                        else:

                            print(f"\n{Y}Semua metode login gagal.{W}")
                            print(f"{Y}Credential tetap disimpan, session akan dibuat saat bot jalan.{W}")

                            config['instagram'] = {
                                'enabled': True,
                                'username': username,
                                'password': password
                            }
                            save_account_config(folder_name, config)

                except Exception as e:
                    print(f"\n{R}✗ Error: {e}{W}")
                    print(f"{Y}Credential tetap disimpan, session akan dibuat saat bot jalan.{W}")


                    config['instagram'] = {
                        'enabled': True,
                        'username': username,
                        'password': password
                    }
                    save_account_config(folder_name, config)
            else:

                config['instagram'] = {
                    'enabled': True,
                    'username': username,
                    'password': password
                }
                save_account_config(folder_name, config)
                print(f"\n{G}✓ Instagram tersimpan!{W}")
                print(f"{Y}Session akan dibuat saat bot pertama kali jalan.{W}")
        else:
            print(f"\n{Y}Password kosong, dibatalkan{W}")
    else:
        config['instagram']['enabled'] = False
        save_account_config(folder_name, config)
        print(f"\n{Y}Instagram disabled{W}")

    input("\nEnter untuk kembali...")

def setup_proxy(folder_name, config):
    """Setup Proxy"""
    show_header()
    print(f"{C}[Setup Proxy - {folder_name}]{W}\n")


    if folder_name == 'account_1':
        print(f"{Y}⚠ Account 1 tidak boleh menggunakan proxy!{W}")
        print(f"   Account 1 selalu menggunakan direct connection.")
        input("\nEnter untuk kembali...")
        return


    current = config.get('proxy', {})
    if current.get('proxy_string'):
        print(f"Proxy saat ini:")
        print(f"  IP      : {current.get('ip', 'Unknown')}")
        print(f"  Country : {current.get('country', 'Unknown')}")
        print(f"  City    : {current.get('city', 'Unknown')}")
        print(f"  Verified: {current.get('verified_at', 'Unknown')}")
        print()

    print("Format: host:port:username:password")
    print(f"Contoh: 142.111.48.253:7030:axfgqegu:ijqvkb0vxazy")
    proxy_input = input("\nProxy (enter untuk disable): ").strip()

    if proxy_input:

        from automation_core import parse_proxy, get_ip_location, format_ip_location


        proxy_config = parse_proxy(proxy_input)
        if proxy_config:
            print(f"\n{C}Mengecek proxy location...{W}", end=" ", flush=True)
            proxy_info = get_ip_location(proxy_dict=proxy_config, timeout=15)

            if proxy_info:
                print(f"{G}✓{W}\n")

                location_display = format_ip_location(proxy_info, detailed=True)
                print(f"Location: {location_display}")


                if proxy_info.get('region'):
                    print(f"Region  : {proxy_info['region']}")
                if proxy_info.get('timezone'):
                    print(f"Timezone: {proxy_info['timezone']}")


                config['proxy'] = {
                    'proxy_string': proxy_input,
                    'ip': proxy_info['ip'],
                    'country': proxy_info.get('country', 'Unknown'),
                    'country_code': proxy_info.get('country_code', ''),
                    'city': proxy_info.get('city', 'Unknown'),
                    'region': proxy_info.get('region', ''),
                    'isp': proxy_info.get('isp', ''),
                    'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }
                save_account_config(folder_name, config)
                print(f"\n{G}✓ Proxy tersimpan dan terverifikasi{W}")
            else:
                print(f"{R}✗ Gagal verifikasi proxy{W}")
                print(f"{Y}Proxy tidak disimpan (mungkin proxy mati atau timeout){W}")
        else:
            print(f"\n{R}✗ Format proxy tidak valid{W}")
    else:

        if 'proxy' in config:
            del config['proxy']
            save_account_config(folder_name, config)
            print(f"\n{Y}Proxy disabled (direct connection){W}")

    input("\nEnter untuk kembali...")

def regenerate_user_agent(folder_name, config):
    """Regenerate User Agent"""
    show_header()
    print(f"{C}[Regenerate User Agent - {folder_name}]{W}\n")


    current = config.get('user_agent', {})
    if current.get('device'):
        from automation_core import UserAgentGenerator
        print(f"User Agent saat ini:")
        print(f"  Device  : {current.get('device')}")
        print(f"  Android : {current.get('android_version')}")
        print(f"  Chrome  : {current.get('chrome_version')}")
        print()

    confirm = input(f"{Y}Generate user agent baru? (y/n):{W} ").strip().lower()

    if confirm == 'y':
        from automation_core import UserAgentGenerator
        print(f"\n{C}Generating new user agent...{W}", end=" ", flush=True)

        ua_data = UserAgentGenerator.generate(config=None)
        config['user_agent'] = ua_data
        save_account_config(folder_name, config)
        print(f"{G}✓{W}")
        print(f"Device  : {ua_data['device']}")
        print(f"Android : {ua_data['android_version']}")
        print(f"Chrome  : {ua_data['chrome_version']}")
        print(f"\n{G}✓ User agent berhasil di-generate{W}")
    else:
        print(f"\n{Y}Dibatalkan{W}")

    input("\nEnter untuk kembali...")

def regenerate_device_fingerprint(folder_name, config):
    """Regenerate Device Fingerprint (Instagram)"""
    show_header()
    print(f"{C}[Regenerate Device Fingerprint - {folder_name}]{W}\n")


    current = config.get('device_fingerprint', {})
    if current.get('manufacturer'):
        from automation_core import DeviceFingerprintGenerator
        device_gen = DeviceFingerprintGenerator(config)
        print(f"Device Fingerprint saat ini:")
        print(f"  {device_gen.get_display_info()}")
        print()

    print(f"{Y}PERINGATAN:{W} Regenerate device fingerprint dapat menyebabkan Instagram")
    print(f"mendeteksi aktivitas mencurigakan jika akun sedang aktif.")
    print()

    confirm = input(f"{Y}Generate device fingerprint baru? (y/n):{W} ").strip().lower()

    if confirm == 'y':
        from automation_core import DeviceFingerprintGenerator
        print(f"\n{C}Generating new device fingerprint...{W}", end=" ", flush=True)

        device_gen = DeviceFingerprintGenerator(config=None)
        fingerprint = device_gen.generate()
        config['device_fingerprint'] = fingerprint
        save_account_config(folder_name, config)
        print(f"{G}✓{W}")
        print(f"Device: {device_gen.get_display_info()}")
        print(f"\n{G}✓ Device fingerprint berhasil di-generate{W}")
        print(f"\n{Y}Note: Session Instagram akan direset saat login berikutnya{W}")
    else:
        print(f"\n{Y}Dibatalkan{W}")

    input("\nEnter untuk kembali...")

def show_task_types(config):
    """Show task types configuration"""
    show_header()
    print(f"{C}[Task Types]{W}\n")

    task_types = config.get('task_types', {})

    print("Task yang diaktifkan:\n")

    for key, enabled in task_types.items():
        status = f"{G}ON{W}" if enabled else f"{R}OFF{W}"
        print(f"  {key:25s} : {status}")

    input("\nEnter untuk kembali...")

def send_account_menu():
    """Send account to Telegram"""
    show_header()
    print(f"{C}[Send Akun ke Telegram]{W}\n")

    folders = show_accounts_list()

    if not folders:
        input("Enter untuk kembali...")
        return

    print(f"Pilih akun untuk dikirim ke Telegram (1-{len(folders)}, 0=batal):")
    choice = input("Nomor: ").strip()

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(folders):
        print(f"{Y}Dibatalkan{W}")
        time.sleep(1)
        return

    folder_name = folders[int(choice) - 1]
    config = load_account_config(folder_name)

    if not config:
        print(f"\n{R}✗ Gagal load config{W}")
        input("\nEnter untuk kembali...")
        return

    print(f"\n{C}Mengirim {folder_name} ke Telegram...{W}")

    if send_account_to_telegram(folder_name, config):
        print(f"\n{G}✓ Akun berhasil dikirim ke Telegram!{W}")
        print(f"\n{Y}Langkah selanjutnya:{W}")
        print(f"1. Buka Telegram")
        print(f"2. Forward/Kirim balik message dari bot")
        print(f"3. Akun akan otomatis diupdate di VPS")
    else:
        print(f"\n{R}✗ Gagal mengirim ke Telegram{W}")

    input("\nEnter untuk kembali...")

def delete_account():
    """Delete account"""
    show_header()
    print(f"{C}[Hapus Akun]{W}\n")

    folders = show_accounts_list()

    if not folders:
        input("Enter untuk kembali...")
        return

    print(f"{R}PERINGATAN: Akun yang dihapus tidak dapat dikembalikan!{W}\n")
    print(f"Pilih akun untuk dihapus (1-{len(folders)}, 0=batal):")
    choice = input("Nomor: ").strip()

    if not choice.isdigit() or int(choice) < 1 or int(choice) > len(folders):
        print(f"{Y}Dibatalkan{W}")
        time.sleep(1)
        return

    folder_name = folders[int(choice) - 1]
    folder_path = os.path.join(ACCOUNTS_DIR, folder_name)


    print(f"\n{R}Yakin ingin menghapus {folder_name}?{W}")
    print(f"Ketik '{folder_name}' untuk konfirmasi:")
    confirm = input().strip()

    if confirm == folder_name:
        import shutil
        try:
            shutil.rmtree(folder_path)
            print(f"\n{G}✓ {folder_name} berhasil dihapus!{W}")
        except Exception as e:
            print(f"\n{R}✗ Gagal menghapus: {e}{W}")
    else:
        print(f"\n{Y}Dibatalkan (konfirmasi tidak cocok){W}")

    input("\nEnter untuk kembali...")

def add_account_from_json():
    """Add account by importing full JSON config"""
    show_header()
    print(f"{C}[Import Akun via JSON]{W}\n")

    print("Paste JSON config lengkap di bawah ini.")
    print("Format JSON harus lengkap dengan credentials, task_types, vk_api, dll.")
    print(f"{Y}Ketik 'END' di baris baru untuk selesai.{W}\n")


    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == 'END':
                break
            lines.append(line)
        except EOFError:
            break
        except KeyboardInterrupt:
            print(f"\n{Y}Dibatalkan{W}")
            input("\nEnter untuk kembali...")
            return

    json_str = '\n'.join(lines)

    if not json_str.strip():
        print(f"\n{R}✗ JSON kosong{W}")
        input("\nEnter untuk kembali...")
        return


    try:
        config = json.loads(json_str)
        print(f"\n{G}✓ JSON valid{W}")
    except json.JSONDecodeError as e:
        print(f"\n{R}✗ JSON tidak valid: {e}{W}")
        input("\nEnter untuk kembali...")
        return


    required_keys = ['credentials', 'task_types']
    missing_keys = [key for key in required_keys if key not in config]

    if missing_keys:
        print(f"\n{R}✗ JSON tidak lengkap. Missing keys: {', '.join(missing_keys)}{W}")
        input("\nEnter untuk kembali...")
        return


    print(f"\n{C}Config Summary:{W}")


    cookies = config.get('credentials', {}).get('cookies', {})
    if cookies.get('vkstoken'):
        print(f"  Cookie   : {G}✓ vkstoken: ...{cookies['vkstoken'][-15:]}{W}")
    else:
        print(f"  Cookie   : {R}✗ Tidak ada{W}")


    vk_api = config.get('vk_api', {})
    if vk_api.get('enabled') and vk_api.get('access_token'):
        print(f"  VK API   : {G}✓ User ID: {vk_api.get('user_id', 'N/A')}{W}")
    else:
        print(f"  VK API   : {Y}Disabled{W}")


    ig = config.get('instagram', {})
    if ig.get('enabled') and ig.get('username'):
        print(f"  Instagram: {G}✓ @{ig['username']}{W}")
    else:
        print(f"  Instagram: {Y}Disabled{W}")


    proxy = config.get('proxy', {})
    if proxy.get('proxy_string'):
        from automation_core import get_country_flag
        flag = get_country_flag(proxy.get('country_code') or proxy.get('country'))
        print(f"  Proxy    : {G}✓ {flag} {proxy.get('ip', 'N/A')} ({proxy.get('country', 'N/A')}){W}")
    else:
        print(f"  Proxy    : {Y}No Proxy{W}")


    ua = config.get('user_agent', {})
    if ua.get('device'):
        print(f"  Device   : {C}{ua['device']} | Android {ua.get('android_version', 'N/A')}{W}")


    task_types = config.get('task_types', {})
    enabled_tasks = [k for k, v in task_types.items() if v]
    print(f"  Tasks    : {len(enabled_tasks)}/{len(task_types)} enabled")

    print()


    folders = get_account_folders()
    if folders:

        numbers = []
        for folder in folders:
            if '_' in folder:
                try:
                    num = int(folder.split('_')[1])
                    numbers.append(num)
                except:
                    pass

        if numbers:
            next_num = max(numbers) + 1
        else:
            next_num = 1
    else:
        next_num = 1

    account_name = f"account_{next_num}"
    print(f"{C}Auto-detected account name: {G}{account_name}{W}")
    print()


    folder_path = os.path.join(ACCOUNTS_DIR, account_name)
    while os.path.exists(folder_path):
        next_num += 1
        account_name = f"account_{next_num}"
        folder_path = os.path.join(ACCOUNTS_DIR, account_name)
        print(f"{Y}Folder exists, trying: {account_name}{W}")


    try:
        os.makedirs(folder_path, exist_ok=True)
        print(f"\n{G}✓ Folder '{account_name}' dibuat{W}")
    except Exception as e:
        print(f"\n{R}✗ Gagal membuat folder: {e}{W}")
        input("\nEnter untuk kembali...")
        return


    try:
        save_account_config(account_name, config)
        print(f"{G}✓ Config disimpan ke {account_name}/config.json{W}")


        ig = config.get('instagram', {})
        if ig.get('enabled') and ig.get('username'):
            username = ig['username']
            clean_id = username.replace('@', '_at_').replace('.', '_')
            session_file = f"ig_session_{clean_id}.json"

            if os.path.exists(session_file):

                import shutil
                dest_session = os.path.join(folder_path, session_file)
                try:
                    shutil.copy2(session_file, dest_session)
                    print(f"{G}✓ Instagram session file copied{W}")
                except Exception as e:
                    print(f"{Y}⚠ Gagal copy IG session: {e}{W}")

        print(f"\n{G}✓✓✓ Akun '{account_name}' berhasil diimport!{W}")
        print(f"\n{C}Akun siap digunakan.{W}")

    except Exception as e:
        print(f"\n{R}✗ Gagal menyimpan config: {e}{W}")

    input("\nEnter untuk kembali...")


COUNTRIES = ["1", "4", "50", "81", "98", "100", "102", "112", "123", "138", "145", "161", "182"]
IG_DOWNLOADS_DIR = os.path.join(os.path.dirname(__file__), "ig_downloads")

def _check_ig_bound_on_web(config):
    """Check if IG already bound on VKSerfing web, return username or None"""
    import re
    try:
        creds = config.get('credentials', {})
        cookies = creds.get('cookies', {})
        proxy_str = config.get('proxy', {}).get('proxy_string')
        proxy = parse_proxy_string(proxy_str)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/143.0 Mobile Safari/537.36',
            'X-XSRF-Token': creds.get('xsrf_token', ''),
            'X-Ajax-Html': '1',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/plain, */*',
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None

        resp = requests.get('https://vkserfing.com/settings', headers=headers, cookies=cookies, proxies=proxies, timeout=15)
        if resp.status_code == 200:


            match = re.search(r'data-icon=\\"instagram\\"[^>]*data-alias=\\"@([^"\\]+)\\"', resp.text)
            if not match:

                match = re.search(r'data-icon="instagram"[^>]*data-alias="@([^"]+)"', resp.text)
            if match:
                return match.group(1)
    except:
        pass
    return None

def _scan_ig_status_single(acc_name, config):
    """Scan single account for IG status (for parallel processing)"""
    acc_dir = os.path.join(ACCOUNTS_DIR, acc_name)


    ig = config.get('instagram', {})
    has_ig_config = ig.get('enabled') or ig.get('username')
    try:
        has_ig_session = any(f.startswith('ig_session_') for f in os.listdir(acc_dir))
    except:
        has_ig_session = False

    if has_ig_config or has_ig_session:
        ig_user = ig.get('username', 'session')
        return {'account': acc_name, 'status': 'has_ig', 'ig_user': ig_user}


    ig_on_web = _check_ig_bound_on_web(config)
    if ig_on_web:
        return {'account': acc_name, 'status': 'has_ig', 'ig_user': ig_on_web}

    return {'account': acc_name, 'status': 'no_ig', 'ig_user': None}

def bind_instagram_to_account():
    """Bind Instagram to VKSerfing account"""
    show_header()
    print(f"{Y}[Bind Instagram ke Akun]{W}\n")

    folders = get_account_folders()
    print(f"{C}Scanning {len(folders)} accounts (parallel)...{W}")


    accounts_with_ig = []
    accounts_no_ig = []

    def scan_worker(acc_name, config):
        return _scan_ig_status_single(acc_name, config)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for acc in folders:
            config = load_account_config(acc)
            if config:
                futures[executor.submit(scan_worker, acc, config)] = acc

        done = 0
        total = len(futures)
        for future in as_completed(futures):
            done += 1
            print(f"\r  Scanning... [{done}/{total}]", end="", flush=True)
            try:
                result = future.result(timeout=20)
                if result['status'] == 'has_ig':
                    accounts_with_ig.append((result['account'], result['ig_user']))
                else:
                    accounts_no_ig.append(result['account'])
            except:
                accounts_no_ig.append(futures[future])

    print(f"\r  Scanning... [{total}/{total}] Done!{' '*20}")

    print(f"\n{G}Akun dengan IG ({len(accounts_with_ig)}):{W}")
    for acc, ig_user in accounts_with_ig[:10]:
        print(f"  ✓ {acc} → @{ig_user}")
    if len(accounts_with_ig) > 10:
        print(f"  ... dan {len(accounts_with_ig)-10} lainnya")

    if not accounts_no_ig:
        print(f"\n{G}Semua akun sudah punya IG!{W}")
        input("\nEnter...")
        return


    while accounts_no_ig:
        print(f"\n{Y}Akun tanpa IG ({len(accounts_no_ig)}):{W}")
        for i, acc in enumerate(accounts_no_ig, 1):
            print(f"  {i}. {acc}")
        print(f"  0. Kembali")

        try:
            choice = input("\nPilih akun: ").strip()
            if choice == '0':
                return
            idx = int(choice) - 1
            if idx < 0 or idx >= len(accounts_no_ig):
                print(f"{R}Invalid!{W}")
                continue
            account_name = accounts_no_ig[idx]
        except:
            print(f"{R}Invalid!{W}")
            continue

        config_file = os.path.join(ACCOUNTS_DIR, account_name, "config.json")
        with open(config_file) as f:
            config = json.load(f)

        print(f"\n{C}Selected: {account_name}{W}")


        success = _do_bind_ig(account_name, config, config_file)

        if success:
            accounts_no_ig.remove(account_name)

        if not accounts_no_ig:
            print(f"\n{G}Semua akun sudah punya IG!{W}")
            input("\nEnter...")
            return


        cont = input(f"\n{Y}Lanjut bind akun lain? (y/n): {W}").strip().lower()
        if cont != 'y':
            return

def _do_bind_ig(account_name, config, config_file):
    """Execute bind process, return True if success"""
    print(f"\n{'='*50}")
    print(f"🔐 STEP 1: Login VKSerfing")
    print(f"{'='*50}")

    vks_session, xsrf = _vks_login(config)
    if not vks_session:
        print(f"{R}VKS session invalid!{W}")
        return False


    print(f"\n{'='*50}")
    print(f"📱 STEP 2: Login Instagram")
    print(f"{'='*50}")

    ig_user = input("IG username/email: ").strip()
    ig_pass = input("IG password: ").strip()
    if not ig_user or not ig_pass:
        print(f"{R}Required!{W}")
        return False

    ig_session, ig_username, ig_client = _ig_login(ig_user, ig_pass)
    if not ig_session:
        print(f"{R}IG login failed!{W}")
        return False


    print(f"\n{'='*50}")
    print(f"🔍 STEP 3: Setup IG Profile")
    print(f"{'='*50}")
    _setup_ig_profile(ig_client)


    print(f"\n{'='*50}")
    print(f"🔗 STEP 4: Bind IG to VKS")
    print(f"{'='*50}")

    if not _bind_ig_vks(vks_session, xsrf, ig_client, ig_username):
        print(f"{R}Binding failed!{W}")
        return False


    print(f"\n{'='*50}")
    print(f"📝 STEP 5: Set VKS Profile")
    print(f"{'='*50}")
    _set_vks_profile(vks_session, xsrf)


    print(f"\n{'='*50}")
    print(f"💾 STEP 6: Save")
    print(f"{'='*50}")


    session_file = f"ig_session_{ig_username}.json"
    with open(os.path.join(ACCOUNTS_DIR, account_name, session_file), 'w') as f:
        json.dump(ig_session, f, indent=2)


    config['instagram'] = {
        'enabled': True,
        'username': ig_username,
        'password': ig_pass,
        'session_file': session_file
    }
    config['task_types']['instagram_followers'] = True
    config['task_types']['instagram_likes'] = True

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"{G}✓ Saved!{W}")
    print(f"\n{G}✓✓✓ @{ig_username} bound to {account_name}!{W}")
    return True

def _vks_login(config):
    """Login VKS via cookies"""
    import requests
    creds = config.get('credentials', {})
    cookies = creds.get('cookies', {})
    xsrf = creds.get('xsrf_token', '')
    proxy_str = config.get('proxy', {}).get('proxy_string', '')
    proxy = parse_proxy_string(proxy_str)

    session = requests.Session()
    if proxy:
        session.proxies.update({'http': proxy, 'https': proxy})

    for k, v in cookies.items():
        session.cookies.set(k, v)

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14) Chrome/131.0.0.0 Mobile Safari/537.36',
        'X-Requested-With': 'XMLHttpRequest'
    })

    try:
        r = session.get('https://vkserfing.ru/assignments/instagram', timeout=30)
        if r.status_code == 200:
            import re
            m = re.search(r"TOKEN\s*=\s*['\"]([^'\"]+)['\"]", r.text)
            if m:
                xsrf = m.group(1)
            print(f"{G}✓ VKS session valid{W}")
            return session, xsrf
    except Exception as e:
        print(f"{R}Error: {e}{W}")
    return None, None

def _ig_login(username, password):
    """Login Instagram"""
    try:
        from instagrapi import Client
        import uuid

        cl = Client()
        cl.delay_range = [1, 3]
        cl.login(username, password)

        info = cl.account_info()
        actual_username = info.username
        print(f"{G}✓ Login OK! @{actual_username}{W}")

        session_data = {
            'authorization_data': {
                'ds_user_id': str(cl.user_id),
                'sessionid': cl.sessionid
            },
            'device_settings': cl.device,
            'user_agent': cl.user_agent
        }
        return session_data, actual_username, cl
    except Exception as e:
        print(f"{R}Error: {e}{W}")
    return None, None, None

def _setup_ig_profile(ig_client):
    """Setup IG profile: name, pic, and 5-7 posts"""
    import random
    from faker import Faker
    fake = Faker()


    try:
        name = fake.first_name()
        ig_client.account_edit(full_name=name)
        print(f"{G}✓ Name set: {name}{W}")
        time.sleep(2)
    except Exception as e:
        print(f"{Y}Warning set name: {e}{W}")


    try:
        user_info = ig_client.account_info()
        media_count = user_info.get('user', {}).get('media_count', 0)
        if media_count >= 5:
            print(f"{G}✓ Already has {media_count} posts, skip upload{W}")
            return
    except:
        pass


    photos = []
    if os.path.exists(IG_DOWNLOADS_DIR):
        for root, dirs, files in os.walk(IG_DOWNLOADS_DIR):
            for f in files:
                if f.endswith(('.jpg', '.jpeg', '.png')):
                    photos.append(os.path.join(root, f))

    if not photos:
        print(f"{Y}No photos in {IG_DOWNLOADS_DIR}{W}")
        return

    random.shuffle(photos)


    try:
        ig_client.account_change_picture(photos[0])
        print(f"{G}✓ Profile pic set{W}")
        time.sleep(2)
    except Exception as e:
        print(f"{Y}Warning profile pic: {e}{W}")


    num_posts = random.randint(5, 7)
    photos_for_posts = photos[1:num_posts+1] if len(photos) > num_posts else photos[1:]

    print(f"{C}Uploading {len(photos_for_posts)} posts...{W}")
    for i, photo in enumerate(photos_for_posts):
        try:
            caption = fake.sentence(nb_words=random.randint(3, 8))
            ig_client.photo_upload(photo, caption)
            print(f"  [{i+1}/{len(photos_for_posts)}] ✓ Posted")
            time.sleep(random.randint(5, 10))
        except Exception as e:
            print(f"  [{i+1}/{len(photos_for_posts)}] ✗ {str(e)[:30]}")
            break

    print(f"{G}✓ Profile setup done{W}")

def _bind_ig_vks(vks_session, xsrf, ig_client, ig_username):
    """Bind IG to VKS"""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'x-xsrf-token': xsrf
    }


    print(f"  [1/4] Get phrase...")
    r = vks_session.get('https://vkserfing.ru/auth/phrase', headers=headers, timeout=30)
    if r.status_code != 200:
        return False
    data = r.json()
    phrase = data['phrase']['text']
    phrase_hash = data['phrase']['hash']
    print(f"  Phrase: {phrase}")


    print(f"  [2/4] Set bio...")
    try:
        ig_client.account_edit(biography=phrase)
        print(f"  {G}✓ Bio set{W}")
    except Exception as e:
        print(f"  {R}Failed: {e}{W}")
        return False

    time.sleep(3)


    print(f"  [3/4] Validate...")
    r = vks_session.post('https://vkserfing.ru/auth/presocial/instagram', headers=headers,
                         json={'username': f'@{ig_username}', 'phraseToken': phrase_hash}, timeout=30)
    if r.status_code != 200:
        return False
    print(f"  {G}✓ Validated{W}")


    print(f"  [4/4] Connect...")
    r = vks_session.post('https://vkserfing.ru/auth/social/instagram', headers=headers,
                         json={'username': f'@{ig_username}', 'phraseToken': phrase_hash}, timeout=30)
    if r.status_code != 200:
        return False

    data = r.json()
    if data.get('status') != 'success':
        print(f"  {R}Error: {data}{W}")
        return False

    print(f"  {G}✓ Connected!{W}")


    try:
        ig_client.account_edit(biography='')
    except:
        pass

    return True

def _set_vks_profile(vks_session, xsrf):
    """Set VKS profile data"""
    headers = {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'x-xsrf-token': xsrf
    }

    country_id = random.choice(COUNTRIES)


    try:
        r = vks_session.get(f'https://vkserfing.ru/get_cities?country_id={country_id}', headers=headers, timeout=30)
        cities = r.json().get('data', []) if r.status_code == 200 else []
    except:
        cities = []

    city_id = random.choice(cities)['value'] if cities else '1'
    birthday = f"{random.randint(1,28):02d}.{random.randint(1,12):02d}.{random.randint(1990,2006)}"
    sex = random.choice(['1', '2'])

    payload = {
        'country_id': str(country_id),
        'city_id': str(city_id),
        'birthday': birthday,
        'sex': sex,
        'platform': 'instagram'
    }

    try:
        r = vks_session.post('https://vkserfing.ru/account/data', headers=headers, json=payload, timeout=30)
        if r.status_code == 200 and r.json().get('status') == 'success':
            print(f"{G}✓ Profile data saved{W}")
        else:
            print(f"{Y}⚠ Profile data failed{W}")
    except:
        print(f"{Y}⚠ Profile data failed{W}")





def _load_telegram_api():
    """Load Telegram API credentials from config"""
    config_path = os.path.join(os.path.dirname(__file__), 'config', 'api_keys.json')
    try:
        with open(config_path) as f:
            config = json.load(f)
            tg = config.get('telegram', {})
            api_id = tg.get('api_id', '')
            api_hash = tg.get('api_hash', '')
            if api_id and api_hash and not str(api_id).startswith('YOUR_'):
                return int(api_id), api_hash
    except:
        pass
    return None, None

TELETHON_API_ID, TELETHON_API_HASH = _load_telegram_api()

if not TELETHON_API_ID:
    print(f"{Y}⚠ Telegram API not configured. Edit config/api_keys.json to enable Telegram binding.{W}")

def _create_vks_session(config, use_proxy=True, refresh_xsrf=False):
    """Create VKS session with proper headers"""
    creds = config.get('credentials', {})
    cookies = creds.get('cookies', {})
    xsrf = creds.get('xsrf_token', '')
    proxy_str = config.get('proxy', {}).get('proxy_string')

    session = requests.Session()
    if use_proxy and proxy_str:
        session.proxies.update({'http': proxy_str, 'https': proxy_str})

    for k, v in cookies.items():
        session.cookies.set(k, v)

    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Linux; Android 15; TECNO LI9 Build/AP3A.240905.015.A2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.7499.146 Mobile Safari/537.36',
        'sec-ch-ua': '"Android WebView";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'sec-ch-ua-mobile': '?1',
        'sec-ch-ua-platform': '"Android"',
        'X-Requested-With': 'XMLHttpRequest',
    })


    if refresh_xsrf:
        try:
            r = session.get('https://vkserfing.com/', timeout=15)
            if r.status_code == 200:

                import re
                token_match = re.search(r'TOKEN\s*[=:]\s*["\']([^"\']+)["\']', r.text)
                if token_match:
                    new_xsrf = token_match.group(1)
                    if new_xsrf and new_xsrf != xsrf:
                        print(f"{C}✓ XSRF refreshed{W}")
                        xsrf = new_xsrf
                        session.headers['X-XSRF-Token'] = new_xsrf
        except:
            pass

    return session, xsrf

def _tg_get_token(session, xsrf, domain):
    """Full flow: GET /settings -> /other/base -> /accounts to get token"""
    headers_base = {
        'X-XSRF-Token': xsrf,
        'Accept': 'application/json, text/plain, */*',
    }
    headers_html = {
        'X-XSRF-Token': xsrf,
        'X-Ajax-Html': '1',
        'Accept': 'application/json, text/plain, */*',
    }


    try:
        r = session.get(f'{domain}/settings', timeout=20)
        if r.status_code != 200:
            return None, f"settings failed: {r.status_code}"
    except Exception as e:
        return None, f"settings error: {e}"


    try:
        r = session.get(f'{domain}/other/base', headers=headers_base, timeout=20)
        if r.status_code != 200:
            return None, f"other/base failed: {r.status_code}"
    except Exception as e:
        return None, f"other/base error: {e}"


    try:
        r = session.get(f'{domain}/accounts', headers=headers_html, timeout=20)
        if r.status_code != 200:
            return None, f"accounts failed: {r.status_code}"


        match = re.search(r'telegram-auth[^>]*token=\\"([^"\\]+)\\"', r.text)
        if not match:
            match = re.search(r'telegram-auth[^>]*token="([^"]+)"', r.text)
        if match:
            return match.group(1), None
        return None, "token not found in response"
    except Exception as e:
        return None, f"accounts error: {e}"

def _tg_verify_binding(session, xsrf, token, domain, max_retries=2):
    """POST /auth/presocial/telegram then /auth/social/telegram with retry"""
    headers = {
        'Content-Type': 'application/json',
        'X-XSRF-Token': xsrf,
        'Accept': 'application/json, text/plain, */*',
        'Origin': domain,
    }


    for attempt in range(max_retries):
        try:
            if attempt > 0:
                wait = 3
                print(f"{Y}⚠ Retry {attempt+1}/{max_retries} in {wait}s...{W}")
                time.sleep(wait)

            r = session.post(f'{domain}/auth/presocial/telegram',
                            json={'token': token}, headers=headers, timeout=15)
            if r.status_code != 200:
                if attempt < max_retries - 1:
                    continue
                return None, f"presocial status: {r.status_code}"

            data = r.json()
            if data.get('status') == 'error':
                error_msg = data.get('message')
                if attempt < max_retries - 1:
                    print(f"{Y}⚠ Error: {error_msg}{W}")
                    continue
                return None, f"presocial error: {error_msg}"
            if data.get('status') != 'success' and 'auth_data' not in data:
                return None, f"presocial unexpected: {data}"

            print(f"{G}✓ presocial OK{W}")
            break
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"{Y}⚠ Exception: {e}{W}")
                continue
            else:
                return None, f"presocial exception: {e}"


    try:
        r = session.post(f'{domain}/auth/social/telegram',
                        json={'token': token}, headers=headers, timeout=15)
        if r.status_code != 200:
            return None, f"social status: {r.status_code}"

        data = r.json()
        if data.get('status') == 'success':
            print(f"{G}✓ social OK - redirect: {data.get('redirect')}{W}")
            return data, None
        return None, f"social failed: {data}"
    except Exception as e:
        return None, f"social exception: {e}"

def _tg_set_profile(session, xsrf, domain):
    """POST /account/data with telegram platform"""
    headers = {
        'Content-Type': 'application/json',
        'X-XSRF-Token': xsrf,
        'Accept': 'application/json, text/plain, */*',
        'Origin': domain,
    }

    payload = {
        'mail': None,
        'country_id': '4',
        'birthday': '23.06.2000',
        'city_id': None,
        'sex': '1',
        'platform': 'telegram'
    }

    try:
        r = session.post(f'{domain}/account/data', json=payload, headers=headers, timeout=20)
        if r.status_code == 200 and r.json().get('status') == 'success':
            print(f"{G}✓ Profile saved{W}")
            return True
    except:
        pass
    print(f"{Y}⚠ Profile save failed{W}")
    return False

def _check_tg_bound_on_web(config):
    """Check if Telegram already bound, return username or None"""
    try:
        creds = config.get('credentials', {})
        cookies = creds.get('cookies', {})
        proxy_str = config.get('proxy', {}).get('proxy_string')
        proxy = parse_proxy_string(proxy_str)

        headers = {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/143.0 Mobile Safari/537.36',
            'X-XSRF-Token': creds.get('xsrf_token', ''),
            'X-Ajax-Html': '1',
            'X-Requested-With': 'XMLHttpRequest',
        }
        proxies = {'http': proxy, 'https': proxy} if proxy else None

        resp = requests.get('https://vkserfing.com/settings', headers=headers, cookies=cookies, proxies=proxies, timeout=15)
        if resp.status_code == 200:

            match = re.search(r'data-platform=\\"telegram\\"[^>]*data-alias=\\"@([^"\\]+)\\"', resp.text)
            if not match:
                match = re.search(r'data-platform="telegram"[^>]*data-alias="@([^"]+)"', resp.text)
            if match:
                return match.group(1)
    except:
        pass
    return None

async def _telegram_auth_via_telethon(session_path, token):
    """Login Telegram via Telethon and interact with vkserfing_bot"""
    if not TELETHON_API_ID or not TELETHON_API_HASH:
        print(f"{R}Telegram API not configured! Edit config/api_keys.json{W}")
        return None

    from telethon import TelegramClient
    from telethon.tl.functions.contacts import GetContactsRequest
    from telethon.tl.types import InputPhoneContact
    import asyncio

    client = TelegramClient(session_path, TELETHON_API_ID, TELETHON_API_HASH)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print(f"{Y}Session tidak valid, perlu login...{W}")
            phone = input("Nomor HP (format: +628xxx): ").strip()
            if not phone:
                return None

            await client.send_code_request(phone)
            code = input("Kode OTP dari Telegram: ").strip()

            try:
                await client.sign_in(phone, code)
            except Exception as e:
                if 'Two-step' in str(e) or '2FA' in str(e):
                    password = input("Password 2FA: ").strip()
                    await client.sign_in(password=password)
                else:
                    raise

        me = await client.get_me()
        print(f"{G}✓ Logged in as @{me.username or me.first_name} ({me.phone}){W}")


        print(f"{C}Sending /start to @vkserfing_bot...{W}")
        bot = await client.get_entity('vkserfing_bot')
        await client.send_message(bot, f'/start {token}')
        await asyncio.sleep(2)


        print(f"{C}Sharing contact...{W}")
        from telethon.tl.functions.messages import SendMediaRequest
        from telethon.tl.types import InputMediaContact
        from telethon import utils

        contact = InputMediaContact(
            phone_number='+' + me.phone if not me.phone.startswith('+') else me.phone,
            first_name=me.first_name or 'User',
            last_name=me.last_name or '',
            vcard=''
        )
        input_peer = await client.get_input_entity(bot)
        await client(SendMediaRequest(
            peer=input_peer,
            media=contact,
            message=''
        ))
        await asyncio.sleep(5)


        messages = await client.get_messages(bot, limit=5)
        for msg in messages:
            if msg.text and 'Почти готово' in msg.text:
                print(f"{G}✓ Bot accepted contact!{W}")
                print(f"{C}Waiting 15s for server sync...{W}")
                await asyncio.sleep(15)
                return {
                    'id': me.id,
                    'username': me.username,
                    'phone': me.phone,
                    'first_name': me.first_name,
                    'last_name': me.last_name or ''
                }

        print(f"{Y}⚠ Bot response not detected, checking anyway...{W}")
        return {
            'id': me.id,
            'username': me.username,
            'phone': me.phone,
            'first_name': me.first_name,
            'last_name': me.last_name or ''
        }

    except Exception as e:
        if 'FloodWait' in str(e):
            wait = int(re.search(r'(\d+)', str(e)).group(1)) if re.search(r'(\d+)', str(e)) else 60
            print(f"{R}FloodWait: tunggu {wait} detik{W}")
        else:
            print(f"{R}Telethon error: {e}{W}")
        return None
    finally:
        await client.disconnect()

def _do_bind_telegram(account_name, config, config_file):
    """Execute Telegram bind process with correct flow from HAR"""
    import asyncio

    domains = ['https://vkserfing.com', 'https://vkserfing.ru']

    print(f"\n{'='*50}")
    print(f"🔐 STEP 1: Get Token from VKSerfing")
    print(f"{'='*50}")


    token = None
    session = None
    xsrf = None
    working_domain = None

    for use_proxy in [False, True]:
        if token:
            break
        proxy_mode = 'proxy' if use_proxy else 'direct'
        session, xsrf = _create_vks_session(config, use_proxy=use_proxy)

        for domain in domains:
            print(f"{C}Trying {domain} ({proxy_mode})...{W}")
            token, err = _tg_get_token(session, xsrf, domain)
            if token:
                print(f"{G}✓ Token: {token[:20]}...{W}")
                working_domain = domain
                break
            else:
                print(f"{Y}⚠ {err}{W}")

    if not token:
        print(f"{R}Failed to get token from all domains!{W}")
        return False

    print(f"\n{'='*50}")
    print(f"📱 STEP 2: Telegram Auth via Telethon")
    print(f"{'='*50}")


    session_dir = os.path.join(ACCOUNTS_DIR, account_name)
    existing_sessions = [f for f in os.listdir(session_dir) if f.endswith('.session')]

    if existing_sessions:
        print(f"Session tersedia: {existing_sessions}")
        session_file = existing_sessions[0]
    else:
        session_file = f"telegram_{account_name}.session"

    session_path = os.path.join(session_dir, session_file.replace('.session', ''))

    tg_info = asyncio.get_event_loop().run_until_complete(
        _telegram_auth_via_telethon(session_path, token)
    )

    if not tg_info:
        print(f"{R}Telegram auth failed!{W}")
        return False


    import gc, subprocess
    gc.collect()
    print(f"{C}Waiting 3s for connection cleanup...{W}")
    time.sleep(3)

    print(f"\n{'='*50}")
    print(f"🔗 STEP 3: Verify on VKSerfing")
    print(f"{'='*50}")


    script_dir = os.path.dirname(os.path.abspath(__file__))
    verify_script = f'''
import sys, json
sys.path.insert(0, '{script_dir}')
from main import _create_vks_session, _tg_verify_binding, _tg_set_profile

with open("{config_file}") as f:
    config = json.load(f)

print("Refreshing XSRF token...")
session, xsrf = _create_vks_session(config, use_proxy=False, refresh_xsrf=True)
token = "{token}"

result, err = _tg_verify_binding(session, xsrf, token, "https://vkserfing.com")
if not result:
    print(f"COM failed: {{err}}")
    result, err = _tg_verify_binding(session, xsrf, token, "https://vkserfing.ru")

if result:
    _tg_set_profile(session, xsrf, "https://vkserfing.com")
    print("SUCCESS")
else:
    print(f"FAILED: {{err}}")
'''

    import sys
    proc = subprocess.Popen(['python3', '-c', verify_script],
                           stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT,
                           text=True,
                           cwd=script_dir)


    output_lines = []
    try:
        for line in proc.stdout:
            print(line, end='')
            output_lines.append(line)
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        print(f"{R}Timeout after 30s!{W}")
        return False

    if proc.returncode != 0:
        print(f"{R}Process failed with code {proc.returncode}{W}")
        return False


    full_output = ''.join(output_lines)
    if 'SUCCESS' not in full_output:
        print(f"{R}Verification failed!{W}")
        return False

    print(f"\n{'='*50}")
    print(f"💾 STEP 4: Save Config")
    print(f"{'='*50}")


    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
    from datetime import datetime

    session_string = None
    try:
        client = TelegramClient(session_path, TELETHON_API_ID, TELETHON_API_HASH)
        client.connect()
        if client.is_user_authorized():
            session_string = StringSession.save(client.session)
        client.disconnect()
    except Exception as e:
        print(f"{Y}⚠ Could not extract session_string: {e}{W}")

    config['telegram'] = {
        'bound': True,
        'id': tg_info['id'],
        'username': tg_info['username'],
        'phone': tg_info['phone'],
        'first_name': tg_info['first_name'],
        'last_name': tg_info['last_name'],
        'session': session_file if session_file.endswith('.session') else session_file + '.session',
        'session_string': session_string,
        'api_id': str(TELETHON_API_ID),
        'api_hash': TELETHON_API_HASH,
        'bind_time': datetime.now().isoformat()
    }
    config['task_types']['telegram_followers'] = True
    config['task_types']['telegram_views'] = True

    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"{G}✓ Saved to config.json{W}")
    print(f"{G}✓ Telegram @{tg_info['username']} bound to {account_name}!{W}")
    return True

def _fetch_balance_quick(config):
    """Quick fetch balance from /cashout"""
    try:
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

        resp = requests.get('https://vkserfing.com/cashout', headers=headers, cookies=cookies, proxies=proxies, timeout=10)
        if resp.status_code == 200:
            html_content = resp.json().get('html', '')
            m = re.search(r'<span>([0-9.]+)</span>', html_content)
            if m:
                return float(m.group(1))
    except:
        pass
    return 0.0

def _scan_tg_status_single(acc_name, config):
    """Scan single account for TG status + balance (for parallel processing)"""

    balance = _fetch_balance_quick(config)


    tg_config = config.get('telegram', {})
    if tg_config.get('bound'):
        tg_user = tg_config.get('username', 'bound')
        return {'account': acc_name, 'status': 'has_tg', 'tg_user': tg_user, 'balance': balance}


    tg_web = _check_tg_bound_on_web(config)
    if tg_web:
        return {'account': acc_name, 'status': 'has_tg', 'tg_user': tg_web, 'balance': balance}

    return {'account': acc_name, 'status': 'no_tg', 'tg_user': None, 'balance': balance}

def bind_telegram_to_account():
    """Bind Telegram to accounts"""
    global STOP_FLAG
    STOP_FLAG = False

    show_header()
    print(f"{C}[Bind Telegram ke Akun]{W}\n")

    folders = get_account_folders()
    if not folders:
        print(f"{Y}Tidak ada akun.{W}")
        input("\nEnter untuk kembali...")
        return

    print(f"Total akun: {len(folders)}\n")
    print(f"  1. {G}Scan semua akun{W} (parallel - cek status TG + balance)")
    print(f"  2. {C}Langsung pilih akun{W} (tanpa scan)")
    print(f"  0. Kembali\n")

    mode = input("Pilih mode: ").strip()

    if mode == '0':
        return
    elif mode == '2':

        print(f"\n{Y}Daftar akun:{W}")
        for i, folder in enumerate(folders, 1):
            print(f"  {i}. {folder}")

        print(f"\n{Y}Pilih nomor akun (0 = kembali):{W}")
        choice = input("Pilih: ").strip()

        if choice == '0':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(folders):
                account_name = folders[idx]
                config_file = os.path.join(ACCOUNTS_DIR, account_name, 'config.json')
                config = load_account_config(account_name)

                if not config:
                    print(f"{R}Config invalid!{W}")
                else:
                    if _do_bind_telegram(account_name, config, config_file):
                        print(f"\n{G}✓ SUCCESS!{W}")
                    else:
                        print(f"\n{R}✗ FAILED{W}")
            else:
                print(f"{R}Nomor tidak valid!{W}")
        except ValueError:
            print(f"{R}Input tidak valid!{W}")

        input("\nEnter untuk kembali...")
        return


    print(f"\n{C}Scanning {len(folders)} accounts (parallel)...{W}")

    accounts_with_tg = []
    accounts_no_tg = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for acc in folders:
            config = load_account_config(acc)
            if config:
                futures[executor.submit(_scan_tg_status_single, acc, config)] = acc

        done = 0
        total = len(futures)
        for future in as_completed(futures):
            if STOP_FLAG:
                break
            done += 1
            print(f"\r  Scanning... [{done}/{total}]", end="", flush=True)
            try:
                result = future.result(timeout=20)
                if result['status'] == 'has_tg':
                    accounts_with_tg.append(result)
                else:
                    accounts_no_tg.append(result)
            except:
                accounts_no_tg.append({'account': futures[future], 'balance': 0, 'tg_user': None})

    print(f"\r  Scanning... [{total}/{total}] Done!{' '*20}\n")

    if STOP_FLAG:
        STOP_FLAG = False
        input("\nEnter untuk kembali...")
        return


    print(f"{'Account':<14} | {'Balance':>8} | {'TG Status':<20}")
    print("-" * 50)

    for r in sorted(accounts_with_tg + accounts_no_tg, key=lambda x: int(x['account'].split('_')[1]) if '_' in x['account'] else 0):
        b = r['balance']
        b_color = G if b >= 100 else Y if b >= 50 else W
        if r.get('tg_user'):
            print(f"{r['account']:<14} | {b_color}{b:>6.2f}₽{W} | {G}@{r['tg_user']}{W}")
        else:
            print(f"{r['account']:<14} | {b_color}{b:>6.2f}₽{W} | {R}NO TG{W}")

    if not accounts_no_tg:
        print(f"\n{G}✓ Semua akun sudah punya Telegram!{W}")
        input("\nEnter untuk kembali...")
        return

    print(f"\n{Y}Akun tanpa Telegram ({len(accounts_no_tg)}):{W}\n")
    for i, r in enumerate(accounts_no_tg, 1):
        b_color = G if r['balance'] >= 100 else Y if r['balance'] >= 50 else W
        print(f"  {i}. {r['account']:<14} {b_color}{r['balance']:>6.2f}₽{W}")

    while True:
        print(f"\n{Y}Pilih nomor akun (0 = kembali):{W}")
        choice = input("Pilih: ").strip()

        if choice == '0':
            return

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(accounts_no_tg):
                account_name = accounts_no_tg[idx]['account']
                config_file = os.path.join(ACCOUNTS_DIR, account_name, 'config.json')
                config = load_account_config(account_name)

                if _do_bind_telegram(account_name, config, config_file):
                    print(f"\n{G}✓ SUCCESS!{W}")
                    accounts_no_tg.pop(idx)
                else:
                    print(f"\n{R}✗ FAILED{W}")

                if not accounts_no_tg:
                    print(f"\n{G}✓ Semua akun sudah di-bind!{W}")
                    break

                cont = input("\nBind akun lain? (y/n): ").strip().lower()
                if cont != 'y':
                    break

                print(f"\n{Y}Akun tersisa ({len(accounts_no_tg)}):{W}")
                for i, (acc, bal) in enumerate(accounts_no_tg, 1):
                    b_color = G if bal >= 100 else Y if bal >= 50 else W
                    print(f"  {i}. {acc:<14} {b_color}{bal:>6.2f}₽{W}")
            else:
                print(f"{R}Nomor tidak valid!{W}")
        except ValueError:
            print(f"{R}Input tidak valid!{W}")

    input("\nEnter untuk kembali...")

def manage_accounts():
    """Manage accounts menu"""
    while True:
        show_header()
        print(f"{C}[Kelola Akun]{W}\n")

        folders = show_accounts_list()

        print(f"Menu:")
        print(f"  1. Buat Akun Baru")
        print(f"  2. Edit Akun")
        print(f"  3. Send Akun ke Telegram")
        print(f"  4. Hapus Akun")
        print(f"  5. {C}Import Akun via JSON{W}")
        print(f"  0. Kembali")

        ch = input("\nPilih: ").strip()

        if ch == '0':
            break
        elif ch == '1':
            create_new_account()
        elif ch == '2':
            edit_account()
        elif ch == '3':
            send_account_menu()
        elif ch == '4':
            delete_account()
        elif ch == '5':
            add_account_from_json()


def volet_menu():
    """Volet withdrawal menu"""
    from withdraw_volet import main as volet_withdraw, check_history

    while True:
        print(f"\n{C}{'='*50}{W}")
        print(f"{C}  Volet Withdrawal{W}")
        print(f"{C}{'='*50}{W}")
        print(f"  1. {G}Withdraw ke Volet{W}")
        print(f"  2. {Y}Cek History Withdrawal{W}")
        print(f"  0. Kembali")

        ch = input("\nPilih: ").strip()

        if ch == '0':
            break
        elif ch == '1':
            volet_withdraw()
        elif ch == '2':
            check_history()


def main_menu():
    """Main menu"""
    while True:
        show_header()

        folders = get_account_folders()
        print(f"Total akun: {G}{len(folders)}{W}\n")

        print(f"Menu Utama:")
        print(f"  1. {G}Jalankan Semua Akun (Sequential){W}")
        print(f"  2. {C}Pilih & Jalankan Akun Tertentu{W}")
        print(f"  3. Kelola Akun")
        print(f"  4. {Y}Fetch Balances{W}")
        print(f"  5. {G}Parallel Mode (10 akun sekaligus){W}")
        print(f"  6. {C}Bind Instagram ke Akun{W}")
        print(f"  7. {C}Bind Telegram ke Akun{W}")
        print(f"  8. {Y}Withdraw Volet{W}")
        print(f"  0. Keluar")

        ch = input("\nPilih: ").strip()

        if ch == '0':
            print(f"\n{Y}Bye!{W}")
            break
        elif ch == '1':
            run_all_accounts()
        elif ch == '2':
            run_selected_accounts()
        elif ch == '3':
            manage_accounts()
        elif ch == '4':
            fetch_all_balances()
        elif ch == '5':
            run_parallel_accounts()
        elif ch == '6':
            bind_instagram_to_account()
        elif ch == '7':
            bind_telegram_to_account()
        elif ch == '8':
            volet_menu()

if __name__ == "__main__":

    if not os.path.exists(ACCOUNTS_DIR):
        print(f"{R}Error: Folder '{ACCOUNTS_DIR}' tidak ditemukan!{W}")
        print(f"{Y}Pastikan script dijalankan dari direktori yang benar.{W}")
        sys.exit(1)


    show_startup()

    main_menu()
