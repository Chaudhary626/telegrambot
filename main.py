"""
AnimeGalaxyHub — Unified Telegram Streaming Bot & API
=====================================================
Combines:
  1. Extractor Bot (receives videos/documents & JSON updates)
  2. Stream Server (FastAPI + Pyrogram MTProto for chunked streaming of 1GB-4GB files)
  3. Webhook Receiver (accepts and processes Telegram updates on a single port)
  4. Auto-Channel Sync (monitors channel posts, fuzzy-matches titles in DB, auto-inserts sources)

Run locally:
  python main.py

Run on Render:
  uvicorn main:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pyrogram import Client, raw
from pyrogram.file_id import FileId, FileType
from pyrogram.errors import FloodWait

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from dotenv import load_dotenv

# Load configurations
import config
from database import Database
from metadata import (
    extract_all_metadata,
    format_file_size,
    format_duration,
)

load_dotenv()

# ──────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("anime_galaxy_system")

# ──────────────────────────────────────────────
# System Instances
# ──────────────────────────────────────────────
db = Database()

# Pyrogram Client (Direct MTProto connection to Telegram DC)
pyrogram_client = Client(
    "stream_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,    # In-memory session data, does not write session file to disk
    no_updates=True,   # Keeps client lightweight (doesn't receive messages here)
)

# python-telegram-bot Application instance
telegram_app = Application.builder().token(config.BOT_TOKEN).build()

# Chunk size for streaming (1MB — Telegram maximum chunk size)
CHUNK_SIZE = 1024 * 1024


# ══════════════════════════════════════════════
#  BOT HELPER FUNCTIONS
# ══════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    """Verify if user is the authorized admin."""
    return user_id == config.ADMIN_ID


def generate_stream_url(file_id: str, file_size: int) -> str:
    """Generate a direct streaming link using the Render Stream API URL."""
    if not config.STREAM_API_URL or not config.STREAM_SECRET:
        return ""
    encoded_id = quote(file_id, safe="")
    return (
        f"{config.STREAM_API_URL.rstrip('/')}/stream/"
        f"{encoded_id}?key={config.STREAM_SECRET}&s={file_size}"
    )


def generate_player_url(file_id: str, file_size: int, title: str = "Video") -> str:
    """Generate an iframe player page link using the Render Stream API URL."""
    if not config.STREAM_API_URL or not config.STREAM_SECRET:
        return ""
    encoded_id = quote(file_id, safe="")
    encoded_title = quote(title, safe="")
    return (
        f"{config.STREAM_API_URL.rstrip('/')}/player/"
        f"{encoded_id}?key={config.STREAM_SECRET}&s={file_size}&title={encoded_title}"
    )


def build_info_message(data: dict, db_id: int = None) -> str:
    """Build a rich markdown message summarizing extracted file metadata."""
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
    """Build a plain text message detailing stream links & HTML embed codes."""
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
        lines.extend([f"💾 DB ID: {db_id}"])

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
    """Extract metadata properties from a telegram.Video object."""
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
    """Extract metadata properties from a telegram.Document object."""
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
    """Merge file properties with regex-detected metadata from name/caption."""
    meta = extract_all_metadata(text_source)
    file_data['quality'] = meta['quality']
    file_data['language'] = meta['language']
    file_data['episode'] = meta['episode']
    file_data['title'] = meta['title']
    file_data['caption'] = text_source
    return file_data


# ══════════════════════════════════════════════
#  BOT HANDLERS
# ══════════════════════════════════════════════

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
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
    """Handle /help command."""
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
    """Handle /last command."""
    if not is_admin(update.effective_user.id):
        return
    last_file = db.get_last_file()
    if not last_file:
        await update.message.reply_text("📭 No files saved yet.")
        return
    msg = build_info_message(last_file, db_id=last_file['id'])
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /count command."""
    if not is_admin(update.effective_user.id):
        return
    count = db.get_file_count()
    await update.message.reply_text(f"📊 Total files in database: *{count}*", parse_mode="Markdown")


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /search command."""
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


async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle private video messages."""
    if not update.message or not is_admin(update.effective_user.id):
        return
    video = update.message.video
    if not video:
        return
    await update.message.reply_text("⏳ Extracting file info...")
    try:
        file_data = extract_from_video(video)
        text_source = update.message.caption or ""
        if not text_source and video.file_name:
            text_source = video.file_name

        file_data = process_file_data(file_data, text_source)
        db_id = db.save_file(file_data)

        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)
    except Exception as e:
        logger.error(f"Error in handle_video: {e}", exc_info=True)
        await update.message.reply_text(f"❌ An error occurred:\n{type(e).__name__}: {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle private document messages."""
    if not update.message or not is_admin(update.effective_user.id):
        return
    document = update.message.document
    if not document:
        return
    filename = (document.file_name or "").lower()
    video_extensions = ('.mkv', '.mp4', '.avi', '.webm', '.mov', '.flv', '.wmv')
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
        file_data = extract_from_document(document)
        text_source = update.message.caption or document.file_name or ""

        file_data = process_file_data(file_data, text_source)
        db_id = db.save_file(file_data)

        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)
    except Exception as e:
        logger.error(f"Error in handle_document: {e}", exc_info=True)
        await update.message.reply_text(f"❌ An error occurred:\n{type(e).__name__}: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle pasting raw JSON logs from other channels."""
    if not update.message or not is_admin(update.effective_user.id):
        return
    text = update.message.text
    if not text:
        return

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return  # Ignore standard conversational text

    await update.message.reply_text("📋 Parsing JSON data...")
    file_data = None
    text_source = ""

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
        file_data = process_file_data(file_data, text_source)
        db_id = db.save_file(file_data)

        msg = build_info_message(file_data, db_id=db_id)
        await update.message.reply_text(msg, parse_mode="Markdown")

        stream_msg = build_stream_message(file_data, db_id=db_id)
        await update.message.reply_text(stream_msg)
    else:
        await update.message.reply_text("⚠️ JSON parsed, but no video/document data found.")


async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle updates containing new channel posts.
    If the post is from the configured TG_CHANNEL_ID and contains a video/document,
    process it, fuzzy-match with movies in the database, and save it directly
    as an active streaming source!
    """
    post = update.channel_post
    if not post:
        return

    # Check if this post is from the monitored channel
    if config.TG_CHANNEL_ID and post.chat.id != config.TG_CHANNEL_ID:
        logger.info(f"Skipping channel post from unmonitored channel: {post.chat.id}")
        return

    # Extract video or document
    video = post.video
    document = post.document
    animation = post.animation

    media = None
    file_type = ""

    if video:
        media = video
        file_type = "video"
    elif document:
        # Check if it's a video file extension
        filename = (document.file_name or "").lower()
        video_extensions = ('.mkv', '.mp4', '.avi', '.webm', '.mov', '.flv', '.wmv')
        is_video_mime = document.mime_type and document.mime_type.startswith('video/')
        is_video_ext = any(filename.endswith(ext) for ext in video_extensions)
        if is_video_mime or is_video_ext:
            media = document
            file_type = "document"
    elif animation:
        media = animation
        file_type = "animation"

    if not media:
        return

    logger.info(f"🎥 New video/document posted in channel: ID {post.message_id}")

    try:
        # Extract metadata
        size = media.file_size or 0
        duration = getattr(media, 'duration', 0) or 0
        width = getattr(media, 'width', 0) or 0
        height = getattr(media, 'height', 0) or 0

        # Title/caption to parse
        text_source = post.caption or ""
        if not text_source and getattr(media, 'file_name', None):
            text_source = media.file_name

        meta = extract_all_metadata(text_source)

        # 1. Fuzzy match movie by title in the database
        movie = db.find_movie_by_title(meta['title'])
        
        # Save to raw files database first as a backup record
        file_data = {
            'title': meta['title'],
            'file_id': media.file_id,
            'file_unique_id': media.file_unique_id,
            'quality': meta['quality'],
            'language': meta['language'],
            'episode': meta['episode'],
            'size': size,
            'duration': duration,
            'width': width,
            'height': height,
            'file_type': file_type,
            'caption': text_source
        }
        db_id = db.save_file(file_data)

        if movie:
            logger.info(f"✅ Found matching movie in DB: '{movie['title']}' (ID: {movie['id']})")
            
            # 2. Extract season/episode numbers
            # e.g., "S01E05" -> season=1, episode=5
            season = None
            episode = None
            if meta['episode'] and meta['episode'] != 'Unknown':
                m = re.match(r'S(\d+)E(\d+)', meta['episode'], re.IGNORECASE)
                if m:
                    season = int(m.group(1))
                    episode = int(m.group(2))
                else:
                    m2 = re.match(r'EP(\d+)', meta['episode'], re.IGNORECASE)
                    if m2:
                        season = 1  # Default to season 1 for EPXX format
                        episode = int(m2.group(1))

            # Build Render direct stream URL
            encoded_id = quote(media.file_id, safe="")
            stream_url = f"{config.STREAM_API_URL.rstrip('/')}/stream/{encoded_id}?key={config.STREAM_SECRET}&s={size}"

            # 3. Save as active streaming source directly
            source_data = {
                'movie_id': movie['id'],
                'season': season,
                'episode': episode,
                'language': meta['language'],
                'quality': meta['quality'],
                'telegram_file_id': media.file_id,
                'stream_url': stream_url,
                'file_size_mb': round(size / 1048576, 2),
                'duration_seconds': duration,
                'title': meta['title'],
                'stream_method': 'direct',
                'is_active': 1,
                'sort_order': 0
            }
            source_id = db.save_streaming_source(source_data)
            logger.info(f"🚀 Streaming source auto-created! ID: {source_id} for Movie: {movie['title']}")
        else:
            logger.warning(f"⚠️ No matching movie found in DB for title: '{meta['title']}'. File saved to files table (ID: {db_id}) for manual linking.")

    except Exception as e:
        logger.error(f"❌ Error in handle_channel_post: {e}", exc_info=True)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors and notify admin if applicable."""
    logger.error(f"Error: {context.error}", exc_info=context.error)
    if update and update.message:
        await update.message.reply_text(f"❌ An error occurred:\n`{str(context.error)[:200]}`", parse_mode="Markdown")


# Register handlers to PTB
telegram_app.add_handler(CommandHandler("start", cmd_start))
telegram_app.add_handler(CommandHandler("help", cmd_help))
telegram_app.add_handler(CommandHandler("last", cmd_last))
telegram_app.add_handler(CommandHandler("count", cmd_count))
telegram_app.add_handler(CommandHandler("search", cmd_search))
telegram_app.add_handler(MessageHandler(filters.VIDEO, handle_video))
telegram_app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_handler(MessageHandler(filters.ChatType.CHANNEL, handle_channel_post))
telegram_app.add_error_handler(error_handler)


# ══════════════════════════════════════════════
#  FASTAPI STREAM API LOGIC
# ══════════════════════════════════════════════

def decode_file_id(file_id_str: str):
    """Decode a Telegram file_id string into an InputFileLocation for Pyrogram MTProto invocation."""
    try:
        decoded = FileId.decode(file_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file_id")

    if decoded.file_type in (
        FileType.VIDEO,
        FileType.DOCUMENT,
        FileType.ANIMATION,
        FileType.VIDEO_NOTE,
        FileType.AUDIO,
        FileType.VOICE,
    ):
        location = raw.types.InputDocumentFileLocation(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
            thumb_size="",
        )
    elif decoded.file_type == FileType.PHOTO:
        location = raw.types.InputPhotoFileLocation(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
            thumb_size=decoded.thumb_size or "y",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {decoded.file_type}")

    return location, decoded


async def stream_file_chunks(location, start: int = 0, end: int = None):
    """Generator: requests chunks from Telegram MTProto via Pyrogram client and yields raw bytes."""
    aligned_offset = (start // CHUNK_SIZE) * CHUNK_SIZE
    skip_bytes = start - aligned_offset
    is_first_chunk = True
    current_offset = aligned_offset

    while True:
        if end is not None and current_offset > end:
            break

        try:
            result = await pyrogram_client.invoke(
                raw.functions.upload.GetFile(
                    location=location,
                    offset=current_offset,
                    limit=CHUNK_SIZE,
                )
            )
        except FloodWait as e:
            logger.warning(f"⏳ FloodWait: waiting {e.value}s")
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            logger.error(f"❌ Pyrogram MTProto stream error at offset {current_offset}: {e}")
            break

        data = bytes(result.bytes)
        if not data:
            break

        if is_first_chunk and skip_bytes > 0:
            data = data[skip_bytes:]
            is_first_chunk = False

        if end is not None:
            remaining = end - max(start, current_offset + skip_bytes) + 1
            if len(data) > remaining and remaining > 0:
                data = data[:remaining]

        if data:
            yield data

        current_offset += CHUNK_SIZE
        is_first_chunk = False

        if len(result.bytes) < CHUNK_SIZE:
            break


# ══════════════════════════════════════════════
#  FASTAPI LIFE CYCLE & SERVICE SETUP
# ══════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Asynchronous lifespan: handles starting/stopping Pyrogram and Bot clients."""
    # ── Step 1: Connect Database ──
    logger.info("📦 Connecting database...")
    db.connect()
    db.create_table()

    # ── Step 2: Start Pyrogram ──
    logger.info("🔌 Connecting Pyrogram (MTProto)...")
    await pyrogram_client.start()
    logger.info("✅ Pyrogram Client is online!")

    # ── Step 3: Start Telegram Bot ──
    logger.info("🤖 Starting Extractor Bot Application...")
    await telegram_app.initialize()
    await telegram_app.start()

    is_render = os.getenv("RENDER") is not None
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")

    if is_render and render_url:
        # Webhook mode: register our endpoint with Telegram
        webhook_url = f"{render_url}/webhook"
        logger.info(f"🌐 Setting Bot Webhook: {webhook_url}")
        await telegram_app.bot.set_webhook(
            url=webhook_url,
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        # Polling mode: start polling in background task (for Termux / local)
        logger.info("📡 Starting Bot in Polling Mode (local/testing)...")
        asyncio.create_task(telegram_app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        ))
        logger.info("✅ Background polling task initialized.")

    yield

    # ── Shutdown ──
    logger.info("🔒 Shutting down services...")
    if not (is_render and render_url):
        await telegram_app.updater.stop()
    await telegram_app.stop()
    await telegram_app.shutdown()
    await pyrogram_client.stop()
    db.close()
    logger.info("👋 System shutdown complete.")


app = FastAPI(title="Unified Telegram Streaming Server & Bot", lifespan=lifespan)

# Allow CORS for website players
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Range", "Content-Type"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
)


# ══════════════════════════════════════════════
#  FASTAPI ENDPOINTS
# ══════════════════════════════════════════════

@app.get("/")
async def health_check():
    """Health check endpoint to keep Render web service alive."""
    return {
        "status": "ok",
        "service": "unified-telegram-streaming-system",
        "pyrogram": "connected" if pyrogram_client.is_connected else "disconnected",
    }


@app.post("/webhook")
async def webhook_endpoint(request: Request):
    """Receive webhook POST updates from Telegram and push them to PTB Application loop."""
    try:
        update_data = await request.json()
        update = Update.de_json(update_data, telegram_app.bot)
        # Process task in background so we respond to Telegram immediately (avoiding retries)
        asyncio.create_task(telegram_app.process_update(update))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


@app.get("/stream/{file_id}")
async def stream_video(
    file_id: str,
    request: Request,
    key: str = "",
    s: int = 0,
):
    """
    MTProto range-enabled chunked video streaming endpoint.
    Bypasses Bot API 20MB limit by pulling bytes directly from Telegram DCs.
    """
    if key != config.STREAM_SECRET:
        raise HTTPException(status_code=403, detail="Access denied")

    location, decoded = decode_file_id(file_id)
    file_size = s if s > 0 else 0
    content_type = "video/mp4"

    range_header = request.headers.get("Range")

    if range_header and file_size > 0:
        range_spec = range_header.replace("bytes=", "").strip()
        parts = range_spec.split("-")
        range_start = int(parts[0]) if parts[0] else 0
        range_end = int(parts[1]) if (len(parts) > 1 and parts[1]) else file_size - 1

        range_start = max(0, range_start)
        range_end = min(range_end, file_size - 1)
        content_length = range_end - range_start + 1

        return StreamingResponse(
            stream_file_chunks(location, start=range_start, end=range_end),
            status_code=206,  # 206 Partial Content for range requests
            headers={
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
            },
            media_type=content_type,
        )
    else:
        headers = {
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        }
        if file_size > 0:
            headers["Content-Length"] = str(file_size)

        return StreamingResponse(
            stream_file_chunks(location),
            status_code=200,
            headers=headers,
            media_type=content_type,
        )


@app.get("/player/{file_id}", response_class=HTMLResponse)
async def player_page(
    file_id: str,
    key: str = "",
    s: int = 0,
    title: str = "Video Player",
):
    """Serves a beautiful, clean Plyr.js HTML5 video player page (suitable for iframe embed)."""
    if key != config.STREAM_SECRET:
        raise HTTPException(status_code=403, detail="Access denied")

    stream_url = f"/stream/{file_id}?key={key}&s={s}"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #0a0a0a;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        .player-container {{
            width: 100%;
            height: 100vh;
            position: relative;
        }}
        :root {{
            --plyr-color-main: #8b5cf6;
            --plyr-video-background: #0a0a0a;
        }}
        .plyr--video {{
            height: 100% !important;
            border-radius: 0;
        }}
        .loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-size: 1.1rem;
            z-index: 10;
            pointer-events: none;
            text-shadow: 0 2px 4px rgba(0,0,0,0.8);
        }}
        .loading.hidden {{ display: none; }}
    </style>
</head>
<body>
    <div class="player-container">
        <div class="loading" id="loading">Loading video...</div>
        <video id="player" playsinline controls crossorigin>
            <source src="{stream_url}" type="video/mp4" />
        </video>
    </div>

    <script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
    <script>
        const player = new Plyr('#player', {{
            controls: [
                'play-large', 'play', 'progress', 'current-time',
                'duration', 'mute', 'volume', 'settings',
                'pip', 'airplay', 'fullscreen'
            ],
            settings: ['quality', 'speed'],
            speed: {{ selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] }},
            keyboard: {{ focused: true, global: true }},
            tooltips: {{ controls: true, seek: true }},
        }});

        const loadingEl = document.getElementById('loading');
        player.on('ready', () => loadingEl.classList.add('hidden'));
        player.on('playing', () => loadingEl.classList.add('hidden'));
        player.on('error', () => {{
            loadingEl.textContent = 'Error loading video';
            loadingEl.classList.remove('hidden');
        }});
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


# ══════════════════════════════════════════════
#  RUNNER
# ══════════════════════════════════════════════

if __name__ == "__main__":
    # Validate the environment configuration before binding
    if not config.validate_config():
        print("❌ Configuration validation failed! Please check your .env parameters.")
    else:
        port = int(os.getenv("PORT", "8000"))
        logger.info(f"🚀 Launching Unified Service on port {port}")
        uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
