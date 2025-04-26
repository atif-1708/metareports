from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user
from app.models import Notification, db
from flask_login import current_user, login_required
main = Blueprint('main', __name__)

@main.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
    return redirect(url_for('auth.login'))

from app.models import Notification, db

@main.route('/notifications')
@login_required  # Use the decorator instead
def notifications():
    # Mark all notifications as read
    unread_notifications = Notification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).all()
    
    for notification in unread_notifications:
        notification.is_read = True
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error updating notification status: {str(e)}")
    
    # Get all notifications for the current user
    all_notifications = Notification.query.filter_by(
        user_id=current_user.id
    ).order_by(Notification.created_at.desc()).all()
    
    return render_template(
        'notifications.html',
        title='Notifications',
        notifications=all_notifications
    )
