#!/usr/bin/env python3
"""
VKSerfing Volet Withdrawal Script
- Check balance semua akun (PARALLEL)
- Withdraw ke Volet wallet untuk balance >= 103₽
- Check withdrawal history
"""

import os
import json
import requests
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

ACCOUNTS_DIR = 'accounts'
MIN_WITHDRAW = 103
VOLET_FEE = 0.03
MAX_WORKERS = 10

G, R, Y, C, W = '\033[92m', '\033[91m', '\033[93m', '\033[96m', '\033[0m'


def get_session(config):
    """Create session with cookies and headers"""
    creds = config.get('credentials', {})
    cookies = creds.get('cookies', {})
    xsrf = creds.get('xsrf_token', '')
    proxy_str = config.get('proxy', {}).get('proxy_string', '')
    ua = config.get('user_agent', {}).get('user_agent', 'Mozilla/5.0 (Linux; Android 11) Chrome/131.0 Mobile Safari/537.36')

    s = requests.Session()
    s.cookies.update(cookies)
    s.headers.update({
        'User-Agent': ua,
        'X-XSRF-Token': xsrf,
        'X-Requested-With': 'XMLHttpRequest',
        'X-Ajax-Html': '1',
        'Accept': 'application/json, text/plain, */*',
    })

    if proxy_str:
        s.proxies = {'http': proxy_str, 'https': proxy_str}

    return s


def get_withdrawal_history(session, domain='https://vkserfing.com'):
    """Get withdrawal history from /cashout"""
    try:
        r = session.get(f'{domain}/cashout', timeout=15)
        if r.status_code == 200:
            html = r.json().get('html', '')
            balance = float(r.json().get('data', {}).get('balance', '0'))


            withdrawals = []

            for match in re.finditer(r'<tr is="cashout-item" :id="(\d+)".*?</tr>', html, re.DOTALL):
                block = match.group(0)
                wd_id = match.group(1)


                wallet_match = re.search(r'word-break-all">([^<]+)</div>', block)
                wallet = wallet_match.group(1) if wallet_match else 'Unknown'


                amount_match = re.search(r'<span class="text-style">(\d+) ₽</span>', block)
                amount = amount_match.group(1) if amount_match else '0'


                date_match = re.search(r'(\d{2}\.\d{2}\.\d{4} в \d{2}:\d{2})', block)
                date = date_match.group(1) if date_match else 'Unknown'


                if 'Не выплачено' in block:
                    status = 'Pending'
                elif 'Выплачено' in block:
                    status = 'Paid'
                else:
                    status = 'Unknown'

                withdrawals.append({
                    'id': wd_id,
                    'wallet': wallet,
                    'amount': amount,
                    'date': date,
                    'status': status
                })

            return balance, withdrawals
    except Exception as e:
        pass
    return 0.0, []


def get_balance(session, domain='https://vkserfing.com'):
    """Get balance from /cashout or /notifications"""
    try:
        r = session.get(f'{domain}/cashout', timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', {})
            balance = data.get('balance', '0')
            return float(balance)
    except:
        pass


    try:
        r = session.get(f'{domain}/notifications', timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', {})
            balance = data.get('balance', '0')
            return float(balance)
    except:
        pass

    return 0.0


def withdraw_volet(session, wallet, amount, domain='https://vkserfing.com'):
    """
    Withdraw to Volet wallet
    wallet format: "U 9148 5460 4126"
    amount: integer (rounded down from balance)
    """
    payload = {
        "bill": wallet,
        "amount": amount,
        "type": "volet"
    }

    try:

        headers = dict(session.headers)
        headers.pop('X-Ajax-Html', None)
        headers['Content-Type'] = 'application/json'

        r = session.post(f'{domain}/cashout', json=payload, headers=headers, timeout=15)


        if 'заблокирован' in r.text.lower() or ('<html' in r.text.lower() and 'blocked' in r.text.lower()):
            return False, 'BANNED', 0


        try:
            data = r.json()
        except:

            print(f"\n{Y}[DEBUG] Raw response: {r.text[:200]}{W}")
            return False, 'Invalid response', 0

        if data.get('status') == 'success':
            msg = data.get('data', {}).get('message', 'Success')
            new_balance = data.get('data', {}).get('balance', '0')
            return True, msg, float(new_balance)
        else:

            error = data.get('message') or data.get('data', {}).get('message', f'Unknown: {str(data)[:100]}')
            return False, error, 0
    except Exception as e:
        return False, f'Exception: {str(e)[:50]}', 0


def get_account_folders():
    """Get all account folders"""
    if not os.path.exists(ACCOUNTS_DIR):
        return []
    folders = []
    for f in os.listdir(ACCOUNTS_DIR):
        if f.startswith('account_') and os.path.isdir(os.path.join(ACCOUNTS_DIR, f)):
            folders.append(f)

    folders.sort(key=lambda x: int(x.split('_')[1]) if x.split('_')[1].isdigit() else 0)
    return folders


def input_wallets():
    """Input Volet wallets"""
    print(f"\n{C}=== Input Volet Wallets ==={W}")
    print(f"Format: U XXXX XXXX XXXX")
    print(f"Enter one wallet per line, empty line to finish")
    print(f"Or paste multiple wallets at once\n")

    wallets = []
    while True:
        try:
            line = input(f"{Y}Wallet [{len(wallets)+1}]: {W}").strip()
            if not line:
                if wallets:
                    break
                print(f"{R}Enter at least one wallet{W}")
                continue


            if re.match(r'^U\s*\d{4}\s*\d{4}\s*\d{4}$', line):

                nums = re.findall(r'\d{4}', line)
                wallet = f"U {nums[0]} {nums[1]} {nums[2]}"
                wallets.append(wallet)
                print(f"{G}  ✓ Added: {wallet}{W}")
            else:
                print(f"{R}  ✗ Invalid format. Use: U XXXX XXXX XXXX{W}")
        except EOFError:
            break
        except KeyboardInterrupt:
            print(f"\n{Y}Cancelled{W}")
            return []

    return wallets


def main():
    print(f"\n{C}{'='*60}{W}")
    print(f"{C}  VKSerfing Volet Withdrawal Tool{W}")
    print(f"{C}{'='*60}{W}")


    wallets = input_wallets()
    if not wallets:
        print(f"{R}No wallets provided. Exiting.{W}")
        return

    print(f"\n{G}Wallets to use ({len(wallets)}):{W}")
    for i, w in enumerate(wallets, 1):
        print(f"  {i}. {w}")


    folders = get_account_folders()
    if not folders:
        print(f"{R}No accounts found in {ACCOUNTS_DIR}/{W}")
        return

    print(f"\n{C}Checking {len(folders)} accounts (parallel)...{W}\n")


    def check_balance_single(folder):
        config_path = os.path.join(ACCOUNTS_DIR, folder, 'config.json')
        if not os.path.exists(config_path):
            return {'folder': folder, 'status': 'error', 'error': 'no config'}
        try:
            with open(config_path) as f:
                config = json.load(f)
            session = get_session(config)
            balance = get_balance(session)
            return {'folder': folder, 'balance': balance, 'config': config, 'status': 'ok'}
        except Exception as e:
            return {'folder': folder, 'status': 'error', 'error': str(e)[:30]}

    eligible = []
    results = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_balance_single, f): f for f in folders}
        done = 0
        total = len(futures)

        for future in as_completed(futures):
            done += 1
            print(f"\r  Scanning... [{done}/{total}]", end="", flush=True)
            try:
                result = future.result(timeout=20)
                results.append(result)
            except:
                results.append({'folder': futures[future], 'status': 'error', 'error': 'timeout'})

    print(f"\r  Scanning... [{total}/{total}] Done!{' '*20}\n")


    for r in sorted(results, key=lambda x: int(x['folder'].split('_')[1]) if '_' in x['folder'] else 0):
        if r['status'] == 'error':
            print(f"  {r['folder']}: {R}Error - {r.get('error', 'unknown')}{W}")
        else:
            balance = r['balance']
            if balance >= MIN_WITHDRAW:
                eligible.append(r)
                print(f"  {r['folder']}: {balance:.2f}₽ {G}✓ ELIGIBLE{W}")
            else:
                print(f"  {r['folder']}: {balance:.2f}₽ {Y}skip{W}")

    if not eligible:
        print(f"\n{Y}No accounts with balance >= {MIN_WITHDRAW}₽{W}")
        return


    total_balance = sum(a['balance'] for a in eligible)
    total_withdraw = sum(int(a['balance']) for a in eligible)
    total_receive = total_withdraw * (1 - VOLET_FEE)

    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Eligible accounts: {len(eligible)}{W}")
    print(f"{G}Total balance: {total_balance:.2f}₽{W}")
    print(f"{G}Total to withdraw: {total_withdraw}₽{W}")
    print(f"{G}After 3% fee: ~{total_receive:.2f}₽{W}")
    print(f"{C}{'='*60}{W}")


    confirm = input(f"\n{Y}Proceed with withdrawal? (yes/no): {W}").strip().lower()
    if confirm not in ['yes', 'y']:
        print(f"{Y}Cancelled{W}")
        return


    print(f"\n{C}Processing withdrawals...{W}\n")

    wallet_idx = 0
    success_count = 0
    total_withdrawn = 0

    for acc in eligible:
        folder = acc['folder']
        config = acc['config']


        wallet = wallets[wallet_idx % len(wallets)]
        wallet_idx += 1

        try:
            session = get_session(config)


            balance = get_balance(session)
            if balance < MIN_WITHDRAW:
                print(f"  {folder}: {balance:.2f}₽ {Y}skip (below min){W}")
                continue

            amount = int(balance)
            print(f"  {folder}: {balance:.2f}₽ → {amount}₽ to {wallet}...", end=" ", flush=True)

            success, msg, _ = withdraw_volet(session, wallet, amount)

            if success:
                print(f"{G}✓ {msg}{W}")

                import time
                time.sleep(5)
                new_balance = get_balance(session)
                print(f"       → Remaining: {new_balance:.2f}₽")
                success_count += 1
                total_withdrawn += amount
            else:
                print(f"{R}✗ {msg}{W}")
        except Exception as e:
            print(f"{R}✗ Error: {str(e)[:30]}{W}")


    print(f"\n{C}{'='*60}{W}")
    print(f"{G}Completed: {success_count}/{len(eligible)} accounts{W}")
    print(f"{G}Total withdrawn: {total_withdrawn}₽{W}")
    print(f"{G}Expected receive: ~{total_withdrawn * (1 - VOLET_FEE):.2f}₽{W}")
    print(f"{C}{'='*60}{W}")


def check_history():
    """Check withdrawal history for all accounts (PARALLEL)"""
    print(f"\n{C}{'='*60}{W}")
    print(f"{C}  Withdrawal History Check{W}")
    print(f"{C}{'='*60}{W}")

    folders = get_account_folders()
    if not folders:
        print(f"{R}No accounts found{W}")
        return

    print(f"\n{C}Checking {len(folders)} accounts (parallel)...{W}\n")

    def check_history_single(folder):
        config_path = os.path.join(ACCOUNTS_DIR, folder, 'config.json')
        if not os.path.exists(config_path):
            return {'folder': folder, 'status': 'error'}
        try:
            with open(config_path) as f:
                config = json.load(f)
            session = get_session(config)
            balance, withdrawals = get_withdrawal_history(session)
            pending = [w for w in withdrawals if w['status'] == 'Pending']
            return {'folder': folder, 'balance': balance, 'pending': pending, 'status': 'ok'}
        except:
            return {'folder': folder, 'status': 'error'}

    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(check_history_single, f): f for f in folders}
        done = 0
        total = len(futures)

        for future in as_completed(futures):
            done += 1
            print(f"\r  Scanning... [{done}/{total}]", end="", flush=True)
            try:
                results.append(future.result(timeout=20))
            except:
                results.append({'folder': futures[future], 'status': 'error'})

    print(f"\r  Scanning... [{total}/{total}] Done!{' '*20}\n")

    total_pending = 0
    total_pending_amount = 0

    for r in sorted(results, key=lambda x: int(x['folder'].split('_')[1]) if '_' in x['folder'] else 0):
        if r['status'] == 'error':
            continue

        if r.get('pending'):
            print(f"{Y}{r['folder']}{W} (balance: {r['balance']:.2f}₽)")
            for w in r['pending']:
                print(f"  └─ #{w['id']}: {w['amount']}₽ → {w['wallet']} | {w['date']} | {R}{w['status']}{W}")
                total_pending += 1
                total_pending_amount += int(w['amount'])
        elif r.get('balance', 0) > 0:
            print(f"  {r['folder']}: {r['balance']:.2f}₽ (no pending)")

    print(f"\n{C}{'='*60}{W}")
    print(f"{Y}Total pending withdrawals: {total_pending}{W}")
    print(f"{Y}Total pending amount: {total_pending_amount}₽{W}")
    print(f"{C}{'='*60}{W}")


def show_menu():
    """Show main menu"""
    print(f"\n{C}{'='*60}{W}")
    print(f"{C}  VKSerfing Volet Tool{W}")
    print(f"{C}{'='*60}{W}")
    print(f"  1. Withdraw to Volet")
    print(f"  2. Check withdrawal history")
    print(f"  0. Exit")
    print(f"{C}{'='*60}{W}")
    return input(f"{Y}Select option: {W}").strip()


if __name__ == '__main__':
    while True:
        choice = show_menu()
        if choice == '1':
            main()
        elif choice == '2':
            check_history()
        elif choice == '0':
            print(f"{G}Bye!{W}")
            break
        else:
            print(f"{R}Invalid option{W}")
