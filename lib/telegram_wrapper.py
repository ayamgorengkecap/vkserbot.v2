#!/usr/bin/env python3
"""
Telegram Wrapper
Simple synchronous wrapper untuk telegram operations yang akan digunakan di automation bot
"""

import asyncio
from telegram_session_manager import TelegramSessionManager


class TelegramWrapper:
    """Synchronous wrapper for telegram operations"""

    def __init__(self):
        self.manager = TelegramSessionManager()
        self.current_session = self.manager.get_valid_session()

    def is_available(self):
        """Check if telegram wrapper is available"""
        return self.current_session is not None

    def join_channel(self, channel_link):
        """Join telegram channel (synchronous)"""
        if not self.current_session:
            return False

        try:
            result = asyncio.run(self.manager.join_channel(self.current_session, channel_link))
            return result
        except Exception as e:
            return False

    def view_post(self, post_link):
        """View telegram post (synchronous) - PROPERLY VIEW WITH CONTENT READ
        Returns:
            True: Success
            False: Failed
        """
        if not self.current_session:
            return False

        try:
            result = asyncio.run(self.manager.view_post(self.current_session, post_link))
            return result
        except Exception as e:
            return False



if __name__ == "__main__":
    print("Testing Telegram Wrapper...")
    wrapper = TelegramWrapper()

    if wrapper.is_available():
        print("\n[TEST] Telegram wrapper is ready!")


        test_channel = input("\nEnter channel to test (or press Enter to skip): ").strip()
        if test_channel:
            result = wrapper.join_channel(test_channel)
            print(f"Join result: {result}")


        test_post = input("\nEnter post link to test (or press Enter to skip): ").strip()
        if test_post:
            result = wrapper.view_post(test_post)
            print(f"View result: {result}")
    else:
        print("\n[ERROR] Telegram wrapper not available")
        print("[INFO] Run: python3 telegram_session_manager.py")
