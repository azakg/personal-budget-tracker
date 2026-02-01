"""Database connection and initialization."""
import sqlite3
from contextlib import contextmanager
from flask import current_app, g


def get_db():
    """Get database connection for current request."""
    if 'db' not in g:
        db_path = current_app.config.get('DB_PATH')
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON;")
    return g.db


def close_db(e=None):
    """Close database connection at end of request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()


@contextmanager
def get_db_connection():
    """Context manager for database operations with automatic commit/rollback."""
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Initialize database schema."""
    db_path = current_app.config.get('DB_PATH')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tx_date TEXT NOT NULL,
            kind TEXT CHECK(kind IN ('income','expense')) NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS budgets (
            user_id INTEGER NOT NULL,
            year INTEGER NOT NULL,
            month INTEGER NOT NULL,
            amount REAL NOT NULL CHECK(amount >= 0),
            PRIMARY KEY (user_id, year, month),
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """
    )

    conn.commit()
    conn.close()


def init_app(app):
    """Initialize database with Flask app."""
    app.teardown_appcontext(close_db)
