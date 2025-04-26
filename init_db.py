# init_db.py
from app import create_app, db

app = create_app('development')
with app.app_context():
    db.create_all()
    print("Database tables created successfully!")