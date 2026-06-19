# 📡 Telegram File ID Extractor Bot

A lightweight Telegram bot that extracts `file_id` and metadata from videos — built to run on **Termux (Android)** with **MySQL (Hostinger)** storage.

---

## 📁 Project Structure

```
telegram-bot/
├── bot.py              # Main bot (entry point)
├── config.py           # Configuration loader
├── database.py         # MySQL database operations
├── metadata.py         # Metadata extraction (quality, language, episode)
├── requirements.txt    # Python dependencies
├── schema.sql          # MySQL table creation script
├── .env.example        # Environment variables template
├── .env                # Your actual settings (create this)
└── README.md           # This file
```

---

## 🚀 Step-by-Step Termux Setup Guide

### Step 1: Install Termux
- Download **Termux** from [F-Droid](https://f-droid.org/en/packages/com.termux/) (NOT from Play Store)
- Open Termux

### Step 2: Update & Install Python
```bash
# Update packages
pkg update && pkg upgrade -y

# Install Python and Git
pkg install python git -y

# Verify installation
python --version
pip --version
```

### Step 3: Clone or Copy the Bot Files
```bash
# Option A: If you have the files on your phone
cd /storage/emulated/0/Download/telegram-bot

# Option B: Create directory and copy files manually
mkdir -p ~/telegram-bot
cd ~/telegram-bot
# Copy all .py files, requirements.txt, .env.example here
```

### Step 4: Install Dependencies
```bash
cd ~/telegram-bot
pip install -r requirements.txt
```

This installs:
- `python-telegram-bot` — Telegram Bot API wrapper
- `PyMySQL` — Pure Python MySQL connector (no C compilation needed!)
- `python-dotenv` — Loads `.env` file

### Step 5: Create Your Telegram Bot
1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Follow the prompts to name your bot
4. Copy the **bot token** (looks like: `123456:ABC-DEF1234...`)

### Step 6: Get Your Telegram User ID
1. Open Telegram, search for **@userinfobot**
2. Send `/start`
3. It will reply with your **user ID** (a number like `123456789`)

### Step 7: Setup MySQL on Hostinger
1. Login to [Hostinger hPanel](https://hpanel.hostinger.com)
2. Go to **Databases** → **MySQL Databases**
3. Create a new database (e.g., `u123456789_telegram`)
4. Note down:
   - **Host** (e.g., `sql123.byethost.com` or `localhost`)
   - **Database name**
   - **Username**
   - **Password**
5. Open **phpMyAdmin** and run the contents of `schema.sql`

### Step 8: Configure the Bot
```bash
# Copy the example env file
cp .env.example .env

# Edit with nano (or any text editor)
nano .env
```

Fill in your values:
```env
BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
ADMIN_ID=123456789
DB_HOST=sql123.byethost.com
DB_PORT=3306
DB_USER=u123456789_admin
DB_PASSWORD=your_secure_password
DB_NAME=u123456789_telegram
```

Save and exit (`Ctrl+X`, then `Y`, then `Enter`).

### Step 9: Run the Bot
```bash
cd ~/telegram-bot
python bot.py
```

You should see:
```
==================================================
  📡 Telegram File ID Extractor Bot
==================================================

👤 Admin ID: 123456789

📦 Connecting to database...
✅ Database connected successfully!
✅ Table 'files' is ready!

🤖 Starting bot...
✅ Bot is running! Press Ctrl+C to stop.
==================================================
```

### Step 10: Keep Bot Running (Optional)
To keep the bot running after closing Termux:
```bash
# Install tmux
pkg install tmux -y

# Start a new tmux session
tmux new -s bot

# Run the bot inside tmux
python bot.py

# Detach from tmux: press Ctrl+B, then D

# Reattach later:
tmux attach -t bot
```

---

## 🎯 How to Use the Bot

### Forward a Video
1. Go to any Telegram channel with videos
2. Long-press on a video message
3. Tap **Forward** → Select your bot
4. The bot will extract all info and save to database

### Send a Video/Document
1. Open chat with your bot
2. Send any `.mp4` or `.mkv` file
3. Bot extracts info automatically

### Paste Raw JSON
1. Forward a message to **@RawDataBot**
2. Copy the JSON response
3. Paste it into your bot chat
4. Bot parses and extracts the file_id

### Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Usage instructions |
| `/last` | Show last saved file |
| `/count` | Total files in database |
| `/search <query>` | Search files by title |

---

## 📋 Example Usage

### Example 1: Forward a Video

**You forward:** A video from your anime channel with caption:
```
Naruto Shippuden S01E05 720p Hindi Dubbed [AnimeFlix]
```

**Bot replies:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 FILE EXTRACTED SUCCESSFULLY
━━━━━━━━━━━━━━━━━━━━━━━━━━

📌 Title: Naruto Shippuden
🎬 Type: video

🆔 file_id:
BAACAgIAAxkBAAIBZ2X...

🔑 file_unique_id:
AgADBAADqKcxG...

───── Details ─────
📏 Size: 450.23 MB
⏱ Duration: 23:45
📐 Resolution: 1280 × 720

───── Metadata ─────
🎞 Quality: 720p
🗣 Language: Hindi
📺 Episode: S01E05

───── Database ─────
💾 Saved with ID: 42

━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Example 2: Paste JSON from @RawDataBot

**You paste:**
```json
{
  "message": {
    "video": {
      "file_id": "BAACAgIAAxkBAAIBZ...",
      "file_unique_id": "AgADBAAD...",
      "file_size": 524288000,
      "duration": 1425,
      "width": 1920,
      "height": 1080
    },
    "caption": "One Piece EP1000 1080p Dual Audio"
  }
}
```

**Bot extracts:**
- Quality: `1080p`
- Language: `Dual Audio`
- Episode: `EP1000`
- Saves to database ✅

### Example 3: Send a Document (.mkv)

**You send:** `Attack.on.Titan.S04E28.1080p.Dual.Audio.x265.mkv`

**Bot detects:**
- Title: `Attack on Titan`
- Quality: `1080p`
- Language: `Dual Audio`
- Episode: `S04E28`

---

## 🔧 Using file_id in Your Website

Once extracted, use the `file_id` in your website's streaming system:

```javascript
// Example: Generate a streaming URL using your backend API
const streamUrl = `https://yoursite.com/api/stream?file_id=${fileId}`;

// Or use it directly with Telegram Bot API
const telegramUrl = `https://api.telegram.org/bot${BOT_TOKEN}/getFile?file_id=${fileId}`;
```

---

## ⚠️ Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `Database connection failed` | Check DB_HOST, DB_USER, DB_PASSWORD in `.env` |
| `Bot token invalid` | Get a new token from @BotFather |
| `Unauthorized` | Make sure ADMIN_ID matches your Telegram user ID |
| `pymysql.err.OperationalError` | Hostinger may block remote MySQL — check their docs |
| Bot stops when Termux closes | Use `tmux` (see Step 10 above) |

---

## 📝 Notes

- **No VPS needed** — runs entirely on your phone via Termux
- **Lightweight** — uses only ~30MB RAM
- **Large files supported** — `file_id` extraction works for files of any size (no download needed)
- **Pure Python** — no C compilation required, perfect for Termux
- **Hostinger compatible** — uses standard MySQL protocol

---

## 📜 License

This project is for personal use. Built for managing Telegram video file_ids for anime/movie streaming websites.
