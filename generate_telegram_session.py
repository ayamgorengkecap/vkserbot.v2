#!/usr/bin/env python3
"""
Generate Telegram session dan bind ke account config
"""

import json
import os
import sys

ACCOUNTS_DIR = 'accounts'
DEFAULT_API_ID = 1724399
DEFAULT_API_HASH = '7f6c4af5220db320413ff672093ee102'

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def generate_and_bind_session(account_folder, phone):
    """Generate Telegram session dan bind ke config"""
    
    config_path = os.path.join(ACCOUNTS_DIR, account_folder, 'config.json')
    
    if not os.path.exists(config_path):
        print(f"{R}❌ Config tidak ditemukan: {config_path}{W}")
        return False
    
    try:
        # Import Telethon
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
        from telethon.errors import SessionPasswordNeededError
        
        print(f"\n{C}Generating session untuk {phone}...{W}")
        
        # Create client with StringSession
        client = TelegramClient(StringSession(), DEFAULT_API_ID, DEFAULT_API_HASH)
        
        client.connect()
        
        if not client.is_user_authorized():
            print(f"{Y}Mengirim kode ke {phone}...{W}")
            client.send_code_request(phone)
            
            code = input(f"{C}Masukkan kode OTP: {W}").strip()
            
            try:
                client.sign_in(phone, code)
            except SessionPasswordNeededError:
                password = input(f"{Y}Masukkan 2FA Password: {W}").strip()
                client.sign_in(password=password)
        
        # Get user info
        me = client.get_me()
        session_string = client.session.save()
        
        print(f"\n{G}✓ Login berhasil!{W}")
        print(f"  User: {me.first_name} (@{me.username})")
        print(f"  ID: {me.id}")
        
        # Load config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Add telegram config
        config['telegram'] = {
            'api_id': DEFAULT_API_ID,
            'api_hash': DEFAULT_API_HASH,
            'phone': phone,
            'session_string': session_string,
            'user_id': me.id,
            'username': me.username or '',
            'first_name': me.first_name or ''
        }
        
        # Enable telegram tasks
        if 'task_types' not in config:
            config['task_types'] = {}
        config['task_types']['telegram_followers'] = True
        config['task_types']['telegram_views'] = True
        
        # Save config
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
        return False

def main():
    print("=" * 60)
    print("GENERATE & BIND TELEGRAM SESSION")
    print("=" * 60)
    
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

if __name__ == '__main__':
    main()
