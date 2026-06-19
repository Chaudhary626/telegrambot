"""
Telegram Video Stream API
=========================
Streams video files from Telegram using MTProto protocol (via Pyrogram).
Supports large files (1GB+) with HTTP Range requests for seeking.

Features:
  • Stream any Telegram video by file_id
  • HTTP Range support (seeking/scrubbing in player)
  • Built-in video player page (Plyr.js)
  • API key authentication
  • CORS configured for your website

Deploy as a Render Web Service (can be same or separate from bot).

Run locally:
  python stream_api.py

Run on Render:
  uvicorn stream_api:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from pyrogram import Client, raw
from pyrogram.file_id import FileId, FileType
from pyrogram.errors import FloodWait

from dotenv import load_dotenv

load_dotenv()

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

# Bot token (same one from @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Get these from https://my.telegram.org → API Development Tools
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")

# Secret key to protect streaming endpoint (make this long and random)
STREAM_SECRET = os.getenv("STREAM_SECRET", "change_this_to_a_random_string")

# Your website domain (for CORS)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "https://animegalaxyhub.com,http://localhost"
).split(",")

# Chunk size for streaming (1MB — Telegram maximum per request)
CHUNK_SIZE = 1024 * 1024  # 1,048,576 bytes

# ──────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Pyrogram Client (connects to Telegram via MTProto)
# ──────────────────────────────────────────────
bot = Client(
    "stream_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,    # Don't save session file to disk
    no_updates=True,   # We don't need to receive messages
)


# ══════════════════════════════════════════════
#  APP SETUP
# ══════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start Pyrogram when app starts, stop when app shuts down."""
    logger.info("🔌 Connecting to Telegram...")
    await bot.start()
    logger.info("✅ Telegram connected! Stream API is ready.")
    yield
    await bot.stop()
    logger.info("🔒 Telegram disconnected.")


app = FastAPI(title="Telegram Video Stream API", lifespan=lifespan)

# Allow your website to load videos from this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Range", "Content-Type"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
)


# ══════════════════════════════════════════════
#  STREAMING LOGIC
# ══════════════════════════════════════════════

def decode_file_id(file_id_str: str):
    """
    Decode a Telegram file_id string into an InputFileLocation.

    This is needed to request file chunks from Telegram's MTProto API.
    The file_id contains: media_id, access_hash, file_reference, dc_id.

    Returns:
        Tuple of (InputFileLocation, decoded FileId object)
    """
    try:
        decoded = FileId.decode(file_id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid file_id")

    # Build the correct InputFileLocation based on file type
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
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {decoded.file_type}",
        )

    return location, decoded


async def stream_file_chunks(location, start: int = 0, end: int = None):
    """
    Generator: yields file data chunks from Telegram via MTProto.

    Handles:
      • Offset alignment (Telegram requires offsets divisible by CHUNK_SIZE)
      • Trimming first/last chunks to match exact Range request
      • FloodWait errors (auto-retry after delay)

    Args:
        location: InputFileLocation from decode_file_id()
        start: First byte to include (from Range header)
        end: Last byte to include (from Range header), or None for full file
    """
    # Align the starting offset down to the nearest chunk boundary
    # Telegram requires offset to be divisible by chunk size
    aligned_offset = (start // CHUNK_SIZE) * CHUNK_SIZE
    skip_bytes = start - aligned_offset  # Bytes to skip in first chunk
    is_first_chunk = True

    current_offset = aligned_offset

    while True:
        # Stop if we've passed the end
        if end is not None and current_offset > end:
            break

        try:
            result = await bot.invoke(
                raw.functions.upload.GetFile(
                    location=location,
                    offset=current_offset,
                    limit=CHUNK_SIZE,
                )
            )
        except FloodWait as e:
            # Telegram rate limit — wait and retry
            logger.warning(f"⏳ FloodWait: waiting {e.value}s")
            await asyncio.sleep(e.value)
            continue
        except Exception as e:
            logger.error(f"❌ Stream error at offset {current_offset}: {e}")
            break

        data = bytes(result.bytes)
        if not data:
            break  # End of file

        # ── Trim first chunk: skip bytes before 'start' ──
        if is_first_chunk and skip_bytes > 0:
            data = data[skip_bytes:]
            is_first_chunk = False

        # ── Trim last chunk: remove bytes after 'end' ──
        if end is not None:
            bytes_sent_so_far = current_offset + CHUNK_SIZE  # approximate
            remaining = end - max(start, current_offset + skip_bytes) + 1
            if len(data) > remaining and remaining > 0:
                data = data[:remaining]

        if data:
            yield data

        current_offset += CHUNK_SIZE
        is_first_chunk = False

        # If we got less data than requested, we've hit EOF
        if len(result.bytes) < CHUNK_SIZE:
            break


# ══════════════════════════════════════════════
#  API ENDPOINTS
# ══════════════════════════════════════════════

@app.get("/")
async def health_check():
    """Health check — keeps Render service alive."""
    return {"status": "ok", "service": "telegram-stream-api"}


@app.get("/stream/{file_id}")
async def stream_video(
    file_id: str,
    request: Request,
    key: str = "",
    s: int = 0,
):
    """
    Stream a video file from Telegram.

    URL format:
      /stream/{file_id}?key=YOUR_SECRET&s=FILE_SIZE_BYTES

    Args:
        file_id: Telegram file_id (from the bot's database)
        key: STREAM_SECRET for authentication
        s: File size in bytes (needed for Range/seeking support)
    """
    # ── Authenticate ──
    if key != STREAM_SECRET:
        raise HTTPException(status_code=403, detail="Access denied")

    # ── Decode file_id ──
    location, decoded = decode_file_id(file_id)

    # ── File size (passed from website, stored in DB) ──
    file_size = s if s > 0 else 0

    # ── Content type ──
    content_type = "video/mp4"

    # ── Parse Range header for seeking ──
    range_header = request.headers.get("Range")

    if range_header and file_size > 0:
        # Example: "bytes=1048576-2097151"
        range_spec = range_header.replace("bytes=", "").strip()
        parts = range_spec.split("-")

        range_start = int(parts[0]) if parts[0] else 0
        range_end = int(parts[1]) if (len(parts) > 1 and parts[1]) else file_size - 1

        # Clamp to valid range
        range_start = max(0, range_start)
        range_end = min(range_end, file_size - 1)
        content_length = range_end - range_start + 1

        return StreamingResponse(
            stream_file_chunks(location, start=range_start, end=range_end),
            status_code=206,  # Partial Content
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
        # ── No Range — stream entire file ──
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
    """
    Serve a beautiful embedded video player page.

    Use this in an <iframe> on your website:
      <iframe src="https://your-stream.onrender.com/player/FILE_ID?key=SECRET&s=SIZE"></iframe>

    Args:
        file_id: Telegram file_id
        key: STREAM_SECRET
        s: File size in bytes
        title: Video title (shown in player)
    """
    if key != STREAM_SECRET:
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
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }}
        .player-container {{
            width: 100%;
            max-width: 100%;
            position: relative;
        }}
        /* Custom Plyr theme */
        :root {{
            --plyr-color-main: #8b5cf6;
            --plyr-video-background: #0a0a0a;
        }}
        .plyr--video {{
            border-radius: 0;
        }}
        /* Loading indicator */
        .loading {{
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            color: #fff;
            font-size: 1.2rem;
            z-index: 10;
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

        // Hide loading when video is ready
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
#  ENTRY POINT
# ══════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🚀 Starting Stream API on port {port}")
    uvicorn.run(
        "stream_api:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )
