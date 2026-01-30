#!/usr/bin/env python3
"""
Copy Telegram session files from /root/telegram/sessions/ to account folders
Based on phone number matching
"""

import os
import json
import shutil

TELEGRAM_SESSIONS_DIR = "/root/telegram/sessions"
ACCOUNTS_DIR = "accounts"

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def main():
    print(f"{C}{'='*60}{W}")
    print(f"{C}Copy Telegram Sessions to Account Folders{W}")
    print(f"{C}{'='*60}{W}\n")
    
    if not os.path.exists(TELEGRAM_SESSIONS_DIR):
        print(f"{R}❌ Telegram sessions folder not found: {TELEGRAM_SESSIONS_DIR}{W}")
        return
    
    # Get all session files
    session_files = [f for f in os.listdir(TELEGRAM_SESSIONS_DIR) if f.endswith('.session')]
    
    if not session_files:
        print(f"{Y}No session files found in {TELEGRAM_SESSIONS_DIR}{W}")
        return
    
    print(f"{C}Found {len(session_files)} session files{W}\n")
    
    # Get all accounts
    accounts = sorted([d for d in os.listdir(ACCOUNTS_DIR) 
                      if os.path.isdir(os.path.join(ACCOUNTS_DIR, d)) and d.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    # Build phone -> account mapping
    phone_to_account = {}
    
    for acc in accounts:
        config_file = os.path.join(ACCOUNTS_DIR, acc, 'config.json')
        if not os.path.exists(config_file):
            continue
        
        try:
            with open(config_file) as f:
                config = json.load(f)
            
            phone = config.get('telegram', {}).get('phone')
            if phone:
                phone_to_account[phone] = acc
        except:
            continue
    
    print(f"{C}Found {len(phone_to_account)} accounts with phone numbers{W}\n")
    
    # Match and copy
    copied = 0
    not_found = 0
    
    for session_file in session_files:
        # Extract phone from filename (remove .session)
        phone = session_file.replace('.session', '')
        
        if phone in phone_to_account:
            account = phone_to_account[phone]
            src = os.path.join(TELEGRAM_SESSIONS_DIR, session_file)
            dst = os.path.join(ACCOUNTS_DIR, account, f'telegram_{account}.session')
            
            try:
                shutil.copy2(src, dst)
                print(f"{G}✓{W} {phone:<20} → {account}")
                copied += 1
            except Exception as e:
                print(f"{R}✗{W} {phone:<20} → {account} (Error: {e})")
        else:
            print(f"{Y}⚠{W} {phone:<20} → No matching account")
            not_found += 1
    
    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Copied: {copied}{W} | {Y}Not found: {not_found}{W}")
    print(f"{C}{'='*60}{W}\n")
    
    if copied > 0:
        print(f"{C}Next step: Run bind_telegram_session.py mode 3 (Auto-rebind){W}")

if __name__ == '__main__':
    main()
