#!/usr/bin/env python3
"""
Fix main.py IP collision to use new proxy pool
"""

import re

# Read main.py
with open('/root/vkserbot.v2/main.py', 'r') as f:
    content = f.read()

# Pattern to replace (old proxy_manager logic)
old_pattern = r'''                    if hasattr\(bot, 'proxy_manager'\) and bot\.proxy_manager:

                        exclude_ips = set\(used_ips\.keys\(\)\)

                        print\(f"\{C\}\[Auto-Fetch\] Mencari proxy baru \(exclude \{len\(exclude_ips\)\} IPs\)\.\.\.\{W\}"\)


                        exclude_proxies = set\(\)
                        for existing_folder in folders\[:idx\]:
                            existing_config = load_account_config\(existing_folder\)
                            if existing_config and existing_config\.get\('proxy'\):
                                proxy_str = existing_config\['proxy'\]\.get\('proxy_string'\)
                                if proxy_str:
                                    exclude_proxies\.add\(proxy_str\)


                        success, new_proxy_dict, new_ip_info = bot\.proxy_manager\.auto_discover_proxy\(
                            exclude_proxies=exclude_proxies,
                            protocol='http'
                        \)

                        if success and new_proxy_dict and new_ip_info:

                            bot\.proxy_dict = new_proxy_dict
                            bot\.proxy_info = new_ip_info
                            current_ip = new_ip_info\.get\('ip'\)


                            config\['proxy'\] = \{
                                'proxy_string': new_proxy_dict\['raw'\],
                                'ip': new_ip_info\['ip'\],
                                'country': new_ip_info\.get\('country', 'Unknown'\),
                                'country_code': new_ip_info\.get\('country_code', ''\),
                                'city': new_ip_info\.get\('city', 'Unknown'\),
                                'region': new_ip_info\.get\('region', ''\),
                                'isp': new_ip_info\.get\('isp', ''\),
                                'verified_at': time\.strftime\('%Y-%m-%d %H:%M:%S'\)
                            \}

                            print\(f"\{G\}✓ New proxy bound: \{new_ip_info\['ip'\]\} \(\{new_ip_info\['country'\]\}\)\{W\}\\n"\)
                        else:
                            print\(f"\{R\}✗ Failed to get new proxy, skipping \{folder\}\{W\}\\n"\)
                            os\.chdir\(original_cwd\)
                            continue
                    else:
                        print\(f"\{R\}✗ No proxy manager available, skipping \{folder\}\{W\}\\n"\)
                        os\.chdir\(original_cwd\)
                        continue'''

new_code = '''                    # Use new proxy pool for collision resolution
                    if hasattr(bot, 'proxy_pool') and bot.proxy_pool:
                        exclude_ips = set(used_ips.keys())
                        
                        print(f"{C}[Auto-Fetch] Getting new proxy from Webshare (exclude {len(exclude_ips)} IPs)...{W}")
                        
                        # Get new proxy from pool
                        new_proxy = bot.proxy_pool.rotate_proxy(
                            folder,
                            current_ip,
                            exclude_ips=exclude_ips,
                            max_retries=3
                        )
                        
                        if new_proxy:
                            # Update bot session
                            bot.session.proxies.update({
                                'http': new_proxy['proxy_url'],
                                'https': new_proxy['proxy_url']
                            })
                            bot.proxy_info = new_proxy['ip_info']
                            bot.current_proxy_ip = new_proxy['ip']
                            current_ip = new_proxy['ip']
                            
                            # Update config
                            config['proxy'] = {
                                'proxy_string': new_proxy['proxy_string'],
                                'ip': new_proxy['ip'],
                                'port': new_proxy['port'],
                                'username': new_proxy['username'],
                                'password': new_proxy['password'],
                                'country': new_proxy['ip_info'].get('country', 'Unknown'),
                                'city': new_proxy['ip_info'].get('city', 'Unknown'),
                                'verified_at': time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                            
                            print(f"{G}✓ New proxy bound: {new_proxy['ip']} ({new_proxy['ip_info']['country']}){W}\\n")
                        else:
                            print(f"{R}✗ Failed to get new proxy, skipping {folder}{W}\\n")
                            os.chdir(original_cwd)
                            continue
                    else:
                        print(f"{R}✗ No proxy pool available, skipping {folder}{W}\\n")
                        os.chdir(original_cwd)
                        continue'''

# Replace all occurrences
content = re.sub(old_pattern, new_code, content)

# Write back
with open('/root/vkserbot.v2/main.py', 'w') as f:
    f.write(content)

print("✓ Fixed main.py IP collision handling")
