#!/usr/bin/env python3
"""
Fast balance fetcher - NO IG login, cookies + proxy only
Parses email and IG from /settings HTML response
"""
import os, json, re, html, requests, concurrent.futures


G, Y, R, C, W = '\033[92m', '\033[93m', '\033[91m', '\033[96m', '\033[0m'

ACCOUNTS_DIR = "accounts"
TIMEOUT = 10
MAX_WORKERS = 10

def parse_settings_html(html_content):
    """Parse email, Instagram, and Telegram from /settings HTML response"""
    email = None
    ig_username = None
    tg_username = None



    init_match = re.search(r':init-data="([^"]+)"', html_content)
    if init_match:
        try:
            init_str = html.unescape(init_match.group(1))
            init_data = json.loads(init_str)
            email = init_data.get('email')
        except:
            pass



    ig_options = re.findall(r'<option[^>]*data-(?:platform|icon)="instagram"[^>]*>', html_content)
    if ig_options:

        alias_match = re.search(r'data-alias="@?([^"]+)"', ig_options[0])
        if alias_match:
            ig_username = alias_match.group(1)



    tg_options = re.findall(r'<option[^>]*data-(?:platform|icon)="telegram"[^>]*>', html_content)
    if tg_options:

        alias_match = re.search(r'data-alias="@?([^"]+)"', tg_options[0])
        if alias_match:
            tg_username = alias_match.group(1)

    return email, ig_username, tg_username

def fetch_balance(acc_name):
    """Fetch balance, email, and IG for single account"""
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

    balance = 0.0
    email = None
    ig_username = None
    tg_username = None
    proxy_failed = False

    for domain in ['https://vkserfing.com', 'https://vkserfing.ru']:
        try:

            resp = requests.get(f'{domain}/cashout', headers=headers, cookies=cookies, proxies=proxies, timeout=TIMEOUT)
            if resp.status_code == 200:
                try:
                    html_content = resp.json().get('html', '')
                    m = re.search(r'<span>([0-9.]+)</span>', html_content)
                    if m:
                        balance = float(m.group(1))
                except:
                    pass


            resp2 = requests.get(f'{domain}/settings', headers=headers, cookies=cookies, proxies=proxies, timeout=TIMEOUT)
            if resp2.status_code == 200:
                try:
                    html_content = resp2.json().get('html', '')
                    email, ig_username, tg_username = parse_settings_html(html_content)
                except:
                    pass

            break

        except (requests.exceptions.ProxyError, requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            proxy_failed = True
            continue
        except:
            continue


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
        'balance': balance,
        'email': email or '-',
        'ig_username': ig_username,
        'tg_username': tg_username,
        'proxy_failed': proxy_failed
    }

def main():
    if not os.path.isdir(ACCOUNTS_DIR):
        print(f"{R}No accounts directory!{W}")
        return

    accounts = sorted(
        [f for f in os.listdir(ACCOUNTS_DIR) if f.startswith('account_')],
        key=lambda x: int(x.split('_')[1]) if '_' in x and x.split('_')[1].isdigit() else 0
    )

    if not accounts:
        print(f"{R}No accounts found!{W}")
        return

    print(f"Fetching {len(accounts)} accounts (parallel: {MAX_WORKERS})...\n")
    print(f"{'Account':<15} | {'Balance':>10} | {'IG':<20} | {'Email':<30}")
    print("-" * 85)

    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_acc = {executor.submit(fetch_balance, acc): acc for acc in accounts}

        for future in concurrent.futures.as_completed(future_to_acc):
            r = future.result()

            if 'error' in r:
                print(f"[✗] {r['account']:<12} | {R}{'ERROR':<8}{W} | {r['error']}")
                continue

            results.append(r)

            b = r['balance']
            color, mark = (G, '✓') if b >= 100 else (Y, '●') if b >= 50 else (W, ' ')
            ig_display = f"@{r['ig_user']}" if r['ig_user'] else '-'
            proxy_mark = f" {R}[P]{W}" if r.get('proxy_failed') else ""

            print(f"[{mark}] {r['account']:<12} | {color}{b:>8.2f}₽{W} | {C}{ig_display:<20}{W} | {r['email']:<30}{proxy_mark}")


    print("\n" + "=" * 85)
    print("SUMMARY (50+₽):")
    print("=" * 85)

    for r in sorted(results, key=lambda x: -x['balance']):
        if r['balance'] < 50:
            continue
        color = G if r['balance'] >= 100 else Y
        ig_display = f"@{r['ig_user']}" if r['ig_user'] else '-'
        print(f"  {r['account']:<15} | {color}{r['balance']:>8.2f}₽{W} | {C}{ig_display:<20}{W} | {r['email']}")


    with_ig = len([r for r in results if r['ig_user']])
    without_ig = len([r for r in results if not r['ig_user']])
    proxy_failed = len([r for r in results if r.get('proxy_failed')])

    print(f"\n{G}100+₽:{W} {len([r for r in results if r['balance'] >= 100])} accounts")
    print(f"{Y}50-99₽:{W} {len([r for r in results if 50 <= r['balance'] < 100])} accounts")
    print(f"{C}With IG:{W} {with_ig} | {R}Without IG:{W} {without_ig}")
    if proxy_failed:
        print(f"{R}Proxy failed:{W} {proxy_failed} accounts")
    print(f"Total: {sum(r['balance'] for r in results):.2f}₽")

if __name__ == "__main__":
    main()
