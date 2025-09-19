from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
import os

# Initialize extensions
db = SQLAlchemy()
csrf = CSRFProtect()

def create_app(config_name=None):
    """Application factory pattern with Hybrid System Support"""
    # Fix template and static folder paths - they are in project root, not app folder
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(project_root, 'templates')
    static_dir = os.path.join(project_root, 'static')
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')

    if config_name == 'development':
        from config import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)
    elif config_name == 'production':
        from config import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        from config import DevelopmentConfig
        app.config.from_object(DevelopmentConfig)

    # Initialize app with configuration
    from config import Config
    if hasattr(Config, 'init_app'):
        Config.init_app(app)

    # Initialize extensions with app
    db.init_app(app)
    csrf.init_app(app)

    # Make CSRF token available in templates
    from flask_wtf.csrf import generate_csrf
    @app.template_global()
    def csrf_token():
        return generate_csrf()

    # Create necessary directories
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config.get('CORPUS_DATA_DIR', 'data/corpus'), exist_ok=True)
    os.makedirs(app.config.get('CORPUS_DOWNLOAD_DIR', 'data/downloads'), exist_ok=True)
    os.makedirs('logs', exist_ok=True)

    # Import models to ensure they are registered
    from app import models

    # Register blueprints
    try:
        # Try to use new route structure
        from app.routes.main import main_bp
        from app.routes.admin import admin_bp

        app.register_blueprint(main_bp)
        app.register_blueprint(admin_bp)

    except ImportError:
        # Fallback to old route structure
        from app.routes import main_bp
        app.register_blueprint(main_bp)

    # Ensure database tables exist
    with app.app_context():
        # Create tables if they don't exist (preserves existing data)
        db.create_all()

        # Initialize hybrid system data
        initialize_hybrid_system()

    return app


def initialize_hybrid_system():
    """Initialize hybrid system components"""
    try:
        from app.models import DomainCoverage, CorpusStatistics

        # Initialize domain coverage if not exists
        categories = [
            ('greetings', 500), ('family', 800), ('agriculture', 1000),
            ('health', 700), ('education', 600), ('weather', 400),
            ('technology', 500), ('business', 600), ('culture', 400),
            ('conversation', 800), ('general', 1000)
        ]

        for category, target_count in categories:
            existing = DomainCoverage.query.filter_by(category=category).first()
            if not existing:
                coverage = DomainCoverage(
                    category=category,
                    target_count=target_count,
                    current_count=0,
                    completion_percentage=0.0
                )
                db.session.add(coverage)

        # Initialize corpus statistics
        existing_stats = CorpusStatistics.query.first()
        if not existing_stats:
            stats = CorpusStatistics()
            stats.update_statistics()
            db.session.add(stats)

        db.session.commit()

    except Exception as e:
        print(f"Warning: Could not initialize hybrid system: {e}")
        db.session.rollback()