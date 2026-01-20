#!/usr/bin/env python3
"""Instagram Photo Downloader - Max 20 photos per profile"""

import os, re, json, time, random, requests
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DOWNLOAD_DIR = SCRIPT_DIR / "ig_downloads"
MAX_PHOTOS = 20

def find_ig_session():
    for folder in ['test', 'accounts']:
        p = SCRIPT_DIR / folder
        if p.exists():
            for acc in sorted(p.iterdir()):
                if acc.is_dir():
                    for f in acc.iterdir():
                        if f.name.startswith('ig_session_') and f.name.endswith('.json'):
                            return f
    return None

def extract_username(url):
    m = re.search(r"instagram\.com/([^/?]+)", url)
    if m and m.group(1) not in ['p', 'reel', 'stories', 'explore']:
        return m.group(1)
    return None

def get_headers(session_file):
    with open(session_file) as f:
        data = json.load(f)
    sessionid = data.get('authorization_data', {}).get('sessionid', '')
    return {
        'User-Agent': 'Instagram 358.0.0.46.83 Android',
        'Cookie': f'sessionid={sessionid}',
        'X-IG-App-ID': '936619743392459',
    }

def download_profile(username, headers):
    user_folder = DOWNLOAD_DIR / username
    user_folder.mkdir(parents=True, exist_ok=True)

    try:

        r = requests.get(f'https://i.instagram.com/api/v1/users/web_profile_info/?username={username}', headers=headers, timeout=15)
        if r.status_code != 200:
            return username, 0, f"HTTP {r.status_code}"

        user = r.json().get('data', {}).get('user')
        if not user:
            return username, 0, "User not found"

        user_id = user['id']


        r2 = requests.get(f'https://i.instagram.com/api/v1/feed/user/{user_id}/?count={MAX_PHOTOS}', headers=headers, timeout=15)
        if r2.status_code != 200:
            return username, 0, f"Feed HTTP {r2.status_code}"

        items = r2.json().get('items', [])

        count = 0
        for item in items:
            if count >= MAX_PHOTOS:
                break

            media_type = item.get('media_type')


            if media_type == 1:
                candidates = item.get('image_versions2', {}).get('candidates', [])
                if candidates:
                    img_url = candidates[0].get('url')
                    if img_url:
                        try:
                            img_r = requests.get(img_url, timeout=30)
                            if img_r.status_code == 200:
                                pk = item.get('pk', f'img_{count}')
                                with open(user_folder / f"{pk}.jpg", 'wb') as f:
                                    f.write(img_r.content)
                                count += 1
                        except:
                            pass

            elif media_type == 8:
                resources = item.get('carousel_media', [])
                for res in resources[:1]:
                    if res.get('media_type') == 1:
                        candidates = res.get('image_versions2', {}).get('candidates', [])
                        if candidates:
                            img_url = candidates[0].get('url')
                            if img_url:
                                try:
                                    img_r = requests.get(img_url, timeout=30)
                                    if img_r.status_code == 200:
                                        pk = res.get('pk', f'img_{count}')
                                        with open(user_folder / f"{pk}.jpg", 'wb') as f:
                                            f.write(img_r.content)
                                        count += 1
                                except:
                                    pass
                        break

            time.sleep(random.uniform(0.2, 0.5))

        return username, count, None
    except Exception as e:
        return username, 0, str(e)[:40]

def main():
    print("=" * 50)
    print("📸 Instagram Photo Downloader")
    print(f"   Max {MAX_PHOTOS} photos per profile")
    print("=" * 50)

    session_file = find_ig_session()
    if not session_file:
        print("❌ No IG session found")
        return

    print(f"🔑 Using: {session_file.name}")
    headers = get_headers(session_file)

    print("\nPaste URLs (empty line to start):")
    urls = []
    while True:
        line = input().strip()
        if not line:
            break
        urls.append(line)

    if not urls:
        print("❌ No URLs")
        return

    usernames = []
    for url in urls:
        u = extract_username(url)
        if u:
            usernames.append(u)
            print(f"  ✓ {u}")

    if not usernames:
        print("❌ No valid usernames")
        return

    print(f"\n📥 Downloading {len(usernames)} profiles...\n")

    results = []
    for i, username in enumerate(usernames, 1):
        print(f"  [{i}/{len(usernames)}] {username}...", end=" ", flush=True)
        u, count, err = download_profile(username, headers)
        print(f"✗ {err}" if err else f"✓ {count} photos")
        results.append((u, count, err))
        if i < len(usernames):
            time.sleep(random.randint(2, 4))

    success = sum(1 for _, c, e in results if not e and c > 0)
    total = sum(c for _, c, _ in results)

    print(f"\n{'='*50}")
    print(f"✅ {success}/{len(usernames)} profiles | 📸 {total} photos")
    print(f"📁 {DOWNLOAD_DIR}")

if __name__ == "__main__":
    main()
