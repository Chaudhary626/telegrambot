-- ══════════════════════════════════════════════
-- Telegram File ID Extractor Bot
-- MySQL Table Schema
-- ══════════════════════════════════════════════
-- Compatible with: MySQL 5.7+, MariaDB 10.3+
-- Hosting: Hostinger, any MySQL provider
-- ══════════════════════════════════════════════

-- Create database (skip if using Hostinger — they create it for you)
-- CREATE DATABASE IF NOT EXISTS telegram_bot
--     CHARACTER SET utf8mb4
--     COLLATE utf8mb4_unicode_ci;
-- USE telegram_bot;

-- ──────────────────────────────────────────────
-- Main files table
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    -- Auto-increment primary key
    id INT AUTO_INCREMENT PRIMARY KEY,

    -- File title (extracted from filename/caption)
    title VARCHAR(500) NOT NULL DEFAULT 'Untitled',

    -- Telegram file_id (used to stream/download the file)
    file_id VARCHAR(500) NOT NULL,

    -- Telegram file_unique_id (permanent identifier)
    file_unique_id VARCHAR(200) DEFAULT NULL,

    -- Video quality (480p, 720p, 1080p, 4K)
    quality VARCHAR(50) DEFAULT 'Unknown',

    -- Audio language (Hindi, English, Dual Audio)
    language VARCHAR(100) DEFAULT 'Unknown',

    -- Episode identifier (S01E01, EP01, etc.)
    episode VARCHAR(50) DEFAULT 'Unknown',

    -- File size in bytes (supports 1GB+ files)
    size BIGINT DEFAULT 0,

    -- Video duration in seconds
    duration INT DEFAULT 0,

    -- Video resolution
    width INT DEFAULT 0,
    height INT DEFAULT 0,

    -- File type (video or document)
    file_type VARCHAR(20) DEFAULT 'video',

    -- Original caption/filename
    caption TEXT DEFAULT NULL,

    -- Timestamp when this record was created
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- ── Indexes for fast lookups ──
    INDEX idx_file_id (file_id(100)),
    INDEX idx_title (title(100)),
    INDEX idx_episode (episode),
    INDEX idx_quality (quality),
    INDEX idx_created_at (created_at)

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ══════════════════════════════════════════════
-- Useful Queries (for reference)
-- ══════════════════════════════════════════════

-- Get all files:
-- SELECT * FROM files ORDER BY id DESC;

-- Get files by quality:
-- SELECT * FROM files WHERE quality = '1080p' ORDER BY id DESC;

-- Search by title:
-- SELECT * FROM files WHERE title LIKE '%Naruto%' ORDER BY id DESC;

-- Get last 10 entries:
-- SELECT * FROM files ORDER BY id DESC LIMIT 10;

-- Count by quality:
-- SELECT quality, COUNT(*) as count FROM files GROUP BY quality;

-- Get total storage size:
-- SELECT SUM(size) as total_bytes FROM files;
