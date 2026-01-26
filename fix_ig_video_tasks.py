#!/usr/bin/env python3
"""
Auto-enable Instagram video/story tasks untuk semua akun
Tasks ini tidak butuh login, jadi bisa dijalankan tanpa IG session
"""

import json
import os

ACCOUNTS_DIR = 'accounts'

G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

def fix_account(account_name):
    """Enable IG video tasks, disable action tasks if no session"""
    config_path = os.path.join(ACCOUNTS_DIR, account_name, 'config.json')
    
    if not os.path.exists(config_path):
        return False, "No config"
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Check if IG session exists
        has_ig_session = config.get('instagram', {}).get('enabled', False)
        
        # Get or create task_types
        if 'task_types' not in config:
            config['task_types'] = {}
        
        task_types = config['task_types']
        
        # Always enable video/story tasks (no login needed)
        task_types['instagram_video'] = True
        task_types['instagram_views'] = True
        task_types['instagram_story'] = True
        
        # Action tasks only if has session
        if has_ig_session:
            # Keep existing settings or default to True
            if 'instagram_followers' not in task_types:
                task_types['instagram_followers'] = True
            if 'instagram_likes' not in task_types:
                task_types['instagram_likes'] = True
            if 'instagram_comments' not in task_types:
                task_types['instagram_comments'] = True
            status = "IG session + video tasks"
        else:
            # Disable action tasks
            task_types['instagram_followers'] = False
            task_types['instagram_likes'] = False
            task_types['instagram_comments'] = False
            status = "Video tasks only (no session)"
        
        # Save
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        return True, status
        
    except Exception as e:
        return False, str(e)

def main():
    folders = sorted([f for f in os.listdir(ACCOUNTS_DIR) 
                     if os.path.isdir(os.path.join(ACCOUNTS_DIR, f)) and f.startswith('account_')],
                     key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0)
    
    print(f"{C}Fixing {len(folders)} accounts...{W}\n")
    
    success = 0
    failed = 0
    
    for acc in folders:
        ok, status = fix_account(acc)
        if ok:
            print(f"{G}✓{W} {acc:<15} - {status}")
            success += 1
        else:
            print(f"{R}✗{W} {acc:<15} - {status}")
            failed += 1
    
    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Success: {success}{W} | {R}Failed: {failed}{W}")
    print(f"{C}{'='*60}{W}")

if __name__ == '__main__':
    main()
