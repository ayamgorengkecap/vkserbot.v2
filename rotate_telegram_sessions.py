#!/usr/bin/env python3
"""
Auto-rotate Telegram sessions from sessions folder when invalid
"""

import os
import json
import glob
import random
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# Paths
SESSIONS_DIR = "/root/vkserbot.v2/sessions"
ACCOUNTS_DIR = "/root/vkserbot.v2/accounts"

# Telegram API credentials
API_ID = 1724399
API_HASH = "7f6c4af5220db320413ff672093ee102"

def get_available_sessions():
    """Get all .session files from sessions folder"""
    pattern = os.path.join(SESSIONS_DIR, "*.session")
    sessions = glob.glob(pattern)
    return [s for s in sessions if os.path.isfile(s)]

def session_to_string(session_file):
    """Convert .session file to string session"""
    try:
        # Extract phone from filename
        phone = os.path.basename(session_file).replace('.session', '')
        
        # Load session
        client = TelegramClient(session_file, API_ID, API_HASH)
        client.connect()
        
        if not client.is_user_authorized():
            client.disconnect()
            return None, None, "Not authorized"
        
        # Get user info
        me = client.get_me()
        
        # Convert to string session
        string_session = StringSession.save(client.session)
        
        client.disconnect()
        
        return string_session, {
            'user_id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'phone': phone
        }, None
        
    except Exception as e:
        return None, None, str(e)

def rotate_telegram_session(account_name, exclude_phones=None):
    """
    Rotate to new Telegram session for account
    
    Args:
        account_name: Account folder name
        exclude_phones: List of phone numbers to exclude (already used/invalid)
    
    Returns:
        True if success, False if failed
    """
    exclude_phones = exclude_phones or []
    
    # Get available sessions
    available = get_available_sessions()
    
    if not available:
        print(f"❌ No sessions available in {SESSIONS_DIR}")
        return False
    
    # Filter out excluded phones
    available = [s for s in available if os.path.basename(s).replace('.session', '') not in exclude_phones]
    
    if not available:
        print(f"❌ No unused sessions available")
        return False
    
    # Random pick
    session_file = random.choice(available)
    phone = os.path.basename(session_file).replace('.session', '')
    
    print(f"🔄 Rotating to session: {phone}")
    
    # Convert to string session
    string_session, user_info, error = session_to_string(session_file)
    
    if error:
        print(f"❌ Session {phone} invalid: {error}")
        # Recursive retry with exclusion
        return rotate_telegram_session(account_name, exclude_phones + [phone])
    
    # Update account config
    config_path = os.path.join(ACCOUNTS_DIR, account_name, "config.json")
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        config['telegram'] = {
            'bound': True,
            'api_id': API_ID,
            'api_hash': API_HASH,
            'phone': user_info['phone'],
            'session_string': string_session,
            'user_id': user_info['user_id'],
            'username': user_info['username'],
            'first_name': user_info['first_name']
        }
        
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Session rotated: @{user_info['username']} ({user_info['phone']})")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update config: {e}")
        return False

def scan_and_rotate_invalid():
    """Scan all accounts and rotate invalid TG sessions"""
    accounts = [d for d in os.listdir(ACCOUNTS_DIR) if os.path.isdir(os.path.join(ACCOUNTS_DIR, d))]
    
    print(f"📊 Scanning {len(accounts)} accounts...\n")
    
    rotated = 0
    skipped = 0
    
    for account in accounts:
        config_path = os.path.join(ACCOUNTS_DIR, account, "config.json")
        
        if not os.path.exists(config_path):
            continue
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            tg = config.get('telegram', {})
            
            # Skip if no TG session
            if not tg.get('session_string'):
                skipped += 1
                continue
            
            # Test session validity
            session_string = tg['session_string']
            
            try:
                client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
                client.connect()
                
                if client.is_user_authorized():
                    me = client.get_me()
                    print(f"✅ {account}: @{me.username} - Valid")
                    client.disconnect()
                    continue
                else:
                    print(f"⚠️  {account}: Session not authorized - Rotating...")
                    client.disconnect()
                    
            except Exception as e:
                print(f"❌ {account}: Session invalid ({str(e)[:50]}) - Rotating...")
            
            # Rotate session
            if rotate_telegram_session(account):
                rotated += 1
            
        except Exception as e:
            print(f"❌ {account}: Error - {e}")
    
    print(f"\n📊 Summary:")
    print(f"  Rotated: {rotated}")
    print(f"  Skipped (no TG): {skipped}")
    print(f"  Valid: {len(accounts) - rotated - skipped}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Rotate specific account
        account_name = sys.argv[1]
        rotate_telegram_session(account_name)
    else:
        # Scan all accounts
        scan_and_rotate_invalid()
