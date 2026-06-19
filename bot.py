"""
Telegram File ID Extractor Bot
================================
Main bot file — handles all Telegram interactions.

Features:
  • Extract file_id from forwarded videos/documents
  • Parse raw Telegram JSON
  • Auto-detect metadata (quality, language, episode)
  • Save to MySQL database
  • Admin-only access

Usage:
  python bot.py
"""

import asyncio
import json
import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

import config
from database import Database
from metadata import (
    extract_all_metadata,
    format_file_size,
    format_duration,
)

# ──────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Database Instance
# ──────────────────────────────────────────────
db = Database()


# ══════════════════════════════════════════════
#  HELPER FUNCTIONS
# ══════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    """Check if the user is the authorized admin."""
    return user_id == config.ADMIN_ID


def generate_stream_url(file_id: str, file_size: int) -> str:
    """
    Generate a direct streaming URL for the video.

    Uses the Stream API (stream_api.py on Render) which bypasses
    the 20MB Bot API limit via MTProto.

    The URL can be used directly in HTML5 <video> tags:
        <video src="STREAM_URL"></video>

    Args:
        file_id: Telegram file_id string
        file_size: File size in bytes (needed for Range/seeking support)

    Returns:
        Full stream URL, or empty string if Stream API is not configured.
    """
    if not config.STREAM_API_URL or not config.STREAM_SECRET:
        return ""

    from urllib.parse import quote
    encoded_id = quote(file_id, safe="")
    return (
        f"{config.STREAM_API_URL.rstrip('/')}/stream/"
        f"{encoded_id}?key={config.STREAM_SECRET}&s={file_size}"
    )


def generate_player_url(file_id: str, file_size: int, title: str = "Video") -> str:
    """
    Generate a player page URL (built-in Plyr.js player).

    Can be used in <iframe> embeds on the website.

    Args:
        file_id: Telegram file_id string
        file_size: File size in bytes
        title: Video title for the player page

    Returns:
        Full player URL, or empty string if Stream API is not configured.
    """
    if not config.STREAM_API_URL or not config.STREAM_SECRET:
        return ""

    from urllib.parse import quote
    encoded_id = quote(file_id, safe="")
    encoded_title = quote(title, safe="")
    return (
        f"{config.STREAM_API_URL.rstrip('/')}/player/"
        f"{encoded_id}?key={config.STREAM_SECRET}&s={file_size}&title={encoded_title}"
    )


def build_info_message(data: dict, db_id: int = None) -> str:
    """
    Build a nicely formatted info message from extracted data.

    Args:
        data: Dictionary with file metadata.
        db_id: Database row ID (if saved).

    Returns:
        Formatted string ready to send as Telegram message.
    """
    file_size = data.get('size', 0)

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "📁 *FILE EXTRACTED SUCCESSFULLY*",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"📌 *Title:* `{data.get('title', 'Untitled')}`",
        f"🎬 *Type:* `{data.get('file_type', 'Unknown')}`",
        "",
        "───── *Technical IDs* ─────",
        f"🆔 *file\\_id:*",
        f"`{data.get('file_id', 'N/A')}`",
        "",
        f"🔑 *file\\_unique\\_id:*",
        f"`{data.get('file_unique_id', 'N/A')}`",
        "",
        "───── *Details* ─────",
        f"📏 *Size:* `{format_file_size(file_size)}` ({file_size} bytes)",
        f"⏱ *Duration:* `{format_duration(data.get('duration', 0))}`",
        f"📐 *Resolution:* `{data.get('width', 0)} × {data.get('height', 0)}`",
        "",
        "───── *Metadata* ─────",
        f"🎞 *Quality:* `{data.get('quality', 'Unknown')}`",
        f"🗣 *Language:* `{data.get('language', 'Unknown')}`",
        f"📺 *Episode:* `{data.get('episode', 'Unknown')}`",
    ]

    if db_id:
        lines.extend([
            "",
            "───── *Database* ─────",
            f"💾 *Saved with ID:* `{db_id}`",
        ])

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def build_stream_message(data: dict, db_id: int = None) -> str:
    """
    Build a PLAIN TEXT message with technical IDs and stream URLs.

    This message is ALWAYS sent (not conditional on stream config).
    Sent as plain text (no parse_mode) to avoid Markdown issues.

    Args:
        data: Dictionary with file metadata.
        db_id: Database row ID.

    Returns:
        Plain text string with technical details.
    """
    file_id = data.get('file_id', 'N/A')
    file_unique_id = data.get('file_unique_id', 'N/A')
    file_size = data.get('size', 0)
    title = data.get('title', 'Video')

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔧 TECHNICAL DATA",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "🆔 file_id:",
        file_id,
        "",
        "🔑 file_unique_id:",
        file_unique_id,
        "",
        f"📏 Size: {file_size} bytes ({format_file_size(file_size)})",
        f"🎬 Type: {data.get('file_type', 'Unknown')}",
    ]

    if db_id:
        lines.extend([
            f"💾 DB ID: {db_id}",
        ])

    # ── Stream URLs (if configured) ──
    stream_url = generate_stream_url(file_id, file_size)
    player_url = generate_player_url(file_id, file_size, title)

    if stream_url:
        lines.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🔗 STREAM LINKS",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
            "▶️ Direct Stream URL:",
            stream_url,
            "",
            "🎬 Player Page URL:",
            player_url,
            "",
            "━━━ 📋 EMBED CODE ━━━",
            "",
            "HTML5 Video:",
            f'<video controls src="{stream_url}"></video>',
            "",
            "iFrame Player:",
            f'<iframe src="{player_url}" width="100%" height="500" frameborder="0" allowfullscreen></iframe>',
        ])

        if db_id:
            lines.extend([
                "",
                "🌐 Website Link:",
                f"https://animegalaxyhub.com/watch.php?id={db_id}",
            ])
    else:
        lines.extend([
            "",
            "⚠️ Stream links not available.",
            "Set STREAM_API_URL & STREAM_SECRET in .env to enable.",
        ])

    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def extract_from_video(video) -> dict:
    """
    Extract metadata from a Telegram Video object.

    Args:
        video: telegram.Video object

    Returns:
        Dictionary with extracted data.
    """
    return {
        'file_id': video.file_id,
        'file_unique_id': video.file_unique_id,
        'size': video.file_size or 0,
        'duration': video.duration or 0,
        'width': video.width or 0,
        'height': video.height or 0,
        'file_type': 'video',
    }


def extract_from_document(document) -> dict:
    """
    Extract metadata from a Telegram Document object.

    Args:
        document: telegram.Document object

    Returns:
        Dictionary with extracted data.
    """
    return {
        'file_id': document.file_id,
        'file_unique_id': document.file_unique_id,
        'size': document.file_size or 0,
        'duration': 0,
        'width': 0,
        'height': 0,
        'file_type': 'document',
    }


def process_file_data(file_data: dict, text_source: str) -> dict:
    """
    Merge file data with metadata extracted from filename/caption.

    Args:
        file_data: Raw file data (file_id, size, etc.)
        text_source: Filename or caption to parse for metadata.

    Returns:
        Complete data dictionary ready for database.
    """
    # Extract metadata from the text
    meta = extract_all_metadata(text_source)

    # Merge: file_data takes priority, metadata fills in the rest
    file_data['quality'] = meta['quality']
    file_data['language'] = meta['language']
    file_data['episode'] = meta['episode']
    file_data['title'] = meta['title']
    file_data['caption'] = text_source

    return file_data


# ══════════════════════════════════════════════
#  COMMAND HANDLERS
# ══════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — welcome message."""
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("⛔ Unauthorized. This bot is private.")
        return

    welcome = (
        "🤖 *File ID Extractor Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Welcome\\! I extract `file_id` and metadata\n"
        "from videos you forward to me\\.\n\n"
        "*How to use:*\n"
        "1️⃣ Forward a video from any channel\n"
        "2️⃣ Send a video/document directly\n"
        "3️⃣ Paste raw Telegram JSON\n\n"
        "Type /help for all commands\\.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(welcome, parse_mode="MarkdownV2")


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command — show usage instructions."""
    if not is_admin(update.effective_user.id):
        return

    help_text = (
        "📖 *HELP \\- Commands & Usage*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Commands:*\n"
        "/start — Welcome message\n"
        "/help — This help menu\n"
        "/last — Show last saved file\n"
        "/count — Total files in database\n"
        "/search `<query>` — Search files\n\n"
        "*Supported inputs:*\n"
        "• Forward a video from channel\n"
        "• Send a video file directly\n"
        "• Send a document \\(\\.mkv, \\.mp4\\)\n"
        "• Paste raw Telegram JSON\n\n"
        "*Auto\\-detected metadata:*\n"
        "• Quality \\(480p/720p/1080p/4K\\)\n"
        "• Language \\(Hindi/English/Dual\\)\n"
        "• Episode \\(S01E01, EP01\\)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    await update.message.reply_text(help_text, parse_mode="MarkdownV2")


async def cmd_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /last command — show the most recently saved file."""
    if not is_admin(update.effective_user.id):
        return

    last_file = db.get_last_file()

    if not last_file:
        await update.message.reply_text("📭 No files saved yet.")
        return

    msg = build_info_message(last_file, db_id=last_file['id'])
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /count command — show total files in database."""
    if not is_admin(update.effective_user.id):
        return

    count = db.get_file_count()
    await update.message.reply_text(f"📊 Total files in database: *{count}*", parse_mode="Markdown")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command — search files by title."""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage: /search <query>\nExample: /search Naruto")
        return

    query = " ".join(context.args)
    results = db.search_files(query)

    if not results:
        await update.message.reply_text(f"🔍 No results found for: *{query}*", parse_mode="Markdown")
        return

    lines = [f"🔍 *Search Results for:* `{query}`\n"]
    for i, file in enumerate(results, 1):
        lines.append(
            f"*{i}.* `{file['title']}`\n"
            f"   Quality: {file['quality']} | EP: {file['episode']}\n"
            f"   ID: `{file['file_id'][:30]}...`\n"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ══════════════════════════════════════════════
#  MESSAGE HANDLERS
# ══════════════════════════════════════════════

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle received video messages.
    Works for both directly sent and forwarded videos.
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    video = update.message.video
    if not video:
        return

    await update.message.reply_text("⏳ Extracting file info...")

    try:
        # Extract raw file data
        file_data = extract_from_video(video)

        # Get text source for metadata (caption or filename)
        text_source = update.message.caption or ""
        if not text_source and video.file_name:
            text_source = video.file_name

        # Process and merge metadata
        file_data = process_file_data(file_data, text_source)

        # Save to database
        db_id = db.save_file(file_data)

        # Message 1: File info with Markdown
        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        # Message 2: Technical data + stream links (plain text)
        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)

        logger.info(f"Extracted video: {file_data['title']} (ID: {db_id})")

    except Exception as e:
        logger.error(f"Error in handle_video: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred:\n{type(e).__name__}: {e}"
        )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle received document messages.
    Filters for video file extensions (.mkv, .mp4, .avi, .webm, .mov).
    """
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Unauthorized.")
        return

    document = update.message.document
    if not document:
        return

    # Check if it's a video file
    video_extensions = ('.mkv', '.mp4', '.avi', '.webm', '.mov', '.flv', '.wmv')
    filename = (document.file_name or "").lower()

    is_video_mime = document.mime_type and document.mime_type.startswith('video/')
    is_video_ext = any(filename.endswith(ext) for ext in video_extensions)

    if not is_video_mime and not is_video_ext:
        await update.message.reply_text(
            "⚠️ This doesn't look like a video file.\n"
            "Supported: .mkv, .mp4, .avi, .webm, .mov"
        )
        return

    await update.message.reply_text("⏳ Extracting file info...")

    try:
        # Extract raw file data
        file_data = extract_from_document(document)

        # Get text source for metadata
        text_source = update.message.caption or document.file_name or ""

        # Process and merge metadata
        file_data = process_file_data(file_data, text_source)

        # Save to database
        db_id = db.save_file(file_data)

        # Message 1: File info with Markdown
        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        # Message 2: Technical data + stream links (plain text)
        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)

        logger.info(f"Extracted document: {file_data['title']} (ID: {db_id})")

    except Exception as e:
        logger.error(f"Error in handle_document: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ An error occurred:\n{type(e).__name__}: {e}"
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle text messages — parses raw Telegram JSON.

    If the text looks like JSON and contains a video/document object,
    extract the file_id and metadata from it.
    """
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text
    if not text:
        return

    # Try to detect and parse JSON
    # Sometimes JSON is wrapped in code blocks
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove markdown code blocks
        cleaned = cleaned.strip("`")
        # Remove optional language label (e.g., "json")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    # Attempt JSON parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        # Not JSON — ignore (don't spam the user)
        return

    await update.message.reply_text("📋 Parsing JSON data...")

    # Try to find video data in the JSON
    file_data = None
    text_source = ""

    # Case 1: Direct video object
    if 'video' in data:
        vid = data['video']
        file_data = {
            'file_id': vid.get('file_id', ''),
            'file_unique_id': vid.get('file_unique_id', ''),
            'size': vid.get('file_size', 0),
            'duration': vid.get('duration', 0),
            'width': vid.get('width', 0),
            'height': vid.get('height', 0),
            'file_type': 'video',
        }
        text_source = data.get('caption', vid.get('file_name', ''))

    # Case 2: Direct document object
    elif 'document' in data:
        doc = data['document']
        file_data = {
            'file_id': doc.get('file_id', ''),
            'file_unique_id': doc.get('file_unique_id', ''),
            'size': doc.get('file_size', 0),
            'duration': 0,
            'width': 0,
            'height': 0,
            'file_type': 'document',
        }
        text_source = data.get('caption', doc.get('file_name', ''))

    # Case 3: Nested in message object
    elif 'message' in data:
        msg_obj = data['message']

        if 'video' in msg_obj:
            vid = msg_obj['video']
            file_data = {
                'file_id': vid.get('file_id', ''),
                'file_unique_id': vid.get('file_unique_id', ''),
                'size': vid.get('file_size', 0),
                'duration': vid.get('duration', 0),
                'width': vid.get('width', 0),
                'height': vid.get('height', 0),
                'file_type': 'video',
            }
            text_source = msg_obj.get('caption', vid.get('file_name', ''))

        elif 'document' in msg_obj:
            doc = msg_obj['document']
            file_data = {
                'file_id': doc.get('file_id', ''),
                'file_unique_id': doc.get('file_unique_id', ''),
                'size': doc.get('file_size', 0),
                'duration': 0,
                'width': 0,
                'height': 0,
                'file_type': 'document',
            }
            text_source = msg_obj.get('caption', doc.get('file_name', ''))

    # Case 4: Raw file_id in the JSON
    elif 'file_id' in data:
        file_data = {
            'file_id': data.get('file_id', ''),
            'file_unique_id': data.get('file_unique_id', ''),
            'size': data.get('file_size', 0),
            'duration': data.get('duration', 0),
            'width': data.get('width', 0),
            'height': data.get('height', 0),
            'file_type': data.get('type', 'unknown'),
        }
        text_source = data.get('file_name', data.get('caption', ''))

    if file_data and file_data.get('file_id'):
        # Process and merge metadata
        file_data = process_file_data(file_data, text_source)

        # Save to database
        db_id = db.save_file(file_data)

        # Message 1: File info with Markdown
        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        # Message 2: Technical data + stream links (plain text)
        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)

        logger.info(f"Parsed JSON: {file_data['title']} (ID: {db_id})")
    else:
        await update.message.reply_text(
            "⚠️ JSON parsed, but no video/document data found.\n\n"
            "Expected format:\n"
            '`{"video": {"file_id": "...", ...}}`\n'
            "or\n"
            '`{"message": {"video": {...}}}`',
            parse_mode="Markdown"
        )


async def handle_unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any unrecognized messages from admin."""
    if not is_admin(update.effective_user.id):
        return

    await update.message.reply_text(
        "🤔 I don't understand this.\n\n"
        "Please send me:\n"
        "• A forwarded video\n"
        "• A video/document file\n"
        "• Raw Telegram JSON\n\n"
        "Type /help for more info."
    )


# ══════════════════════════════════════════════
#  ERROR HANDLER
# ══════════════════════════════════════════════

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify admin."""
    logger.error(f"Error: {context.error}", exc_info=context.error)

    if update and update.message:
        await update.message.reply_text(
            f"❌ An error occurred:\n`{str(context.error)[:200]}`",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════
#  MAIN — Start the Bot
# ══════════════════════════════════════════════

def build_app() -> Application:
    """
    Build the bot application with all handlers registered.

    Returns:
        Configured Application instance (not yet running).
    """
    app = Application.builder().token(config.BOT_TOKEN).build()

    # Register command handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("last", cmd_last))
    app.add_handler(CommandHandler("count", cmd_count))
    app.add_handler(CommandHandler("search", cmd_search))

    # Register message handlers (order matters!)
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Register error handler
    app.add_error_handler(error_handler)

    return app


def main():
    """
    Initialize and start the bot.

    Auto-detects the environment:
      • Render → runs in WEBHOOK mode (receives updates via HTTPS)
      • Termux / Local → runs in POLLING mode (fetches updates periodically)
    """

    # Fix for Python 3.14+ (no implicit event loop creation)
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    print("=" * 50)
    print("  📡 Telegram File ID Extractor Bot")
    print("=" * 50)
    print()

    # ── Step 1: Validate configuration ──
    if not config.validate_config():
        print("❌ Fix configuration issues before starting.")
        print("   Edit the .env file with your settings.")
        return

    print(f"👤 Admin ID: {config.ADMIN_ID}")
    print()

    # ── Step 2: Connect to database ──
    print("📦 Connecting to database...")
    if not db.connect():
        print("❌ Cannot start without database connection.")
        print("   Check your MySQL settings in .env")
        return

    # ── Step 3: Create table if needed ──
    db.create_table()
    print()

    # ── Step 4: Build the bot application ──
    print("🤖 Starting bot...")
    app = build_app()

    # ── Step 5: Detect environment and run ──
    # Render sets the RENDER env var automatically
    is_render = os.getenv("RENDER") is not None
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    port = int(os.getenv("PORT", "10000"))

    if is_render and render_url:
        # ─── WEBHOOK MODE (Render) ───
        webhook_url = f"{render_url}/webhook"
        print(f"🌐 Running in WEBHOOK mode (Render)")
        print(f"   URL: {webhook_url}")
        print(f"   Port: {port}")
        print("=" * 50)

        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        # ─── POLLING MODE (Termux / Local) ───
        print("📡 Running in POLLING mode (Termux/Local)")
        print("✅ Bot is running! Press Ctrl+C to stop.")
        print("=" * 50)

        app.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )

    # Cleanup on exit
    db.close()


if __name__ == "__main__":
    main()

