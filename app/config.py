import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    # General Flask config
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'very-secret-key-for-development'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://reportuser:admin@localhost:5432/flask_reports'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configs
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    ALLOWED_EXTENSIONS = {'csv'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload size
    
    # Email configuration
    MAIL_SERVER = 'live.smtp.mailtrap.io'
    MAIL_PORT = 587  # As recommended in your credentials
    MAIL_USE_TLS = True
    MAIL_USERNAME = 'api'  # Use this username for API-based sending
    MAIL_PASSWORD = '005c885fc68a4477ba39a34f12b4c7b5' 
    MAIL_DEFAULT_SENDER = 'noreply@rajabbuttperfume.online'
    
    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    
    # Admin credentials
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL') or 'admin@goodigital.com'
    
    # Report deadline defaults (Friday 5 PM)
    DEFAULT_DEADLINE_DAY = 4  # Friday (0=Monday, 6=Sunday)
    DEFAULT_DEADLINE_HOUR = 17  # 5 PM
    DEFAULT_DEADLINE_MINUTE = 0
    REMINDER_HOURS_BEFORE = 24  # Send reminder 24 hours before deadline

class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False

class TestingConfig(Config):
    DEBUG = False
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False

class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    
    # In production, these should be set by environment variables
    SECRET_KEY = os.environ.get('SECRET_KEY')
    # Default to PostgreSQL if DATABASE_URL is not set
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://reportuser:admin@localhost:5432/flask_reports'

# Configuration dictionary to select the appropriate configuration
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}