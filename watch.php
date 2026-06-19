<?php
/**
 * ═══════════════════════════════════════════════════════
 * AnimeGalaxyHub — Video Player Embed Page
 * ═══════════════════════════════════════════════════════
 *
 * This PHP file goes on your Hostinger website.
 * It reads file_id and size from your MySQL database
 * and generates the streaming player.
 *
 * Usage:
 *   https://animegalaxyhub.com/watch.php?id=42
 *   https://animegalaxyhub.com/watch.php?file_id=BAACAgIAA...
 *
 * Place this file in your website's public directory.
 */

// ──────────────────────────────────────────────
// Configuration
// ──────────────────────────────────────────────

// Your Stream API URL (deployed on Render)
$STREAM_API = "https://your-stream-api.onrender.com";

// Your stream secret key (same as STREAM_SECRET env var on Render)
$STREAM_SECRET = "your_stream_secret_here";

// MySQL Database (same as your bot's database)
$DB_HOST = "localhost";
$DB_USER = "u602666777_admin";
$DB_PASS = "your_password";
$DB_NAME = "u602666777_telegram";

// ──────────────────────────────────────────────
// Database Connection
// ──────────────────────────────────────────────
$conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS, $DB_NAME);
if ($conn->connect_error) {
    die("Database connection failed");
}
$conn->set_charset("utf8mb4");

// ──────────────────────────────────────────────
// Get Video Data
// ──────────────────────────────────────────────
$video = null;

if (isset($_GET['id'])) {
    // Method 1: Get by database ID
    $id = intval($_GET['id']);
    $stmt = $conn->prepare("SELECT * FROM files WHERE id = ?");
    $stmt->bind_param("i", $id);
    $stmt->execute();
    $video = $stmt->get_result()->fetch_assoc();
    $stmt->close();

} elseif (isset($_GET['file_id'])) {
    // Method 2: Get by file_id directly
    $file_id = $_GET['file_id'];
    $stmt = $conn->prepare("SELECT * FROM files WHERE file_id = ?");
    $stmt->bind_param("s", $file_id);
    $stmt->execute();
    $video = $stmt->get_result()->fetch_assoc();
    $stmt->close();
}

$conn->close();

if (!$video) {
    http_response_code(404);
    die("Video not found");
}

// ──────────────────────────────────────────────
// Build Stream URLs
// ──────────────────────────────────────────────
$file_id = urlencode($video['file_id']);
$file_size = intval($video['size']);
$title = htmlspecialchars($video['title']);
$quality = htmlspecialchars($video['quality']);
$language = htmlspecialchars($video['language']);
$episode = htmlspecialchars($video['episode']);

// Direct stream URL (for <video> src)
$stream_url = "{$STREAM_API}/stream/{$file_id}?key={$STREAM_SECRET}&s={$file_size}";

// Player page URL (for iframe embed)
$player_url = "{$STREAM_API}/player/{$file_id}?key={$STREAM_SECRET}&s={$file_size}&title=" . urlencode($video['title']);

// Format file size
function formatSize($bytes) {
    if ($bytes >= 1073741824) return round($bytes / 1073741824, 2) . ' GB';
    if ($bytes >= 1048576) return round($bytes / 1048576, 2) . ' MB';
    return round($bytes / 1024, 2) . ' KB';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= $title ?> - AnimeGalaxyHub</title>
    <meta name="description" content="Watch <?= $title ?> <?= $quality ?> <?= $language ?> on AnimeGalaxyHub">

    <!-- Plyr.js Video Player -->
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />

    <!-- Google Font -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">

    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            background: #0f0f13;
            color: #e4e4e7;
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            line-height: 1.6;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        /* ── Video Player ── */
        .player-wrapper {
            position: relative;
            width: 100%;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 25px 50px rgba(0, 0, 0, 0.5);
            margin-bottom: 24px;
            background: #000;
        }

        :root {
            --plyr-color-main: #8b5cf6;
            --plyr-video-background: #000;
            --plyr-badge-background: #8b5cf6;
        }

        /* ── Video Info ── */
        .video-info {
            background: #1a1a24;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid rgba(139, 92, 246, 0.15);
        }

        .video-title {
            font-size: 1.5rem;
            font-weight: 700;
            color: #fff;
            margin-bottom: 16px;
        }

        .video-meta {
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
        }

        .meta-tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 14px;
            background: rgba(139, 92, 246, 0.12);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 500;
            color: #c4b5fd;
        }

        .meta-tag .icon { font-size: 1rem; }

        /* ── Download Section ── */
        .download-section {
            background: #1a1a24;
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(139, 92, 246, 0.15);
        }

        .download-section h3 {
            font-size: 1.1rem;
            margin-bottom: 16px;
            color: #a78bfa;
        }

        .download-btn {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 12px 24px;
            background: linear-gradient(135deg, #8b5cf6, #6d28d9);
            color: #fff;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            font-size: 0.95rem;
            transition: all 0.3s ease;
            border: none;
            cursor: pointer;
        }

        .download-btn:hover {
            background: linear-gradient(135deg, #a78bfa, #8b5cf6);
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(139, 92, 246, 0.3);
        }

        /* ── Responsive ── */
        @media (max-width: 768px) {
            .container { padding: 12px; }
            .video-title { font-size: 1.2rem; }
            .video-meta { gap: 8px; }
        }
    </style>
</head>
<body>

<div class="container">

    <!-- Video Player -->
    <div class="player-wrapper">
        <video id="player" playsinline controls crossorigin>
            <source src="<?= $stream_url ?>" type="video/mp4" />
            Your browser doesn't support video playback.
        </video>
    </div>

    <!-- Video Info -->
    <div class="video-info">
        <h1 class="video-title"><?= $title ?></h1>
        <div class="video-meta">
            <span class="meta-tag">
                <span class="icon">🎞</span> <?= $quality ?>
            </span>
            <span class="meta-tag">
                <span class="icon">🗣</span> <?= $language ?>
            </span>
            <?php if ($episode !== 'Unknown'): ?>
            <span class="meta-tag">
                <span class="icon">📺</span> <?= $episode ?>
            </span>
            <?php endif; ?>
            <span class="meta-tag">
                <span class="icon">📏</span> <?= formatSize($file_size) ?>
            </span>
            <?php if ($video['width'] > 0): ?>
            <span class="meta-tag">
                <span class="icon">📐</span> <?= $video['width'] ?>×<?= $video['height'] ?>
            </span>
            <?php endif; ?>
        </div>
    </div>

    <!-- Download Button (Optional) -->
    <div class="download-section">
        <h3>⬇️ Download</h3>
        <a href="<?= $stream_url ?>" class="download-btn" download="<?= $title ?>.mp4">
            📥 Download <?= $quality ?> (<?= formatSize($file_size) ?>)
        </a>
    </div>

</div>

<!-- Plyr.js -->
<script src="https://cdn.plyr.io/3.7.8/plyr.polyfilled.js"></script>
<script>
    const player = new Plyr('#player', {
        controls: [
            'play-large', 'play', 'rewind', 'fast-forward', 'progress',
            'current-time', 'duration', 'mute', 'volume',
            'settings', 'pip', 'airplay', 'fullscreen'
        ],
        settings: ['quality', 'speed'],
        speed: { selected: 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
        keyboard: { focused: true, global: true },
        tooltips: { controls: true, seek: true },
        seekTime: 10,
    });
</script>

</body>
</html>
