#!/usr/bin/env python3
"""
Instagram Binding - Bind IG to existing VKS account
Flow: Load VKS cookies → Login IG → Setup profile → Bind IG to VKS
"""

import os
import sys
import io
import json
import glob
import random
import time
import re
import uuid
import requests
from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    TwoFactorRequired,
    BadPassword,
    LoginRequired,
    PleaseWaitFewMinutes,
    RecaptchaRequired
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ACCOUNTS_DIR = os.path.join(SCRIPT_DIR, "accounts")
IG_DOWNLOADS_DIR = os.path.join(SCRIPT_DIR, "ig_downloads")

REF_CODE = "551134276"
BASE_URL = "https://vkserfing.ru"

COUNTRIES = ["1", "4", "50", "81", "98", "100", "102", "112", "123", "138", "145", "161", "182"]

def retry(func, retries=3, delay_range=(2, 4), silent=False):
    """Retry wrapper for any function"""
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            if attempt < retries - 1:
                if not silent:
                    print(f"   ⚠️ Retry {attempt+1}/{retries}: {str(e)[:40]}")
                time.sleep(random.uniform(*delay_range))
            else:
                raise


DEVICES = [
    {"manufacturer": "Samsung", "model": "Galaxy S24 Ultra", "device": "SM-S928B", "cpu": "sm8650", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1440x3120"},
    {"manufacturer": "Samsung", "model": "Galaxy S23 Ultra", "device": "SM-S918B", "cpu": "sm8550", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1440x3088"},
    {"manufacturer": "Xiaomi", "model": "14 Ultra", "device": "aurora", "cpu": "sm8650", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1440x3200"},
    {"manufacturer": "Xiaomi", "model": "Redmi Note 13 Pro", "device": "emerald", "cpu": "sm7435", "android": 34, "release": "14.0", "dpi": "440dpi", "resolution": "1220x2712"},
    {"manufacturer": "OPPO", "model": "Find X7 Ultra", "device": "CPH2571", "cpu": "sm8650", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1440x3168"},
    {"manufacturer": "Google", "model": "Pixel 8 Pro", "device": "husky", "cpu": "gs301", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1344x2992"},
    {"manufacturer": "OnePlus", "model": "12", "device": "CPH2573", "cpu": "sm8650", "android": 34, "release": "14.0", "dpi": "480dpi", "resolution": "1440x3168"},
]

APP_VERSIONS = [
    ("358.0.0.46.83", "618574860"),
    ("357.0.0.33.97", "617574860"),
    ("356.0.0.35.90", "616574860"),
]

USER_AGENTS = [
    "Mozilla/5.0 (Linux; Android 14; SM-S928B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
]

def delay(min_s=1, max_s=3, msg=""):
    d = random.uniform(min_s, max_s)
    if msg:
        print(f"   ⏳ {msg} ({d:.1f}s)")
    time.sleep(d)


def list_accounts():
    """List accounts without IG session"""
    if not os.path.exists(ACCOUNTS_DIR):
        return []

    accounts = []
    for folder in os.listdir(ACCOUNTS_DIR):
        if folder.startswith('account_'):
            has_ig = len(glob.glob(os.path.join(ACCOUNTS_DIR, folder, "ig_session_*.json"))) > 0
            if not has_ig:
                accounts.append(folder)

    accounts.sort(key=lambda x: int(x.split('_')[1]))
    return accounts

def load_config(account_name):
    path = os.path.join(ACCOUNTS_DIR, account_name, "config.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None

def save_config(account_name, config):
    path = os.path.join(ACCOUNTS_DIR, account_name, "config.json")
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)


def login_vks_with_cookie(config):
    """Login VKSerfing using existing cookies + proxy from config"""
    print(f"\n{'='*50}")
    print(f"🔐 STEP 1: Login VKSerfing (via Cookie)")
    print(f"{'='*50}")

    creds = config.get('credentials', {})
    cookies = creds.get('cookies', {})
    xsrf = creds.get('xsrf_token', '')
    proxy_info = config.get('proxy', {})

    if not cookies.get('vkstoken'):
        print(f"   ❌ No vkstoken in config!")
        return None, None, None

    session = requests.Session()


    proxy_string = proxy_info.get('proxy_string')
    if proxy_string:
        session.proxies.update({"http": proxy_string, "https": proxy_string})
        print(f"   Proxy: {proxy_info.get('ip', 'unknown')}")
    else:
        print(f"   Proxy: None (direct)")

    session.headers.update({
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        "Origin": BASE_URL,
        "Referer": f"{BASE_URL}/",
    })


    for k, v in cookies.items():
        session.cookies.set(k, v, domain='vkserfing.ru')

    print(f"   Cookies: {list(cookies.keys())}")


    resp = retry(lambda: session.get(f"{BASE_URL}/assignments/instagram", timeout=30))


    match = re.search(r"TOKEN\s*=\s*['\"]([^'\"]+)['\"]", resp.text)
    if match:
        xsrf = match.group(1)
    if 'XSRF-TOKEN' in session.cookies:
        xsrf = session.cookies['XSRF-TOKEN']

    if resp.status_code == 200 and 'assignments' in resp.url:
        print(f"   ✅ VKS session valid!")
        print(f"   XSRF: {xsrf[:30]}...")
        return session, xsrf, proxy_info
    else:
        print(f"   ❌ VKS session invalid (redirected to login)")
        return None, None, None


def login_instagram(username, password):
    """Login Instagram dan return session + client"""
    print(f"\n{'='*50}")
    print(f"📱 STEP 2: Login Instagram")
    print(f"{'='*50}")
    print(f"   Username: {username}")

    device = random.choice(DEVICES)
    app_ver, ver_code = random.choice(APP_VERSIONS)

    uuids = {
        "phone_id": str(uuid.uuid4()),
        "uuid": str(uuid.uuid4()),
        "client_session_id": str(uuid.uuid4()),
        "advertising_id": str(uuid.uuid4()),
        "android_device_id": f"android-{random.randint(10**15, 10**16-1):016x}",
        "request_id": str(uuid.uuid4()),
        "tray_session_id": str(uuid.uuid4())
    }

    device_settings = {
        "app_version": app_ver,
        "android_version": device['android'],
        "android_release": device['release'],
        "dpi": device['dpi'],
        "resolution": device['resolution'],
        "manufacturer": device['manufacturer'],
        "device": device['device'],
        "model": device['model'],
        "cpu": device['cpu'],
        "version_code": ver_code
    }

    ua = f"Instagram {app_ver} Android ({device['android']}/{device['release']}; {device['dpi']}; {device['resolution']}; {device['manufacturer']}; {device['model']}; {device['device']}; {device['cpu']}; en_US; {ver_code})"

    print(f"   Device: {device['manufacturer']} {device['model']}")

    cl = Client()
    cl.set_device(device_settings)
    cl.set_user_agent(ua)
    cl.set_uuids(uuids)
    cl.set_locale("en_US")
    cl.set_timezone_offset(-14400)
    cl.delay_range = [1, 3]

    delay(1, 2, "Loading app")

    try:

        try:
            cl.login(username, password)
        except ChallengeRequired as e:

            print(f"   ⚠️  Challenge detected, attempting auto-solve...")
            try:

                api_path = cl.last_json.get("challenge", {}).get("api_path", "")
                if api_path:

                    cl.challenge_code_handler(username, 1)
                    print(f"   💡 Verification code sent to email")
                    code = input("   Enter verification code: ").strip()
                    cl.challenge_code_handler(username, code)
                    print(f"   ✅ Challenge solved!")
                else:
                    raise e
            except:
                raise e

        print(f"   ✅ Login OK! User ID: {cl.user_id}")

        info = retry(lambda: cl.account_info())
        actual_username = info.username
        print(f"   ✅ IG Username: @{actual_username}")

        session_data = {
            "uuids": uuids,
            "mid": cl.mid,
            "ig_u_rur": None,
            "ig_www_claim": None,
            "authorization_data": {
                "ds_user_id": str(cl.user_id),
                "sessionid": cl.sessionid
            },
            "cookies": {},
            "last_login": time.time(),
            "device_settings": device_settings,
            "user_agent": ua,
            "country": "US",
            "country_code": 1,
            "locale": "en_US",
            "timezone_offset": -14400,
        }

        return session_data, actual_username, str(cl.user_id), cl

    except ChallengeRequired as e:
        print(f"   ❌ Challenge required - Instagram needs verification")
        print(f"   💡 Try: Login via Instagram app first, complete verification, then try again")
        return None, None, None, None
    except TwoFactorRequired:
        print(f"   ❌ 2FA enabled - Please disable 2FA first")
        return None, None, None, None
    except BadPassword:
        print(f"   ❌ Wrong password")
        return None, None, None, None
    except PleaseWaitFewMinutes:
        print(f"   ❌ Rate limited - Wait 5-10 minutes and try again")
        return None, None, None, None
    except RecaptchaRequired:
        print(f"   ❌ Recaptcha required - Account flagged by Instagram")
        print(f"   💡 Try: Login via Instagram app/web first to clear the flag")
        return None, None, None, None
    except LoginRequired:
        print(f"   ❌ Login failed - Account may be disabled or credentials invalid")
        return None, None, None, None
    except Exception as e:
        error_msg = str(e).lower()
        if 'checkpoint' in error_msg or 'challenge' in error_msg:
            print(f"   ❌ Account needs verification")
            print(f"   💡 Login via Instagram app/web first to complete verification")
        elif 'password' in error_msg:
            print(f"   ❌ Password incorrect")
        elif 'user' in error_msg and 'not found' in error_msg:
            print(f"   ❌ Username not found")
        elif 'spam' in error_msg or 'suspicious' in error_msg:
            print(f"   ❌ Account flagged as suspicious")
            print(f"   💡 Wait 24-48 hours or verify via Instagram app")
        else:
            print(f"   ❌ Error: {str(e)[:100]}")
        return None, None, None, None

    return None, None, None, None


def get_random_photos(count=10):
    if not os.path.exists(IG_DOWNLOADS_DIR):
        return []

    all_photos = []
    for user_folder in os.listdir(IG_DOWNLOADS_DIR):
        user_path = os.path.join(IG_DOWNLOADS_DIR, user_folder)
        if os.path.isdir(user_path):
            for f in os.listdir(user_path):
                if f.endswith(('.jpg', '.jpeg', '.png')):
                    all_photos.append(os.path.join(user_path, f))

    random.shuffle(all_photos)
    return all_photos[:count]

def setup_ig_profile(ig_client):
    """Setup IG profile - always set new pic, post only if needed"""
    print(f"\n{'='*50}")
    print(f"🔍 STEP 3: Setup IG Profile")
    print(f"{'='*50}")

    try:
        photos = get_random_photos(15)
        if not photos:
            print(f"   ⚠️ No photos in ig_downloads/")
            return True


        print(f"   [+] Setting profile pic...")
        try:
            retry(lambda: ig_client.account_change_picture(photos[0]))
            print(f"   ✅ Profile pic set")
            photos.pop(0)
            delay(3, 5, "Waiting")
        except Exception as e:
            print(f"   ⚠️ Failed: {str(e)[:30]}")


        post_count = 0
        try:
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()
            medias = retry(lambda: ig_client.user_medias(ig_client.user_id, amount=5), silent=True)
            post_count = len(medias) if medias else 0
            sys.stderr = old_stderr
        except:
            sys.stderr = old_stderr

        posts_needed = max(0, 5 - post_count)
        if posts_needed > 0 and photos:
            print(f"   [+] Creating {posts_needed} posts...")
            captions = ["✨", "💫", "🌟", "🔥", "❤️", "Good vibes ✨", "Blessed 🙏"]
            posted = 0
            for i in range(min(posts_needed, len(photos))):
                try:
                    old_stderr = sys.stderr
                    sys.stderr = io.StringIO()
                    retry(lambda p=photos[i]: ig_client.photo_upload(p, caption=random.choice(captions)))
                    sys.stderr = old_stderr
                    posted += 1
                    print(f"   ✅ Post {posted}/{posts_needed}")
                    if posted < posts_needed:
                        delay(4, 8, "Waiting")
                except Exception as e:
                    sys.stderr = old_stderr
                    print(f"   ⚠️ Post failed, skipping")
        else:
            print(f"   Posts: {post_count} ✅")

        print(f"   ✅ Profile setup done")
        return True

    except Exception as e:
        print(f"   ⚠️ Error: {str(e)[:50]}")
        return True


def bind_ig_to_vks(vks_session, xsrf, ig_client, ig_username):
    """Bind Instagram to VKSerfing account"""
    print(f"\n{'='*50}")
    print(f"🔗 STEP 4: Bind IG to VKSerfing")
    print(f"{'='*50}")

    def get_headers():
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
            "x-xsrf-token": xsrf,
        }

    def vks_get(url, **kwargs):
        return retry(lambda: vks_session.get(url, **kwargs))

    def vks_post(url, **kwargs):
        return retry(lambda: vks_session.post(url, **kwargs))


    print(f"\n   [1/4] Get verification phrase...")
    delay(1, 2)
    resp = vks_get(f"{BASE_URL}/auth/phrase", headers=get_headers(), timeout=30)

    if resp.status_code != 200:
        print(f"   ❌ Failed: {resp.status_code}")
        return False

    data = resp.json()
    if data.get("status") != "success":
        print(f"   ❌ Error: {data}")
        return False

    phrase = data["phrase"]["text"]
    phrase_hash = data["phrase"]["hash"]
    print(f"   ✅ Phrase: {phrase}")


    print(f"\n   [2/4] Set Instagram bio...")
    delay(1, 2)
    try:
        retry(lambda: ig_client.account_edit(biography=phrase))
        print(f"   ✅ Bio updated")
    except Exception as e:
        print(f"   ❌ Failed: {e}")
        return False

    time.sleep(3)


    print(f"\n   [3/4] Validating @{ig_username}...")
    delay(1, 2)
    resp = vks_post(
        f"{BASE_URL}/auth/presocial/instagram",
        headers=get_headers(),
        json={"username": f"@{ig_username}", "phraseToken": phrase_hash},
        timeout=30
    )

    if resp.status_code != 200 or "error" in resp.text.lower():
        print(f"   ❌ Failed: {resp.text[:100]}")
        return False
    print(f"   ✅ Validation OK")


    print(f"\n   [4/4] Connecting account...")
    delay(1, 2)
    resp = vks_post(
        f"{BASE_URL}/auth/social/instagram",
        headers=get_headers(),
        json={"username": f"@{ig_username}", "phraseToken": phrase_hash},
        timeout=30
    )

    if resp.status_code != 200:
        print(f"   ❌ Failed: {resp.status_code}")
        return False

    data = resp.json()
    if data.get("status") != "success":
        print(f"   ❌ Error: {data.get('message', data)}")
        return False

    print(f"   ✅ Connected!")


    print(f"\n   [+] Clearing bio...")
    try:
        retry(lambda: ig_client.account_edit(biography=""))
        print(f"   ✅ Bio cleared")
    except:
        print(f"   ⚠️ Manual clear needed")

    return True


def get_city_list(vks_session, xsrf, country_id):
    """Get cities for country from API"""
    headers = {
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'x-xsrf-token': xsrf,
    }
    resp = retry(lambda: vks_session.get(f'{BASE_URL}/get_cities?country_id={country_id}', headers=headers, timeout=30))
    if resp.status_code == 200:
        data = resp.json()
        return data.get('data', [])
    return []

def set_vks_profile_data(vks_session, xsrf):
    """Set VKS profile data (country, city, birthday, sex)"""
    print(f"\n{'='*50}")
    print(f"📝 STEP 5: Set VKS Profile Data")
    print(f"{'='*50}")

    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json, text/plain, */*',
        'X-Requested-With': 'XMLHttpRequest',
        'x-xsrf-token': xsrf,
    }


    country_id = random.choice(COUNTRIES)
    print(f"   Country ID: {country_id}")


    print(f"   [1/2] Getting city list...")
    cities = get_city_list(vks_session, xsrf, country_id)

    if not cities:
        print(f"   ❌ No cities found for country {country_id}")
        return False


    city = random.choice(cities)
    city_id = city['value']
    city_name = city['label']
    print(f"   City: {city_name} (ID: {city_id})")


    year = random.randint(1990, 2006)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    birthday = f"{day:02d}.{month:02d}.{year}"
    print(f"   Birthday: {birthday}")


    sex = random.choice(["1", "2"])
    print(f"   Sex: {'Male' if sex == '1' else 'Female'}")


    print(f"\n   [2/2] Saving profile data...")
    payload = {
        "mail": None,
        "country_id": str(country_id),
        "birthday": birthday,
        "city_id": str(city_id),
        "sex": sex,
        "platform": "instagram"
    }

    resp = vks_session.post(f'{BASE_URL}/account/data', headers=headers, json=payload, timeout=30)

    if resp.status_code == 200:
        data = resp.json()
        if data.get('status') == 'success':
            print(f"   ✅ Profile data saved!")
            return True
        else:
            print(f"   ❌ Error: {data}")
    else:
        print(f"   ❌ Failed: {resp.status_code}")

    return False


def save_account(account_name, config, ig_session, ig_username, ds_user_id, ig_password, vks_session, xsrf, proxy_info):
    """Save IG session and update config with VKS cookies format from vks_register.py"""
    print(f"\n{'='*50}")
    print(f"💾 STEP 6: Save Account")
    print(f"{'='*50}")

    account_dir = os.path.join(ACCOUNTS_DIR, account_name)


    session_file = f"ig_session_{ig_username}.json"
    with open(os.path.join(account_dir, session_file), 'w') as f:
        json.dump(ig_session, f, indent=2)
    print(f"   ✅ {session_file}")


    all_cookies = dict(vks_session.cookies)
    cookie_string = "; ".join([f"{k}={v}" for k, v in all_cookies.items()])

    config['credentials'] = {
        "cookies": {
            "vkstoken": all_cookies.get("vkstoken", ""),
            "vksid": all_cookies.get("vksid", ""),
            "sessid": all_cookies.get("sessid", ""),
            "ref": all_cookies.get("ref", ""),
            "notify_rules": all_cookies.get("notify_rules", ""),
        },
        "xsrf_token": xsrf,
        "all_cookies": all_cookies,
        "cookie_string": cookie_string,
    }


    config['proxy'] = proxy_info

    config['instagram'] = {
        "enabled": True,
        "username": ig_username,
        "ds_user_id": ds_user_id,
        "session_file": session_file,
        "password": ig_password
    }

    config['task_types']['instagram_followers'] = True
    config['task_types']['instagram_likes'] = True
    config['task_types']['instagram_comments'] = True
    config['task_types']['instagram_video'] = True

    save_config(account_name, config)
    print(f"   ✅ config.json updated")
    print(f"   ✅ VKS cookies saved (format: vks_register.py)")

    return True


def main():
    print("=" * 50)
    print("🔗 Instagram Binding (Cookie + IG Login + Bind)")
    print("=" * 50)

    accounts = list_accounts()
    if not accounts:
        print("\n❌ No accounts without IG found!")
        return

    print(f"\n📁 Accounts without IG ({len(accounts)}):")
    for i, acc in enumerate(accounts, 1):
        print(f"  {i}. {acc}")
    print("  0. Exit")

    try:
        choice = input("\nAccount number: ").strip()
        if choice == '0':
            return
        idx = int(choice) - 1
        if idx < 0 or idx >= len(accounts):
            print("❌ Invalid!")
            return
        account_name = accounts[idx]
    except ValueError:
        print("❌ Invalid!")
        return

    config = load_config(account_name)
    if not config:
        print(f"❌ Config not found!")
        return

    print(f"\n📱 Selected: {account_name}")


    vks_session, xsrf, proxy_info = login_vks_with_cookie(config)
    if not vks_session:
        print("\n❌ VKS session invalid! Re-register needed.")
        return


    print("\n" + "="*50)
    ig_user = input("Instagram username/email: ").strip()
    ig_pass = input("Instagram password: ").strip()

    if not ig_user or not ig_pass:
        print("❌ Required!")
        return

    ig_session, ig_username, ds_user_id, ig_client = login_instagram(ig_user, ig_pass)
    if not ig_session:
        print("\n❌ IG login failed!")
        return


    if not setup_ig_profile(ig_client):
        print("\n❌ Profile setup cancelled!")
        return


    if not bind_ig_to_vks(vks_session, xsrf, ig_client, ig_username):
        print("\n❌ Binding failed!")
        return


    if not set_vks_profile_data(vks_session, xsrf):
        print("\n⚠️ Profile data setup failed, but continuing...")


    save_account(account_name, config, ig_session, ig_username, ds_user_id, ig_pass, vks_session, xsrf, proxy_info)

    print(f"\n{'='*50}")
    print(f"✅ DONE! @{ig_username} bound to {account_name}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
