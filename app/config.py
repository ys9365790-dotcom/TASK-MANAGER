"""
app/config.py
--------------
Configuration module for the TaskManager Flask application.

This file centralizes all application configuration variables, such as:
- Secret keys used for cryptographic session signing and flash messaging.
- Database connection URI (configured for SQLite by default).
- SQLAlchemy operational settings (such as disabling modification tracking for better performance).
"""

import os

# Base directory of the project (one level above 'app')
BASE_DIR = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))


class Config:
    """Base configuration class holding application settings."""

    # Secret key for session security and CSRF protection in Flask
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'taskmanager-super-secret-dev-key-2026'

    # SQLite database file located at the root of the project: taskmanager.db
    # Can be overridden by the DATABASE_URL environment variable for production
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f"sqlite:///{os.path.join(BASE_DIR, 'taskmanager.db')}"

    # Disables Flask-SQLAlchemy event system tracking to conserve memory and resources
    SQLALCHEMY_TRACK_MODIFICATIONS = False
