"""Personal Budget Tracker - Main application entry point."""
import os
from app import create_app
from app.database import init_db
from config import config


# Determine environment
env = os.getenv("FLASK_ENV", "development")
app = create_app(env)


if __name__ == "__main__":
    # Initialize database
    with app.app_context():
        init_db()

    # Get port and debug settings from config
    port = app.config.get('PORT', 5000)
    debug = app.config.get('DEBUG', True)

    app.run(debug=debug, port=port)
