#!/usr/bin/env python3
"""
Validate all Telegram sessions and auto-rebind if invalid
"""

import os
import json
import sys

ACCOUNTS_DIR = 'accounts'
G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

sys.path.insert(0, 'lib')

def validate_and_rebind():
    """Validate all telegram sessions and rebind if needed"""
    
    print(f"{C}{'='*60}{W}")
    print(f"{C}Validate & Auto-Rebind Telegram Sessions{W}")
    print(f"{C}{'='*60}{W}\n")
    
    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
    except ImportError:
        print(f"{R}❌ Telethon not installed{W}")
        return
    
    accounts = sorted([d for d in os.listdir(ACCOUNTS_DIR) 
                      if os.path.isdir(os.path.join(ACCOUNTS_DIR, d)) and d.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    print(f"{C}Checking {len(accounts)} accounts...{W}\n")
    
    valid = 0
    invalid = 0
    rebinded = 0
    no_session = 0
    
    for acc in accounts:
        config_file = os.path.join(ACCOUNTS_DIR, acc, 'config.json')
        
        if not os.path.exists(config_file):
            continue
        
        try:
            with open(config_file) as f:
                config = json.load(f)
        except:
            continue
        
        tg_config = config.get('telegram', {})
        session_string = tg_config.get('session_string')
        
        if not session_string or session_string == 'null':
            no_session += 1
            continue
        
        # Validate session string
        api_id = int(tg_config.get('api_id', 1724399))
        api_hash = tg_config.get('api_hash', '7f6c4af5220db320413ff672093ee102')
        
        try:
            client = TelegramClient(StringSession(session_string), api_id, api_hash)
            client.connect()
            
            if client.is_user_authorized():
                print(f"{G}✓{W} {acc:<15} - Session valid")
                valid += 1
                client.disconnect()
            else:
                print(f"{R}✗{W} {acc:<15} - Session invalid/expired")
                invalid += 1
                client.disconnect()
                
                # Try to rebind from session file
                session_file = os.path.join(ACCOUNTS_DIR, acc, f'telegram_{acc}.session')
                
                if os.path.exists(session_file):
                    print(f"  {Y}→ Found session file, attempting rebind...{W}")
                    
                    try:
                        # Load from session file
                        session_name = session_file.replace('.session', '')
                        file_client = TelegramClient(session_name, api_id, api_hash)
                        file_client.connect()
                        
                        if file_client.is_user_authorized():
                            # Convert to string session
                            new_session_string = file_client.session.save()
                            me = file_client.get_me()
                            
                            # Update config
                            config['telegram']['session_string'] = new_session_string
                            config['telegram']['user_id'] = me.id
                            config['telegram']['username'] = me.username or ''
                            config['telegram']['first_name'] = me.first_name or ''
                            
                            with open(config_file, 'w') as f:
                                json.dump(config, f, indent=2)
                            
                            print(f"  {G}✓ Rebinded successfully (@{me.username}){W}")
                            rebinded += 1
                            
                            file_client.disconnect()
                        else:
                            print(f"  {R}✗ Session file also invalid{W}")
                            file_client.disconnect()
                    
                    except Exception as e:
                        print(f"  {R}✗ Rebind failed: {str(e)[:50]}{W}")
                else:
                    print(f"  {Y}→ No session file found for rebind{W}")
        
        except Exception as e:
            print(f"{R}✗{W} {acc:<15} - Error: {str(e)[:50]}")
            invalid += 1
    
    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Valid: {valid}{W} | {R}Invalid: {invalid}{W} | {C}Rebinded: {rebinded}{W} | {Y}No session: {no_session}{W}")
    print(f"{C}{'='*60}{W}")

if __name__ == '__main__':
    validate_and_rebind()
