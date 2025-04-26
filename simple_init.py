# simple_init.py
from app import create_app
from app.models import db, User

app = create_app('development')

with app.app_context():
    # Create database tables
    db.create_all()
    
    # Check if admin user exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        # Create admin user
        admin = User(
            username='admin',
            email='admin@flaskreports.com',
            first_name='Admin',
            last_name='User',
            role='admin',
            is_active=True
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin user created!")
    
    print("Database initialized successfully!")