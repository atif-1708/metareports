from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'employee'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reports = db.relationship('Report', backref='user', lazy='dynamic')
    notifications = db.relationship('Notification', backref='user', lazy='dynamic',
                                   primaryjoin="User.id == Notification.user_id")
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def __repr__(self):
        return f'<User {self.username}>'


class Report(db.Model):
    __tablename__ = 'reports'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    week_end = db.Column(db.Date, nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    approved = db.Column(db.Boolean, default=False)
    admin_notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    campaigns = db.relationship('Campaign', backref='report', lazy='dynamic', cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Report {self.title}>'


class Campaign(db.Model):
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('reports.id'), nullable=False)
    campaign_name = db.Column(db.String(200), nullable=False)
    purchases = db.Column(db.Integer, nullable=False)
    cost_per_purchase = db.Column(db.Float, nullable=False)
    
    @property
    def total_cost(self):
        return self.purchases * self.cost_per_purchase
    
    def __repr__(self):
        return f'<Campaign {self.campaign_name}>'


class NotificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Change to match __tablename__
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    sent_by = db.Column(db.Integer, db.ForeignKey('users.id'))  # Change this one too
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship("User", foreign_keys=[user_id])
    sender = db.relationship("User", foreign_keys=[sent_by])
class Notification(db.Model):
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    category = db.Column(db.String(50), default='info')  # info, warning, alert
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Notification {self.id}>'


# This should be in your models.py file
class ReportDeadline(db.Model):
    __tablename__ = 'report_deadlines'
    
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.Integer, nullable=False)  # 0-6 for Monday-Sunday
    hour = db.Column(db.Integer, nullable=False)
    minute = db.Column(db.Integer, nullable=False)
    am_pm = db.Column(db.String(2), nullable=False, default="PM")  # Make sure this field exists
    reminder_hours_before = db.Column(db.Integer, nullable=False, default=24)
    is_active = db.Column(db.Boolean, default=True)
    
    def __repr__(self):
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = days[self.day_of_week]
        minute_str = f"{self.minute:02d}" if self.minute < 10 else str(self.minute)
        return f"Deadline({day_name} at {self.hour}:{minute_str} {self.am_pm})"
    
    def get_24h_hour(self):
        """Convert 12h to 24h format"""
        if self.am_pm == 'PM' and self.hour != 12:
            return self.hour + 12
        elif self.am_pm == 'AM' and self.hour == 12:
            return 0
        return self.hour
class MissingReport(db.Model):
    __tablename__ = 'missing_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    report_week = db.Column(db.String(50), nullable=False)  # Store as "2023-01-01 to 2023-01-07"
    deadline_date = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved = db.Column(db.Boolean, default=False)
    @property
    def formatted_deadline(self):
        if self.deadline_date:
            # Format the datetime in a readable way
            return self.deadline_date.strftime('%Y-%m-%d %I:%M %p')
        return "No deadline set"
    # Relationship
    user = db.relationship('User', backref=db.backref('missing_reports', lazy='dynamic'))