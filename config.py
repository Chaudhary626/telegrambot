"""
Configuration Module
====================
Loads settings from .env file or environment variables.
All sensitive data (tokens, passwords) should be in .env file.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# ──────────────────────────────────────────────
# Telegram Bot Settings
# ──────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
# The numeric channel ID, e.g. -1001234567890
try:
    TG_CHANNEL_ID = int(os.getenv("TG_CHANNEL_ID", "0"))
except ValueError:
    TG_CHANNEL_ID = 0

# ──────────────────────────────────────────────
# MySQL Database Settings (Hostinger compatible)
# ──────────────────────────────────────────────
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "telegram_bot")

# ──────────────────────────────────────────────
# Stream API / MTProto Settings
# ──────────────────────────────────────────────
# Get API_ID and API_HASH from https://my.telegram.org → API Development Tools
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
# URL of your deployed stream_api.py service on Render
STREAM_API_URL = os.getenv("STREAM_API_URL", "")
# Secret key to protect stream URLs (must match stream_api.py's STREAM_SECRET)
STREAM_SECRET = os.getenv("STREAM_SECRET", "")

# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────
def validate_config():
    """Check that all required settings are configured."""
    errors = []

    if not BOT_TOKEN:
        errors.append("BOT_TOKEN is not set")
    if ADMIN_ID == 0:
        errors.append("ADMIN_ID is not set")
    if TG_CHANNEL_ID == 0:
        errors.append("TG_CHANNEL_ID is not set")
    if API_ID == 0:
        errors.append("API_ID is not set")
    if not API_HASH:
        errors.append("API_HASH is not set")
    if not DB_PASSWORD:
        errors.append("DB_PASSWORD is not set (warning: empty password)")

    if errors:
        print("⚠️  Configuration Issues:")
        for err in errors:
            print(f"   • {err}")
        print("   → Edit your .env file to fix these.\n")

    return len(errors) == 0
