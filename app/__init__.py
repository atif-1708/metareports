import os
from flask import Flask, app
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_mail import Mail
from apscheduler.schedulers.background import BackgroundScheduler
from app.models import db, User, ReportDeadline
from app.config import config

# Initialize extensions
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'
migrate = Migrate()
mail = Mail()
scheduler = BackgroundScheduler(timezone='Asia/Karachi')


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_app(config_name='default'):
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Set timezone configuration
    os.environ['TZ'] = 'Asia/Karachi'
    app.config['TIMEZONE'] = 'Asia/Karachi'
    
    # Ensure the uploads directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Initialize extensions with the app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    # Register blueprints
    from app.routes.main_routes import main
    from app.routes.auth_routes import auth
    from app.routes.admin_routes import admin
    from app.routes.employee_routes import employee
    
    app.register_blueprint(main)
    app.register_blueprint(auth)
    app.register_blueprint(admin)
    app.register_blueprint(employee)
    
    # Add timezone utility functions to templates
    from app.utils import utc_to_local, get_local_now, check_missing_reports, check_deadline_and_notify
    
    @app.context_processor
    def utility_processor():
        def get_formatted_deadline():
            """Returns formatted deadline string for use in templates"""
            try:
                # Force a fresh query from the database to avoid cached results
                db.session.expire_all()
                current_deadline = ReportDeadline.query.filter_by(is_active=True).first()
                
                if not current_deadline:
                    return "Friday at 5:00 PM"  # Default value
                
                days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                day_name = days[current_deadline.day_of_week]
                minute_str = f"{current_deadline.minute:02d}" if current_deadline.minute < 10 else str(current_deadline.minute)
                
                return f"{day_name} at {current_deadline.hour}:{minute_str} {current_deadline.am_pm}"
            except Exception as e:
                # In case of any error, return a default value
                return "Friday at 5:00 PM"
        
        return {
            'utc_to_local': utc_to_local,
            'now': get_local_now,
            'get_formatted_deadline': get_formatted_deadline
        }
    
    @app.template_filter('format_datetime')
    def format_datetime(value, format='%b %d, %Y at %I:%M %p'):
        """Format a UTC datetime to local time with a given format."""
        if value is None:
            return ""
        local_dt = utc_to_local(value)
        return local_dt.strftime(format)
    
    # Setup initial data
    with app.app_context():
        db.create_all()
        
        # Create admin user if it doesn't exist
        admin_user = User.query.filter_by(username=app.config['ADMIN_USERNAME']).first()
        if not admin_user:
            admin_user = User(
                username=app.config['ADMIN_USERNAME'],
                email=app.config['ADMIN_EMAIL'],
                first_name='Admin',
                last_name='User',
                role='admin',
                is_active=True
            )
            admin_user.set_password(app.config['ADMIN_PASSWORD'])
            db.session.add(admin_user)
            
        # Create default report deadline if not exists
        if not ReportDeadline.query.filter_by(is_active=True).first():
            default_deadline = ReportDeadline(
                day_of_week=app.config['DEFAULT_DEADLINE_DAY'],
                hour=app.config['DEFAULT_DEADLINE_HOUR'],
                minute=app.config['DEFAULT_DEADLINE_MINUTE'],
                am_pm='PM',  # Add default AM/PM value
                reminder_hours_before=app.config['REMINDER_HOURS_BEFORE'],
                is_active=True
            )
            db.session.add(default_deadline)
            db.session.commit()
    
    # Initialize and start scheduler
    if not scheduler.running:
        # Weekly check (as a backup)
        scheduler.add_job(
            func=check_missing_reports,
            trigger='cron',
            day_of_week='sat',  # Run every Saturday
            hour=0,
            # At midnight PKT
            id='check_missing_reports'
        )
        
        # Hourly job to check if it's time to check for deadline and send notifications
        scheduler.add_job(
            func=check_deadline_and_notify,
            trigger='interval',
            minutes=60,  # Run every hour
            id='check_deadline_and_notify'
        )
        
        # Run once at startup to ensure we don't miss anything
        with app.app_context():
            check_deadline_and_notify()
            
        scheduler.start()
        
    @app.context_processor
    def inject_models():
        from app.models import MissingReport, db
        return dict(MissingReport=MissingReport, db=db)
       
    return app