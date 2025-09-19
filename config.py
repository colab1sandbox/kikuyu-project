import os
from datetime import timedelta

class Config:
    """Base configuration class for Hybrid Kikuyu Translation Platform"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://neondb_owner:npg_IqfGwQAXN3l1@ep-empty-leaf-a1u0aj23-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OpenRouter Configuration
    OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY') or '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'
    OPENROUTER_MODEL = os.environ.get('OPENROUTER_MODEL') or 'meta-llama/llama-3.3-70b-instruct:free'
    OPENROUTER_DAILY_LIMIT = int(os.environ.get('OPENROUTER_DAILY_LIMIT', 50))  # Free tier limit

    # Hybrid System Configuration
    CORPUS_DATA_DIR = os.environ.get('CORPUS_DATA_DIR') or 'data/corpus'
    CORPUS_DOWNLOAD_DIR = os.environ.get('CORPUS_DOWNLOAD_DIR') or 'data/downloads'

    # CSV Dataset Configuration
    CSV_DATASET_FILE = os.environ.get('CSV_DATASET_FILE') or 'data/englishswahli_dataset.csv'
    CSV_DATASET_ENABLED = os.environ.get('CSV_DATASET_ENABLED', 'true').lower() == 'true'

    # Prompt Cache Settings
    PROMPT_CACHE_FILE = 'instance/prompts.json'
    MIN_CACHE_SIZE = int(os.environ.get('MIN_CACHE_SIZE', 200))  # Auto-refill when below 200
    PROMPT_BATCH_SIZE = int(os.environ.get('PROMPT_BATCH_SIZE', 300))  # Refill with 300 prompts

    # Smart Selector Configuration
    SMART_SELECTOR_ENABLED = os.environ.get('SMART_SELECTOR_ENABLED', 'true').lower() == 'true'
    COVERAGE_GAP_THRESHOLD = float(os.environ.get('COVERAGE_GAP_THRESHOLD', 0.25))  # 25%
    QUALITY_THRESHOLD = float(os.environ.get('QUALITY_THRESHOLD', 0.7))

    # Source Distribution Targets (percentages)
    TARGET_SOURCE_DISTRIBUTION = {
        'corpus': int(os.environ.get('TARGET_CORPUS_PERCENTAGE', 60)),
        'llm': int(os.environ.get('TARGET_LLM_PERCENTAGE', 25)),
        'community': int(os.environ.get('TARGET_COMMUNITY_PERCENTAGE', 15))
    }

    # Quality Control Configuration
    QUALITY_CONTROL_ENABLED = os.environ.get('QUALITY_CONTROL_ENABLED', 'true').lower() == 'true'
    AUTO_QUALITY_SCORING = os.environ.get('AUTO_QUALITY_SCORING', 'true').lower() == 'true'
    DUPLICATE_DETECTION_ENABLED = os.environ.get('DUPLICATE_DETECTION_ENABLED', 'true').lower() == 'true'

    # Community Submission Configuration
    COMMUNITY_SUBMISSIONS_ENABLED = os.environ.get('COMMUNITY_SUBMISSIONS_ENABLED', 'true').lower() == 'true'
    COMMUNITY_SUBMISSION_RATE_LIMIT = int(os.environ.get('COMMUNITY_SUBMISSION_RATE_LIMIT', 5))  # per hour
    COMMUNITY_AUTO_APPROVAL_THRESHOLD = float(os.environ.get('COMMUNITY_AUTO_APPROVAL_THRESHOLD', 0.9))

    # Coverage Tracking Configuration
    DEFAULT_CATEGORY_TARGET = int(os.environ.get('DEFAULT_CATEGORY_TARGET', 1000))
    COVERAGE_UPDATE_FREQUENCY = int(os.environ.get('COVERAGE_UPDATE_FREQUENCY', 3600))  # seconds

    # Analytics Configuration
    ANALYTICS_ENABLED = os.environ.get('ANALYTICS_ENABLED', 'true').lower() == 'true'
    ANALYTICS_RETENTION_DAYS = int(os.environ.get('ANALYTICS_RETENTION_DAYS', 90))
    DAILY_STATS_UPDATE = os.environ.get('DAILY_STATS_UPDATE', 'true').lower() == 'true'

    # User Management Configuration
    DAILY_SUBMISSION_LIMIT = None  # Unlimited by default
    USER_SESSION_TIMEOUT = timedelta(hours=int(os.environ.get('USER_SESSION_TIMEOUT_HOURS', 24)))
    ANONYMOUS_SUBMISSIONS = os.environ.get('ANONYMOUS_SUBMISSIONS', 'true').lower() == 'true'

    # Admin Configuration
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    ADMIN_SESSION_TIMEOUT = timedelta(hours=int(os.environ.get('ADMIN_SESSION_TIMEOUT_HOURS', 8)))

    # Data Export Configuration
    EXPORT_ENABLED = os.environ.get('EXPORT_ENABLED', 'true').lower() == 'true'
    EXPORT_FORMATS = ['csv', 'json']
    MAX_EXPORT_RECORDS = int(os.environ.get('MAX_EXPORT_RECORDS', 10000))

    # Performance Configuration
    DATABASE_POOL_SIZE = int(os.environ.get('DATABASE_POOL_SIZE', 10))
    DATABASE_POOL_TIMEOUT = int(os.environ.get('DATABASE_POOL_TIMEOUT', 30))
    PAGINATION_PER_PAGE = int(os.environ.get('PAGINATION_PER_PAGE', 50))

    # Corpus Building Configuration
    INITIAL_CORPUS_SIZE = int(os.environ.get('INITIAL_CORPUS_SIZE', 70000))
    SCALE_CORPUS_SIZE = int(os.environ.get('SCALE_CORPUS_SIZE', 500000))
    WIKIPEDIA_EXTRACT_LIMIT = int(os.environ.get('WIKIPEDIA_EXTRACT_LIMIT', 50000))
    TATOEBA_EXTRACT_LIMIT = int(os.environ.get('TATOEBA_EXTRACT_LIMIT', 10000))

    # External Data Sources Configuration
    ENABLE_WIKIPEDIA_SOURCE = os.environ.get('ENABLE_WIKIPEDIA_SOURCE', 'true').lower() == 'true'
    ENABLE_TATOEBA_SOURCE = os.environ.get('ENABLE_TATOEBA_SOURCE', 'true').lower() == 'true'
    ENABLE_NEWS_SOURCE = os.environ.get('ENABLE_NEWS_SOURCE', 'false').lower() == 'true'

    # API Rate Limiting
    API_RATE_LIMIT = os.environ.get('API_RATE_LIMIT', '100 per hour')
    API_RATE_LIMIT_STORAGE_URL = os.environ.get('API_RATE_LIMIT_STORAGE_URL')

    # Logging Configuration
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/kikuyu.log')
    LOG_MAX_BYTES = int(os.environ.get('LOG_MAX_BYTES', 10485760))  # 10MB
    LOG_BACKUP_COUNT = int(os.environ.get('LOG_BACKUP_COUNT', 5))

    # Session Configuration
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        # Create necessary directories
        os.makedirs(app.config['CORPUS_DATA_DIR'], exist_ok=True)
        os.makedirs(app.config['CORPUS_DOWNLOAD_DIR'], exist_ok=True)
        os.makedirs('instance', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

        # Configure logging
        import logging
        from logging.handlers import RotatingFileHandler

        if not app.debug:
            file_handler = RotatingFileHandler(
                app.config['LOG_FILE'],
                maxBytes=app.config['LOG_MAX_BYTES'],
                backupCount=app.config['LOG_BACKUP_COUNT']
            )
            file_handler.setFormatter(logging.Formatter(
                '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
            ))
            file_handler.setLevel(getattr(logging, app.config['LOG_LEVEL']))
            app.logger.addHandler(file_handler)
            app.logger.setLevel(getattr(logging, app.config['LOG_LEVEL']))
            app.logger.info('Kikuyu Translation Platform startup')

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
