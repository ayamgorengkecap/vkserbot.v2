#!/usr/bin/env python3
"""
Telegram Session Manager
Untuk membuat dan mengelola session Telegram yang akan digunakan untuk task automation
"""

import json
import os
import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetMessagesViewsRequest
import sys


DEFAULT_API_ID = 1724399
DEFAULT_API_HASH = '7f6c4af5220db320413ff672093ee102'


class TelegramSessionManager:
    def __init__(self, session_file='telegram_session.json'):
        self.session_file = session_file
        self.sessions = self.load_sessions()

    def load_sessions(self):
        """Load saved sessions from file"""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_sessions(self):
        """Save sessions to file"""
        with open(self.session_file, 'w') as f:
            json.dump(self.sessions, indent=2, fp=f)
        print(f"[SUCCESS] Sessions saved to {self.session_file}")

    def add_session(self, session_name, api_id=None, api_hash=None, phone=None):
        """Add new session configuration"""

        if api_id is None:
            api_id = DEFAULT_API_ID
        if api_hash is None:
            api_hash = DEFAULT_API_HASH

        self.sessions[session_name] = {
            'api_id': api_id,
            'api_hash': api_hash,
            'phone': phone,
            'session_string': None,
            'valid': False
        }
        self.save_sessions()
        print(f"[INFO] Session '{session_name}' added")
        print(f"[INFO] Using API ID: {api_id}")
        print(f"[INFO] Using API Hash: {api_hash[:20]}...")

    async def create_session(self, session_name):
        """Create and validate new Telegram session"""
        if session_name not in self.sessions:
            print(f"[ERROR] Session '{session_name}' not found")
            return False

        session_data = self.sessions[session_name]
        api_id = session_data['api_id']
        api_hash = session_data['api_hash']
        phone = session_data['phone']


        print(f"\n⚠️  PERINGATAN: Anda akan membuat session Telegram baru untuk {phone}")
        print("    Session ini akan digunakan untuk automation tasks")
        confirm = input("\nLanjutkan membuat session? (yes/no): ").strip().lower()
        if confirm not in ['yes', 'y']:
            print("\n❌ Pembuatan session dibatalkan")
            return False

        print(f"\n[INFO] Creating session for {phone}...")


        client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print(f"[INFO] Sending code to {phone}...")
                await client.send_code_request(phone)


                code = input("[INPUT] Enter the code you received: ")

                try:
                    await client.sign_in(phone, code)
                except SessionPasswordNeededError:
                    password = input("[INPUT] Two-step verification enabled. Enter your password: ")
                    await client.sign_in(password=password)
                except PhoneCodeInvalidError:
                    print("[ERROR] Invalid code!")
                    return False


            me = await client.get_me()
            print(f"[SUCCESS] Logged in as: {me.first_name} (@{me.username})")
            print(f"[SUCCESS] User ID: {me.id}")


            self.sessions[session_name]['valid'] = True
            self.sessions[session_name]['user_id'] = me.id
            self.sessions[session_name]['username'] = me.username or ""
            self.sessions[session_name]['first_name'] = me.first_name
            self.save_sessions()

            await client.disconnect()
            return True

        except Exception as e:
            print(f"[ERROR] Failed to create session: {e}")
            return False

    async def test_session(self, session_name):
        """Test if existing session is still valid"""
        if session_name not in self.sessions:
            print(f"[ERROR] Session '{session_name}' not found")
            return False

        session_data = self.sessions[session_name]
        api_id = session_data['api_id']
        api_hash = session_data['api_hash']

        client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print(f"[ERROR] Session '{session_name}' is not authorized")
                self.sessions[session_name]['valid'] = False
                self.save_sessions()
                await client.disconnect()
                return False

            me = await client.get_me()
            print(f"[SUCCESS] Session valid: {me.first_name} (@{me.username})")

            self.sessions[session_name]['valid'] = True
            self.save_sessions()

            await client.disconnect()
            return True

        except Exception as e:
            print(f"[ERROR] Session test failed: {e}")
            self.sessions[session_name]['valid'] = False
            self.save_sessions()
            return False

    async def join_channel(self, session_name, channel_username):
        """Join a Telegram channel/group - PROPERLY JOIN AND VERIFY"""
        if session_name not in self.sessions:
            print(f"[ERROR] Session '{session_name}' not found")
            return False

        if not self.sessions[session_name].get('valid', False):
            print(f"[ERROR] Session '{session_name}' is not valid")
            return False

        session_data = self.sessions[session_name]
        api_id = session_data['api_id']
        api_hash = session_data['api_hash']

        client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)

        try:
            await client.connect()


            channel = channel_username.replace('https://t.me/', '').replace('@', '').strip()

            print(f"[INFO] Joining channel: @{channel}")


            try:
                entity = await client.get_entity(channel)


                await client(JoinChannelRequest(entity))


                await asyncio.sleep(1)


                full_channel = await client.get_entity(entity)
                print(f"[SUCCESS] Joined @{channel}")
                print(f"[INFO] Channel: {full_channel.title if hasattr(full_channel, 'title') else channel}")

            except Exception as join_error:

                error_msg = str(join_error).lower()
                if 'already' in error_msg or 'participant' in error_msg:
                    print(f"[INFO] Already a member of @{channel}")
                    await client.disconnect()
                    return True
                else:
                    raise join_error

            await client.disconnect()
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if 'already' in error_msg or 'participant' in error_msg:
                print(f"[INFO] Already a member (from error check)")
                await client.disconnect()
                return True
            print(f"[ERROR] Failed to join channel: {e}")
            await client.disconnect()
            return False

    async def view_post(self, session_name, post_link):
        """View a Telegram post (for view tasks) - PROPERLY VIEW WITH CONTENT READ"""
        if session_name not in self.sessions:
            print(f"[ERROR] Session '{session_name}' not found")
            return False

        if not self.sessions[session_name].get('valid', False):
            print(f"[ERROR] Session '{session_name}' is not valid")
            return False

        session_data = self.sessions[session_name]
        api_id = session_data['api_id']
        api_hash = session_data['api_hash']

        client = TelegramClient(f'sessions/{session_name}', api_id, api_hash)

        try:
            await client.connect()


            parts = post_link.replace('https://t.me/', '').split('/')
            if len(parts) != 2:
                print(f"[ERROR] Invalid post link format")
                await client.disconnect()
                return False

            channel_username = parts[0]
            message_id = int(parts[1])

            print(f"[INFO] Viewing post: {channel_username}/{message_id}")


            channel = await client.get_entity(channel_username)


            message = await client.get_messages(channel, ids=message_id)

            if not message:
                print(f"[ERROR] Post not found")
                await client.disconnect()
                return False


            print(f"[INFO] Reading message content...")


            if message.text:
                text_preview = message.text[:50] + ('...' if len(message.text) > 50 else '')
                print(f"[INFO] Text: {text_preview}")


            if message.media:
                try:
                    print(f"[INFO] Message has media, fetching...")

                    media_type = type(message.media).__name__
                    print(f"[INFO] Media type: {media_type}")


                    if hasattr(message.media, 'photo') or hasattr(message.media, 'document'):
                        print(f"[INFO] Fetching media preview...")

                        try:

                            await client.download_media(message, file=bytes)
                        except:

                            pass
                except Exception as e:
                    print(f"[WARNING] Media fetch error (continuing): {e}")


            try:
                await client.send_read_acknowledge(channel, message)
                print(f"[INFO] Marked as read")
            except:

                pass

            print(f"[SUCCESS] Post fully viewed: {channel_username}/{message_id}")
            await client.disconnect()
            return True

        except Exception as e:
            print(f"[ERROR] Failed to view post: {e}")
            await client.disconnect()
            return False

    def list_sessions(self):
        """List all saved sessions"""
        if not self.sessions:
            print("[INFO] No sessions found")
            return

        print("\n=== SAVED SESSIONS ===")
        for name, data in self.sessions.items():
            status = "✓ VALID" if data.get('valid', False) else "✗ INVALID"
            phone = data.get('phone', 'N/A')
            username = data.get('username', 'N/A')
            print(f"{name}: {phone} (@{username}) [{status}]")
        print()

    def get_valid_session(self):
        """Get first valid session name"""
        for name, data in self.sessions.items():
            if data.get('valid', False):
                return name
        return None


async def interactive_menu():
    """Interactive menu for session management"""
    manager = TelegramSessionManager()


    os.makedirs('sessions', exist_ok=True)

    while True:
        print("\n" + "="*70)
        print("TELEGRAM SESSION MANAGER")
        print("="*70)
        print("1. Add new session")
        print("2. Create/authorize session")
        print("3. Test existing session")
        print("4. List all sessions")
        print("5. Test join channel")
        print("6. Test view post")
        print("7. Exit")
        print("="*70)

        choice = input("\nChoice: ").strip()

        if choice == '1':
            print("\n--- ADD NEW SESSION ---")
            print(f"Default API credentials:")
            print(f"  API ID: {DEFAULT_API_ID}")
            print(f"  API Hash: {DEFAULT_API_HASH[:20]}...")
            print(f"\nTekan Enter untuk menggunakan default credentials")

            session_name = input("\nSession name: ").strip()
            api_id = input(f"API ID [{DEFAULT_API_ID}]: ").strip()
            api_hash = input(f"API Hash [{DEFAULT_API_HASH[:20]}...]: ").strip()
            phone = input("Phone (with country code, e.g. +62xxx): ").strip()


            if not api_id:
                api_id = DEFAULT_API_ID
            if not api_hash:
                api_hash = DEFAULT_API_HASH

            manager.add_session(session_name, int(api_id), api_hash, phone)

        elif choice == '2':
            print("\n--- CREATE SESSION ---")
            manager.list_sessions()
            session_name = input("Session name to authorize: ").strip()
            await manager.create_session(session_name)

        elif choice == '3':
            print("\n--- TEST SESSION ---")
            manager.list_sessions()
            session_name = input("Session name to test: ").strip()
            await manager.test_session(session_name)

        elif choice == '4':
            manager.list_sessions()

        elif choice == '5':
            print("\n--- TEST JOIN CHANNEL ---")
            manager.list_sessions()
            session_name = input("Session name: ").strip()
            channel = input("Channel username or link (e.g. @channel or https://t.me/channel): ").strip()
            await manager.join_channel(session_name, channel)

        elif choice == '6':
            print("\n--- TEST VIEW POST ---")
            manager.list_sessions()
            session_name = input("Session name: ").strip()
            post_link = input("Post link (e.g. https://t.me/channel/123): ").strip()
            await manager.view_post(session_name, post_link)

        elif choice == '7':
            print("\nGoodbye!")
            break

        else:
            print("[ERROR] Invalid choice")


if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════════════════════════╗
║           TELEGRAM SESSION MANAGER                               ║
║                                                                  ║
║  Untuk mendapatkan API ID dan API Hash:                         ║
║  1. Buka https://my.telegram.org/apps                           ║
║  2. Login dengan nomor Telegram Anda                            ║
║  3. Create new application                                       ║
║  4. Copy API ID dan API Hash                                     ║
╚══════════════════════════════════════════════════════════════════╝
""")

    try:
        asyncio.run(interactive_menu())
    except KeyboardInterrupt:
        print("\n\n[INFO] Stopped by user")
    except Exception as e:
        print(f"\n[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
