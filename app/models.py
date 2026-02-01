"""Application models."""
import sqlite3
from flask_login import UserMixin
from app.database import get_db


class User(UserMixin):
    """User model for authentication."""

    def __init__(self, row: sqlite3.Row):
        """Initialize user from database row."""
        self.id = row["id"]
        self.email = row["email"]

    @staticmethod
    def get_by_id(user_id: int):
        """Get user by ID."""
        conn = get_db()
        row = conn.execute(
            "SELECT id, email FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
        return User(row) if row else None

    @staticmethod
    def get_by_email(email: str):
        """Get user by email."""
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        return row

    @staticmethod
    def create(email: str, password_hash: str, created_at: str):
        """Create a new user."""
        from app.database import get_db_connection

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, password_hash, created_at)
            )
            row = conn.execute(
                "SELECT id, email FROM users WHERE email = ?",
                (email,)
            ).fetchone()
            return User(row) if row else None

    @staticmethod
    def exists(email: str) -> bool:
        """Check if user with email exists."""
        conn = get_db()
        row = conn.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        return row is not None
