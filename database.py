import sqlite3
import os

DB_PATH = "bot_data.db"

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_banned INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE,
                name TEXT,
                username TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    # ===================== משתמשים =====================

    def add_user(self, user_id: int, username: str, first_name: str):
        self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
            (user_id, username, first_name)
        )
        self.conn.commit()

    def get_all_users(self):
        cursor = self.conn.execute("SELECT * FROM users WHERE is_banned = 0")
        return [dict(row) for row in cursor.fetchall()]

    def get_users_count(self):
        cursor = self.conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 0")
        return cursor.fetchone()[0]

    def ban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def unban_user(self, user_id: int):
        self.conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_banned_users(self):
        cursor = self.conn.execute("SELECT * FROM users WHERE is_banned = 1")
        return [dict(row) for row in cursor.fetchall()]

    def get_banned_count(self):
        cursor = self.conn.execute("SELECT COUNT(*) FROM users WHERE is_banned = 1")
        return cursor.fetchone()[0]

    def is_banned(self, user_id: int) -> bool:
        cursor = self.conn.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row and row[0] == 1

    # ===================== ערוצים =====================

    def add_channel(self, chat_id: int, name: str, username: str = ""):
        self.conn.execute(
            "INSERT OR REPLACE INTO channels (chat_id, name, username) VALUES (?, ?, ?)",
            (chat_id, name, username)
        )
        self.conn.commit()

    def remove_channel(self, chat_id: int):
        self.conn.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        self.conn.commit()

    def get_channels(self):
        cursor = self.conn.execute("SELECT * FROM channels")
        return [dict(row) for row in cursor.fetchall()]
