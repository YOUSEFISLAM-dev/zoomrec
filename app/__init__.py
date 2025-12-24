"""
ZoomRec - Zoom Meeting Recording Web Application
Records Zoom meetings and indexes them by meeting URL.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name=None):
    """Application factory."""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///zoomrec.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['RECORDINGS_DIR'] = os.environ.get('RECORDINGS_DIR', '/workspaces/zoomrec/recordings')
    app.config['MAX_CONCURRENT_RECORDINGS'] = int(os.environ.get('MAX_CONCURRENT_RECORDINGS', 3))
    
    # Ensure recordings directory exists
    os.makedirs(app.config['RECORDINGS_DIR'], exist_ok=True)
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Register blueprints
    from app.routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    # Create tables
    with app.app_context():
        db.create_all()
    
    return app
