"""Flask application factory."""
import os
from pathlib import Path
from flask import Flask
from flask_login import LoginManager

from config import config


def create_app(config_name='default'):
    """Create and configure Flask application.

    Args:
        config_name: Configuration name ('development', 'production', or 'default')

    Returns:
        Configured Flask application instance
    """
    app = Flask(__name__, instance_relative_config=True)

    # Load configuration
    app.config.from_object(config[config_name])

    # Ensure instance folder exists
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    # Set database path
    app.config['DB_PATH'] = os.path.join(app.instance_path, app.config['DB_NAME'])

    # Initialize extensions
    from app import database
    database.init_app(app)

    # Initialize Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        """Load user by ID for Flask-Login."""
        try:
            return User.get_by_id(int(user_id))
        except (ValueError, TypeError):
            return None

    # Register blueprints
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.main import bp as main_bp
    app.register_blueprint(main_bp)

    from app.receipts import bp as receipts_bp
    app.register_blueprint(receipts_bp)

    return app
