"""
Clean Output Formatter for Bot
"""
import sys
from datetime import datetime

class CleanOutput:
    """Clean, minimal output formatter"""


    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'


    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    CYAN = '\033[96m'
    GRAY = '\033[90m'

    @staticmethod
    def account_header(account_name, ip, user_agent, balance):
        """Print account header"""
        device = user_agent.split('(')[1].split(')')[0] if '(' in user_agent else 'Unknown'

        print(f"\n{CleanOutput.CYAN}┌─ {account_name} {CleanOutput.RESET}")
        print(f"{CleanOutput.GRAY}│ IP: {ip}{CleanOutput.RESET}")
        print(f"{CleanOutput.GRAY}│ UA: {device}{CleanOutput.RESET}")
        print(f"{CleanOutput.GRAY}│ Balance: {balance:.2f}₽{CleanOutput.RESET}")

    @staticmethod
    def task_summary(tasks_dict):
        """Print task summary"""
        total = sum(tasks_dict.values())
        if total == 0:
            print(f"{CleanOutput.GRAY}│ Tasks: None{CleanOutput.RESET}")
            return

        print(f"{CleanOutput.GRAY}│ Tasks:{CleanOutput.RESET}")
        for k, v in tasks_dict.items():
            if v > 0:
                print(f"{CleanOutput.GRAY}│   {CleanOutput.GREEN}{k}: {v}{CleanOutput.RESET}")
            else:
                print(f"{CleanOutput.GRAY}│   {k}: {CleanOutput.YELLOW}0{CleanOutput.RESET}")
        print(f"{CleanOutput.GRAY}│ Total: {total}{CleanOutput.RESET}")

    @staticmethod
    def progress_bar(current, total, width=30):
        """Generate progress bar"""
        if total == 0:
            return ""

        percent = current / total
        filled = int(width * percent)
        bar = f"{CleanOutput.GREEN}{'█' * filled}{CleanOutput.GRAY}{'░' * (width - filled)}{CleanOutput.RESET}"
        return f"[{bar}] {current}/{total} ({percent*100:.0f}%)"

    @staticmethod
    def task_progress(current, total):
        """Print task progress (update in-place)"""
        bar = CleanOutput.progress_bar(current, total, width=20)

        print(f"\r{CleanOutput.GRAY}│ {bar}{CleanOutput.RESET}", end='', flush=True)

    @staticmethod
    def task_result(task_type, success, error_msg=None):
        """Print task result (minimal)"""
        if success:
            symbol = f"{CleanOutput.GREEN}✓{CleanOutput.RESET}"
        else:
            symbol = f"{CleanOutput.RED}✗{CleanOutput.RESET}"

        if error_msg:
            print(f"\r{CleanOutput.GRAY}│ {symbol} {task_type}: {error_msg}{CleanOutput.RESET}")
        else:

            pass

    @staticmethod
    def account_footer(earned, final_balance):
        """Print account footer"""
        if earned > 0:
            color = CleanOutput.GREEN
            symbol = "+"
        elif earned < 0:
            color = CleanOutput.RED
            symbol = ""
        else:
            color = CleanOutput.GRAY
            symbol = "±"

        print(f"\n{CleanOutput.GRAY}│ Earned: {color}{symbol}{earned:.2f}₽{CleanOutput.RESET}")
        print(f"{CleanOutput.GRAY}└─ Final: {final_balance:.2f}₽{CleanOutput.RESET}")

    @staticmethod
    def error(message, error_code=None):
        """Print error message"""
        if error_code:
            print(f"{CleanOutput.RED}✗ Error {error_code}: {message}{CleanOutput.RESET}")
        else:
            print(f"{CleanOutput.RED}✗ {message}{CleanOutput.RESET}")

    @staticmethod
    def warning(message):
        """Print warning message"""
        print(f"{CleanOutput.YELLOW}⚠ {message}{CleanOutput.RESET}")

    @staticmethod
    def info(message):
        """Print info message"""
        print(f"{CleanOutput.GRAY}{message}{CleanOutput.RESET}")
