<?php
/**
 * ═══════════════════════════════════════════════════════
 * AnimeGalaxyHub — Stream API Helper
 * ═══════════════════════════════════════════════════════
 *
 * This PHP file generates stream URLs from your database.
 * Put it on Hostinger alongside your website files.
 *
 * Endpoints:
 *   GET /stream_helper.php?action=get_url&id=42
 *   GET /stream_helper.php?action=get_url&file_id=BAACAgIAA...
 *   GET /stream_helper.php?action=list&page=1
 *
 * Returns JSON that your JavaScript player can use.
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');

// ──────────────────────────────────────────────
// ⚠️ EDIT THESE VALUES
// ──────────────────────────────────────────────

// Your Stream API on Render (the stream_api.py service)
$STREAM_API_URL = "https://animegalaxyhub-stream.onrender.com";

// The STREAM_SECRET you set in Render environment variables
$STREAM_SECRET  = "your_stream_secret_here";

// MySQL Database credentials
$DB_HOST = "localhost";
$DB_USER = "u602666777_admin";
$DB_PASS = "your_password";
$DB_NAME = "u602666777_telegram";

// ──────────────────────────────────────────────
// Database connection
// ──────────────────────────────────────────────
$conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS, $DB_NAME);
if ($conn->connect_error) {
    echo json_encode(["error" => "Database connection failed"]);
    exit;
}
$conn->set_charset("utf8mb4");

// ──────────────────────────────────────────────
// Handle actions
// ──────────────────────────────────────────────
$action = $_GET['action'] ?? '';

switch ($action) {

    // ── Get stream URL for a video ──
    case 'get_url':
        $video = null;

        if (isset($_GET['id'])) {
            $id = intval($_GET['id']);
            $stmt = $conn->prepare("SELECT * FROM files WHERE id = ?");
            $stmt->bind_param("i", $id);
            $stmt->execute();
            $video = $stmt->get_result()->fetch_assoc();
            $stmt->close();
        } elseif (isset($_GET['file_id'])) {
            $fid = $_GET['file_id'];
            $stmt = $conn->prepare("SELECT * FROM files WHERE file_id = ? LIMIT 1");
            $stmt->bind_param("s", $fid);
            $stmt->execute();
            $video = $stmt->get_result()->fetch_assoc();
            $stmt->close();
        }

        if (!$video) {
            http_response_code(404);
            echo json_encode(["error" => "Video not found"]);
            exit;
        }

        $file_id  = $video['file_id'];
        $size     = intval($video['size']);
        $encoded  = urlencode($file_id);

        echo json_encode([
            "success"    => true,
            "id"         => $video['id'],
            "title"      => $video['title'],
            "quality"    => $video['quality'],
            "language"   => $video['language'],
            "episode"    => $video['episode'],
            "size"       => $size,
            "size_human" => formatBytes($size),
            "duration"   => intval($video['duration']),
            "width"      => intval($video['width']),
            "height"     => intval($video['height']),

            // ✅ These are the URLs your player needs
            "stream_url" => "{$STREAM_API_URL}/stream/{$encoded}?key={$STREAM_SECRET}&s={$size}",
            "player_url" => "{$STREAM_API_URL}/player/{$encoded}?key={$STREAM_SECRET}&s={$size}&title=" . urlencode($video['title']),
        ]);
        break;

    // ── List all videos ──
    case 'list':
        $page  = max(1, intval($_GET['page'] ?? 1));
        $limit = min(50, max(1, intval($_GET['limit'] ?? 20)));
        $offset = ($page - 1) * $limit;

        // Total count
        $count_result = $conn->query("SELECT COUNT(*) as total FROM files");
        $total = $count_result->fetch_assoc()['total'];

        // Fetch videos
        $stmt = $conn->prepare("SELECT id, title, quality, language, episode, size, duration, width, height, created_at FROM files ORDER BY id DESC LIMIT ? OFFSET ?");
        $stmt->bind_param("ii", $limit, $offset);
        $stmt->execute();
        $result = $stmt->get_result();

        $videos = [];
        while ($row = $result->fetch_assoc()) {
            $row['size_human'] = formatBytes($row['size']);
            $videos[] = $row;
        }
        $stmt->close();

        echo json_encode([
            "success" => true,
            "total"   => intval($total),
            "page"    => $page,
            "limit"   => $limit,
            "videos"  => $videos,
        ]);
        break;

    // ── Search videos ──
    case 'search':
        $query = $_GET['q'] ?? '';
        if (empty($query)) {
            echo json_encode(["error" => "Missing search query (?q=...)"]);
            exit;
        }

        $search = "%{$query}%";
        $stmt = $conn->prepare("SELECT id, title, quality, language, episode, size, created_at FROM files WHERE title LIKE ? ORDER BY id DESC LIMIT 20");
        $stmt->bind_param("s", $search);
        $stmt->execute();
        $result = $stmt->get_result();

        $videos = [];
        while ($row = $result->fetch_assoc()) {
            $row['size_human'] = formatBytes($row['size']);
            $videos[] = $row;
        }
        $stmt->close();

        echo json_encode([
            "success" => true,
            "query"   => $query,
            "count"   => count($videos),
            "videos"  => $videos,
        ]);
        break;

    default:
        echo json_encode([
            "error" => "Unknown action. Use: get_url, list, or search",
            "examples" => [
                "Get stream URL"  => "/stream_helper.php?action=get_url&id=42",
                "List videos"     => "/stream_helper.php?action=list&page=1",
                "Search"          => "/stream_helper.php?action=search&q=naruto",
            ],
        ]);
}

$conn->close();

// ──────────────────────────────────────────────
// Helper
// ──────────────────────────────────────────────
function formatBytes($bytes) {
    if ($bytes >= 1073741824) return round($bytes / 1073741824, 2) . ' GB';
    if ($bytes >= 1048576)    return round($bytes / 1048576, 2) . ' MB';
    if ($bytes >= 1024)       return round($bytes / 1024, 2) . ' KB';
    return $bytes . ' B';
}
?>
