"""
Metadata Extraction Module
===========================
Parses filenames and captions to detect:
- Video quality (480p, 720p, 1080p, 4K)
- Language (Hindi, English, Dual Audio, Japanese)
- Episode info (S01E01, EP01, etc.)
"""

import re


def detect_quality(text: str) -> str:
    """
    Detect video quality from filename or caption.

    Checks for common quality tags like 480p, 720p, 1080p, 2160p, 4K.
    Returns the matched quality or 'Unknown'.

    Examples:
        >>> detect_quality("Naruto.S01E01.720p.mkv")
        '720p'
        >>> detect_quality("Movie [1080p] [BluRay]")
        '1080p'
    """
    if not text:
        return "Unknown"

    text = text.lower()

    # Check from highest to lowest quality
    quality_patterns = [
        (r'2160p|4k|uhd', '2160p/4K'),
        (r'1080p|full\s*hd|fhd', '1080p'),
        (r'720p|hd(?!r)', '720p'),
        (r'480p|sd', '480p'),
        (r'360p', '360p'),
    ]

    for pattern, label in quality_patterns:
        if re.search(pattern, text):
            return label

    return "Unknown"


def detect_language(text: str) -> str:
    """
    Detect audio language from filename or caption.

    Checks for common language tags.
    Returns the matched language or 'Unknown'.

    Examples:
        >>> detect_language("Movie.Hindi.Dubbed.mkv")
        'Hindi'
        >>> detect_language("Movie [Dual Audio] [Hindi-English]")
        'Dual Audio'
    """
    if not text:
        return "Unknown"

    text_lower = text.lower()

    # Check dual audio first (more specific)
    dual_patterns = [
        r'dual\s*audio',
        r'hindi\s*[\-\+&]\s*english',
        r'english\s*[\-\+&]\s*hindi',
        r'hin\s*[\-\+&]\s*eng',
        r'eng\s*[\-\+&]\s*hin',
        r'multi\s*audio',
    ]
    for pattern in dual_patterns:
        if re.search(pattern, text_lower):
            return "Dual Audio"

    # Check individual languages
    language_patterns = [
        (r'\bhindi\b|\bhin\b|\bhindi\s*dubbed\b', 'Hindi'),
        (r'\benglish\b|\beng\b|\bengdub\b', 'English'),
        (r'\bjapanese\b|\bjap\b|\bjpn\b', 'Japanese'),
        (r'\bkorean\b|\bkor\b', 'Korean'),
        (r'\btamil\b|\btam\b', 'Tamil'),
        (r'\btelugu\b|\btel\b', 'Telugu'),
    ]

    for pattern, label in language_patterns:
        if re.search(pattern, text_lower):
            return label

    return "Unknown"


def detect_episode(text: str) -> str:
    """
    Detect episode information from filename or caption.

    Supports formats: S01E01, EP01, Episode 01, E01, etc.
    Returns the matched episode string or 'Unknown'.

    Examples:
        >>> detect_episode("Naruto.S01E05.720p.mkv")
        'S01E05'
        >>> detect_episode("One Piece EP1000.mkv")
        'EP1000'
    """
    if not text:
        return "Unknown"

    # Try different episode patterns (most specific first)
    episode_patterns = [
        # S01E01 or S1E1 format
        (r'(S\d{1,2}E\d{1,4})', lambda m: m.group(1).upper()),
        # Season 1 Episode 1
        (r'Season\s*(\d{1,2})\s*Episode\s*(\d{1,4})',
         lambda m: f"S{m.group(1).zfill(2)}E{m.group(2).zfill(2)}"),
        # EP01 or EP1 or EP001
        (r'EP\.?(\d{1,4})', lambda m: f"EP{m.group(1).zfill(2)}"),
        # Episode 01
        (r'Episode\s*(\d{1,4})', lambda m: f"EP{m.group(1).zfill(2)}"),
        # E01 (but not in words like "the")
        (r'(?<![a-zA-Z])E(\d{2,4})(?![a-zA-Z])',
         lambda m: f"EP{m.group(1).zfill(2)}"),
        # Standalone number with dash: - 01, - 001
        (r'\s-\s(\d{2,4})(?:\s|\.|\[|\(|$)',
         lambda m: f"EP{m.group(1).zfill(2)}"),
    ]

    for pattern, formatter in episode_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return formatter(match)

    return "Unknown"


def extract_title(text: str) -> str:
    """
    Try to extract a clean title from filename or caption.

    Supports two formats:
    1. Structured caption: "📄Title:- Witch Hat Atelier"
    2. Standard filename: "Naruto.S01E05.720p.mkv"

    Returns a cleaned-up title string.
    """
    if not text:
        return "Untitled"

    # ── Format 1: Structured caption with "Title:-" or "Title:" ──
    title_match = re.search(
        r'(?:📄|🎬|🎥)?\s*Title\s*[:\-]+\s*(.+)',
        text, re.IGNORECASE
    )
    if title_match:
        title = title_match.group(1).strip()
        # Clean trailing emojis and whitespace
        title = re.sub(r'\s*[\n\r].*', '', title)  # Take only first line
        title = title.strip(' -–—:')
        if title:
            return title

    # ── Format 2: Standard filename parsing ──
    title = text

    # If it's a multi-line caption, take only the first meaningful line
    if '\n' in title:
        first_line = title.split('\n')[0].strip()
        # Remove emoji prefixes
        first_line = re.sub(r'^[^\w\s]+\s*', '', first_line)
        # Remove label prefix like "Title:-"
        first_line = re.sub(r'^(?:title|name)\s*[:\-]+\s*', '', first_line, flags=re.IGNORECASE)
        if first_line and len(first_line) > 2:
            return first_line.strip()

    # Remove file extension
    title = re.sub(r'\.(mkv|mp4|avi|webm|mov|flv)$', '', title, flags=re.IGNORECASE)

    # Remove common tags in brackets
    title = re.sub(r'\[.*?\]', '', title)
    title = re.sub(r'\(.*?\)', '', title)

    # Remove quality/codec/source tags
    remove_patterns = [
        r'(?:480|720|1080|2160)p',
        r'\b(?:x264|x265|h264|h265|hevc|avc|10bit)\b',
        r'\b(?:bluray|bdrip|brrip|webrip|web-dl|hdtv|dvdrip|hdrip)\b',
        r'\b(?:aac|flac|ac3|dts|mp3|eac3|atmos)\b',
        r'\b(?:dual\s*audio|multi\s*audio|hindi|english|japanese)\b',
        r'S\d{1,2}E\d{1,4}',
        r'EP\.?\d{1,4}',
    ]

    for pattern in remove_patterns:
        title = re.sub(pattern, '', title, flags=re.IGNORECASE)

    # Replace dots and underscores with spaces
    title = title.replace('.', ' ').replace('_', ' ')

    # Clean up extra whitespace
    title = re.sub(r'\s+', ' ', title).strip(' -–—')

    return title if title else "Untitled"


def parse_structured_caption(text: str) -> dict:
    """
    Parse structured captions with emoji labels.

    Handles captions like:
        📄Title:- Witch Hat Atelier
        🎬Session:- S01
        🎬Episode:- E02
        🌐Quality:- 1080p
        🗣Language:- Hindi
        ✍Subtitles:- English

    Returns dict with extracted values (empty dict if not a structured caption).
    """
    if not text or '\n' not in text:
        return {}

    result = {}

    # Title
    m = re.search(r'Title\s*[:\-]+\s*(.+)', text, re.IGNORECASE)
    if m:
        result['title'] = m.group(1).strip()

    # Season
    m = re.search(r'Session\s*[:\-]+\s*S?(\d+)', text, re.IGNORECASE)
    if not m:
        m = re.search(r'Season\s*[:\-]+\s*S?(\d+)', text, re.IGNORECASE)
    season = m.group(1).zfill(2) if m else ""

    # Episode
    m = re.search(r'Episode\s*[:\-]+\s*E?P?(\d+)', text, re.IGNORECASE)
    if m:
        ep = m.group(1).zfill(2)
        if season:
            result['episode'] = f"S{season}E{ep}"
        else:
            result['episode'] = f"EP{ep}"

    # Quality
    m = re.search(r'Quality\s*[:\-]+\s*(\d+p|\d+k|4k|uhd|fhd|hd|sd)', text, re.IGNORECASE)
    if m:
        result['quality'] = m.group(1)

    # Language
    m = re.search(r'Language\s*[:\-]+\s*(.+)', text, re.IGNORECASE)
    if m:
        result['language'] = m.group(1).strip()

    return result


def extract_all_metadata(text: str) -> dict:
    """
    Extract all metadata from a single text string.

    First tries structured caption parsing (emoji format).
    Falls back to regex-based detection for standard filenames.

    Returns a dictionary with quality, language, episode, and title.
    """
    # Try structured caption format first
    structured = parse_structured_caption(text)

    if structured:
        # Use structured values, fall back to regex for missing fields
        return {
            'quality': structured.get('quality', detect_quality(text)),
            'language': structured.get('language', detect_language(text)),
            'episode': structured.get('episode', detect_episode(text)),
            'title': structured.get('title', extract_title(text)),
        }

    # Fall back to standard regex parsing
    return {
        'quality': detect_quality(text),
        'language': detect_language(text),
        'episode': detect_episode(text),
        'title': extract_title(text),
    }


def format_file_size(size_bytes: int) -> str:
    """
    Convert bytes to a human-readable file size string.

    Examples:
        >>> format_file_size(1073741824)
        '1.00 GB'
        >>> format_file_size(5242880)
        '5.00 MB'
    """
    if size_bytes is None or size_bytes == 0:
        return "Unknown"

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    size = float(size_bytes)

    for unit in units:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{size:.2f} PB"


def format_duration(seconds: int) -> str:
    """
    Convert seconds to HH:MM:SS or MM:SS format.

    Examples:
        >>> format_duration(3661)
        '1:01:01'
        >>> format_duration(125)
        '2:05'
    """
    if seconds is None or seconds == 0:
        return "Unknown"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
