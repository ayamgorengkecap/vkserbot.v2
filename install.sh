#!/bin/bash
#
# VKSBot Installer
# Automatically sets up Python environment and dependencies
#

set -e

echo "╔══════════════════════════════════════════╗"
echo "║         VKSBot Installer v1.0            ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check Python
echo -n "Checking Python... "
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    echo -e "${GREEN}Found Python $PYTHON_VERSION${NC}"
else
    echo -e "${RED}Python3 not found!${NC}"
    echo "Please install Python 3.8+ first"
    exit 1
fi

# Create virtual environment
echo -n "Creating virtual environment... "
if [ -d "venv" ]; then
    echo -e "${YELLOW}Already exists${NC}"
else
    python3 -m venv venv
    echo -e "${GREEN}Done${NC}"
fi

# Activate venv
echo -n "Activating virtual environment... "
source venv/bin/activate
echo -e "${GREEN}Done${NC}"

# Upgrade pip
echo -n "Upgrading pip... "
pip install --upgrade pip -q
echo -e "${GREEN}Done${NC}"

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q
echo -e "${GREEN}Dependencies installed${NC}"

# Make scripts executable
chmod +x bot_simple.py bot.py main.py 2>/dev/null || true

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Installation Complete!           ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "To run the bot:"
echo ""
echo -e "  ${GREEN}source venv/bin/activate${NC}"
echo -e "  ${GREEN}python3 bot_simple.py${NC}"
echo ""
echo "Or for multi-threaded mode:"
echo ""
echo -e "  ${GREEN}python3 bot.py${NC}"
echo ""
