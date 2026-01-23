#!/usr/bin/env python3
"""
Match and copy Telegram session files based on web username
"""

import os
import json
import glob
import shutil
from telethon.sync import TelegramClient

# Paths
SESSIONS_DIR = "/root/vkserbot.v2/sessions"
ACCOUNTS_DIR = "/root/vkserbot.v2/accounts"

# Telegram API credentials
API_ID = 1724399
API_HASH = "7f6c4af5220db320413ff672093ee102"

def get_session_username(session_file):
    """Get username from session file"""
    try:
        client = TelegramClient(session_file, API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            client.disconnect()
            return None
        
        me = client.get_me()
        username = me.username
        
        client.disconnect()
        return username
        
    except Exception as e:
        return None

def get_web_telegram_username(config):
    """Get Telegram username from VKSerfing web using /settings endpoint"""
    try:
        import requests
        import re
        import html
        
        cookies = config.get('credentials', {}).get('cookies', {})
        proxy_str = config.get('proxy', {}).get('proxy_string')
        
        session = requests.Session()
        
        if proxy_str:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                proxy_url = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                session.proxies = {'http': proxy_url, 'https': proxy_url}
        
        session.cookies.update(cookies)
        
        # Fetch /settings page
        resp = session.get('https://vkserfing.ru/settings', timeout=15)
        
        if resp.status_code != 200:
            return None
        
        html_content = resp.text
        
        # Parse Telegram username from data-alias
        tg_options = re.findall(r'<option[^>]*data-(?:platform|icon)="telegram"[^>]*>', html_content)
        if tg_options:
            alias_match = re.search(r'data-alias="@?([^"]+)"', tg_options[0])
            if alias_match:
                return alias_match.group(1)
        
        return None
        
    except Exception as e:
        return None

def match_and_copy_session(account_name):
    """Match session file with web username and copy to account folder"""
    
    config_path = os.path.join(ACCOUNTS_DIR, account_name, "config.json")
    
    if not os.path.exists(config_path):
        print(f"❌ {account_name}: Config not found")
        return False
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"❌ {account_name}: Failed to load config - {e}")
        return False
    
    # Get web username
    web_username = get_web_telegram_username(config)
    
    if not web_username:
        print(f"⚠️  {account_name}: No Telegram on web")
        return None
    
    print(f"🔍 {account_name}: Web username = @{web_username}")
    
    # Find matching session file
    session_files = glob.glob(os.path.join(SESSIONS_DIR, "*.session"))
    
    for session_file in session_files:
        session_username = get_session_username(session_file)
        
        if session_username and session_username.lower() == web_username.lower():
            print(f"✅ {account_name}: Match found - {os.path.basename(session_file)}")
            
            # Copy session file to account folder
            dest_file = os.path.join(ACCOUNTS_DIR, account_name, "telegram.session")
            
            try:
                shutil.copy2(session_file, dest_file)
                print(f"📁 {account_name}: Session copied to telegram.session")
                
                # Update config to use session file
                config['telegram'] = {
                    'bound': True,
                    'api_id': API_ID,
                    'api_hash': API_HASH,
                    'session_file': 'telegram.session',
                    'username': session_username
                }
                
                with open(config_path, 'w') as f:
                    json.dump(config, f, indent=2)
                
                print(f"✅ {account_name}: Config updated\n")
                return True
                
            except Exception as e:
                print(f"❌ {account_name}: Failed to copy - {e}\n")
                return False
    
    print(f"❌ {account_name}: No matching session found\n")
    return False

def scan_all_accounts():
    """Scan all accounts and match sessions"""
    accounts = [d for d in os.listdir(ACCOUNTS_DIR) if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))]
    
    print(f"📊 Scanning {len(accounts)} accounts...\n")
    
    matched = 0
    skipped = 0
    failed = 0
    
    for account in sorted(accounts):
        result = match_and_copy_session(account)
        
        if result is True:
            matched += 1
        elif result is False:
            failed += 1
        else:
            skipped += 1
    
    print(f"\n📊 Summary:")
    print(f"  ✅ Matched: {matched}")
    print(f"  ❌ Failed: {failed}")
    print(f"  ⚠️  Skipped: {skipped}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Match specific account
        account_name = sys.argv[1]
        match_and_copy_session(account_name)
    else:
        # Scan all accounts
        scan_all_accounts()
