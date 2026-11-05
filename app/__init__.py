"""
app/__init__.py
----------------
Application factory package for TaskManager.

This file is responsible for:
1. Instantiating the SQLAlchemy database extension (`db`).
2. Instantiating Flask-Login (`login_manager`) for session handling and protected views.
3. Providing the `create_app()` factory function to configure and initialize Flask.
4. Explicitly pointing Flask to the root `templates/` and `static/` directories as requested.
5. Registering route blueprints and initializing database tables.
"""

import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from app.config import Config

# Instantiate the SQLAlchemy extension (unbound to any specific app instance yet)
db = SQLAlchemy()

# Instantiate Flask-Login manager for user session tracking and route protection
login_manager = LoginManager()
login_manager.login_view = 'main.login'
login_manager.login_message = 'Please log in to access the task board.'
login_manager.login_message_category = 'info'


def create_app(config_class=Config) -> Flask:
    """
    Application Factory Pattern:
    Initializes a new Flask application instance, applies configuration, binds
    extensions (SQLAlchemy, Flask-Login), and registers blueprints.

    Args:
        config_class: Configuration object/class containing database URI, secret keys, etc.

    Returns:
        Flask: The fully configured Flask application instance.
    """
    # Determine the project root directory (one level up from this 'app' folder)
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    # Point Flask to the root-level 'templates' and 'static' directories
    template_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')

    # Create the Flask application instance with custom template and static folders
    app = Flask(
        __name__,
        template_folder=template_dir,
        static_folder=static_dir
    )

    # Load configuration settings into the app
    app.config.from_object(config_class)

    # Bind the SQLAlchemy database object to this Flask application
    db.init_app(app)

    # Bind Flask-Login to this Flask application
    login_manager.init_app(app)

    # User loader callback for Flask-Login to reload user object from session ID
    @login_manager.user_loader
    def load_user(user_id):
        from app.models import User
        return User.query.get(int(user_id))

    # Register the main web routes blueprint
    from app.routes import main_bp
    app.register_blueprint(main_bp)

    # Register the REST API blueprint (/api/tasks, /api/activity, etc.)
    from app.api import api_bp
    app.register_blueprint(api_bp)

    # Create tables automatically within the application context if they don't already exist
    with app.app_context():
        # Import models so SQLAlchemy is aware of all declared tables
        from app import models  # noqa: F401
        db.create_all()

        # Seamlessly ensure 'important' column exists for existing SQLite tables
        try:
            with db.engine.connect() as conn:
                res = conn.execute(db.text("PRAGMA table_info(tasks)"))
                cols = [row[1] for row in res.fetchall()]
                if 'important' not in cols:
                    conn.execute(db.text("ALTER TABLE tasks ADD COLUMN important BOOLEAN DEFAULT 0 NOT NULL"))
                    conn.commit()
        except Exception:
            pass

    return app
