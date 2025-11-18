"""Application configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration."""

    # App settings
    APP_NAME = "Personal Budget Tracker"
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-me")

    # Database
    DB_NAME = "budget.db"

    # Instance folder
    INSTANCE_PATH = None  # Will be set by app factory

    # File upload settings
    UPLOAD_FOLDER = "static/uploads"
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'pdf'}
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

    # API Keys
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

    # Categories
    DEFAULT_CATEGORIES = [
        "Grocery",
        "Car",
        "Utilities",
        "Apartment Rent",
        "Entertainment",
        "Health",
        "Other"
    ]


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    PORT = int(os.getenv("PORT", "5000"))


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    PORT = int(os.getenv("PORT", "8000"))


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig
}
