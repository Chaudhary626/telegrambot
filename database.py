"""
Database Module
================
Handles all MySQL database operations.
Uses PyMySQL (pure Python, works on Termux without issues).

Compatible with Hostinger MySQL databases.
"""

import pymysql
from pymysql.cursors import DictCursor
from datetime import datetime
import re

import config


class Database:
    """MySQL database handler for storing extracted file metadata."""

    def __init__(self):
        """Initialize database connection settings."""
        self.connection = None

    def connect(self):
        """
        Establish connection to MySQL database.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            self.connection = pymysql.connect(
                host=config.DB_HOST,
                port=config.DB_PORT,
                user=config.DB_USER,
                password=config.DB_PASSWORD,
                database=config.DB_NAME,
                charset='utf8mb4',
                cursorclass=DictCursor,
                autocommit=True,
                # Connection timeout (important for remote Hostinger DB)
                connect_timeout=10,
                read_timeout=30,
                write_timeout=30,
            )
            print("✅ Database connected successfully!")
            return True
        except pymysql.Error as e:
            print(f"❌ Database connection failed: {e}")
            return False

    def ensure_connection(self):
        """
        Make sure we have an active database connection.
        Reconnects automatically if the connection was lost.
        """
        try:
            if self.connection is None or not self.connection.open:
                self.connect()
            else:
                # Ping to check if connection is alive
                self.connection.ping(reconnect=True)
        except pymysql.Error:
            self.connect()

    def create_table(self):
        """
        Create the files table if it doesn't exist.

        This is safe to call multiple times (uses IF NOT EXISTS).
        """
        self.ensure_connection()

        create_sql = """
        CREATE TABLE IF NOT EXISTS files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            title VARCHAR(500) NOT NULL DEFAULT 'Untitled',
            file_id VARCHAR(500) NOT NULL,
            file_unique_id VARCHAR(200) DEFAULT NULL,
            quality VARCHAR(50) DEFAULT 'Unknown',
            language VARCHAR(100) DEFAULT 'Unknown',
            episode VARCHAR(50) DEFAULT 'Unknown',
            size BIGINT DEFAULT 0,
            duration INT DEFAULT 0,
            width INT DEFAULT 0,
            height INT DEFAULT 0,
            file_type VARCHAR(20) DEFAULT 'video',
            caption TEXT DEFAULT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_file_id (file_id(100)),
            INDEX idx_title (title(100)),
            INDEX idx_episode (episode)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
        """

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(create_sql)
            print("✅ Table 'files' is ready!")
            return True
        except pymysql.Error as e:
            print(f"❌ Failed to create table: {e}")
            return False

    def save_file(self, data: dict) -> int:
        """
        Save extracted file data to database.

        Args:
            data: Dictionary containing file metadata.
                  Expected keys: title, file_id, file_unique_id, quality,
                  language, episode, size, duration, width, height,
                  file_type, caption

        Returns:
            The inserted row ID, or 0 if failed.
        """
        self.ensure_connection()

        insert_sql = """
        INSERT INTO files (
            title, file_id, file_unique_id, quality, language,
            episode, size, duration, width, height, file_type, caption
        ) VALUES (
            %(title)s, %(file_id)s, %(file_unique_id)s, %(quality)s, %(language)s,
            %(episode)s, %(size)s, %(duration)s, %(width)s, %(height)s,
            %(file_type)s, %(caption)s
        )
        """

        # Set defaults for any missing keys
        defaults = {
            'title': 'Untitled',
            'file_id': '',
            'file_unique_id': '',
            'quality': 'Unknown',
            'language': 'Unknown',
            'episode': 'Unknown',
            'size': 0,
            'duration': 0,
            'width': 0,
            'height': 0,
            'file_type': 'video',
            'caption': None,
        }
        defaults.update(data)

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, defaults)
                row_id = cursor.lastrowid
            print(f"✅ Saved to database (ID: {row_id})")
            return row_id
        except pymysql.Error as e:
            print(f"❌ Failed to save file: {e}")
            return 0

    def get_last_file(self) -> dict | None:
        """
        Get the most recently saved file from the database.

        Returns:
            Dictionary of the last file data, or None if empty.
        """
        self.ensure_connection()

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM files ORDER BY id DESC LIMIT 1"
                )
                return cursor.fetchone()
        except pymysql.Error as e:
            print(f"❌ Failed to fetch last file: {e}")
            return None

    def search_files(self, query: str, limit: int = 10) -> list:
        """
        Search files by title.

        Args:
            query: Search term to match against titles.
            limit: Maximum number of results.

        Returns:
            List of matching file dictionaries.
        """
        self.ensure_connection()

        try:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM files WHERE title LIKE %s ORDER BY id DESC LIMIT %s",
                    (f"%{query}%", limit)
                )
                return cursor.fetchall()
        except pymysql.Error as e:
            print(f"❌ Search failed: {e}")
            return []

    def get_file_count(self) -> int:
        """Get total number of files in database."""
        self.ensure_connection()

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) as count FROM files")
                result = cursor.fetchone()
                return result['count'] if result else 0
        except pymysql.Error as e:
            print(f"❌ Count failed: {e}")
            return 0

    def find_movie_by_title(self, title: str) -> dict | None:
        """
        Fuzzy search for a movie in the website's movies table.
        Used to auto-link extracted Telegram channel video files.
        """
        self.ensure_connection()
        try:
            with self.connection.cursor() as cursor:
                # 1. Try exact match
                cursor.execute("SELECT id, title, slug, content_type FROM movies WHERE title = %s AND status = 1", (title,))
                row = cursor.fetchone()
                if row:
                    return row

                # 2. Try partial match
                cursor.execute("SELECT id, title, slug, content_type FROM movies WHERE title LIKE %s AND status = 1 LIMIT 1", (f"%{title}%",))
                row = cursor.fetchone()
                if row:
                    return row

                # 3. Clean up common words and try again
                cleaned_title = re.sub(r'\b(?:the|a|an|of|and|in|on|at|to|for|with|by|season|episode|ep|s\d+e\d+|movie|anime)\b', '', title, flags=re.IGNORECASE)
                cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
                if len(cleaned_title) > 3:
                    cursor.execute("SELECT id, title, slug, content_type FROM movies WHERE title LIKE %s AND status = 1 LIMIT 1", (f"%{cleaned_title}%",))
                    row = cursor.fetchone()
                    if row:
                        return row
        except pymysql.Error as e:
            print(f"❌ Failed to find movie by title: {e}")
        return None

    def save_streaming_source(self, data: dict) -> int:
        """
        Insert or update a streaming source directly in the website's streaming_sources table.
        This enables instant, fully automated playback on the watch page.
        """
        self.ensure_connection()

        insert_sql = """
        INSERT INTO streaming_sources (
            movie_id, season, episode, language, quality, telegram_file_id,
            stream_url, file_size_mb, duration_seconds, title, stream_method,
            is_active, sort_order
        ) VALUES (
            %(movie_id)s, %(season)s, %(episode)s, %(language)s, %(quality)s, %(telegram_file_id)s,
            %(stream_url)s, %(file_size_mb)s, %(duration_seconds)s, %(title)s, %(stream_method)s,
            %(is_active)s, %(sort_order)s
        ) ON DUPLICATE KEY UPDATE
            telegram_file_id = VALUES(telegram_file_id),
            stream_url = VALUES(stream_url),
            file_size_mb = VALUES(file_size_mb),
            duration_seconds = VALUES(duration_seconds),
            title = VALUES(title)
        """
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(insert_sql, data)
                # If ON DUPLICATE KEY UPDATE was triggered, return the row ID of existing match
                if cursor.lastrowid:
                    return cursor.lastrowid
                
                # Otherwise query the ID by unique key constraint values
                query_sql = """
                SELECT id FROM streaming_sources 
                WHERE movie_id = %(movie_id)s AND season = %(season)s AND episode = %(episode)s 
                  AND language = %(language)s AND quality = %(quality)s LIMIT 1
                """
                cursor.execute(query_sql, data)
                res = cursor.fetchone()
                return res['id'] if res else 1
        except pymysql.Error as e:
            print(f"❌ Failed to save streaming source: {e}")
            return 0

    def close(self):
        """Close the database connection."""
        if self.connection and self.connection.open:
            self.connection.close()
            print("🔒 Database connection closed.")
