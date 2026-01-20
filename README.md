# VKSBot

VK automation bot with advanced features.

## Support

For questions or support, contact: [@aldo_tamvan](https://t.me/aldo_tamvan)

## Requirements

**IMPORTANT:** This bot requires **Python 3.11.2**. Other Python versions may not work due to bytecode compatibility.

### Install Python 3.11.2

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev -y
```

**Verify installation:**
```bash
python3.11 --version
# Should output: Python 3.11.2
```

**Termux (Android):**
```bash
pkg update && pkg upgrade -y
pkg install python git -y
```

**Verify installation:**
```bash
python --version
# Should output: Python 3.11.x or higher
```

## Prerequisites

Before running this bot, you need to register accounts using the account registration tool.

### Step 1: Register Accounts

1. Clone the account registration tool:
```bash
git clone https://github.com/ayamgorengkecap/ayams
cd ayams
```

2. Follow the instructions in the ayams repository to create accounts

3. After registration, copy the generated account folders to this project:
```bash
cp -r ayams/accounts/* vkserbot.v2/accounts/
```

## Installation

### Linux/Mac

```bash
# Clone repository
git clone https://github.com/ayamgorengkecap/vkserbot.v2
cd vkserbot.v2

# Create virtual environment with Python 3.11
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Termux (Android)

```bash
# Clone repository
git clone https://github.com/ayamgorengkecap/vkserbot.v2
cd vkserbot.v2

# Create virtual environment
python -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Note:** Always activate the virtual environment before running the bot.

## Usage

### Activate Virtual Environment

Before running the bot, you must activate the virtual environment:

**Linux/Mac:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

You'll see `(venv)` prefix in your terminal when activated.

### Run the Bot

**Linux/Mac:**
```bash
python3 main.py
```

**Termux:**
```bash
python main.py
```

### Deactivate Virtual Environment

When you're done:
```bash
deactivate
```

## License

MIT License
