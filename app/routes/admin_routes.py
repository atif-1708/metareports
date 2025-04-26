from flask import Blueprint, jsonify, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import pytz
from sqlalchemy import func
from app.models import MissingReport, User, Report, Campaign
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, EmailField, BooleanField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, ValidationError, NumberRange
from functools import wraps

from app.models import db, User, Report, Campaign, ReportDeadline, NotificationLog
from app.utils import get_dashboard_stats, get_employee_stats, get_report_stats, create_notification, send_email_notification

# Define Karachi timezone
karachi_tz = pytz.timezone('Asia/Karachi')

admin = Blueprint('admin', __name__, url_prefix='/admin')
@admin.app_context_processor
def inject_missing_count():
    # Only query if the user is authenticated and is an admin
    if current_user.is_authenticated and current_user.role == 'admin':
        missing_count = MissingReport.query.filter_by(resolved=False).count()
    else:
        missing_count = 0
    return {'missing_count': missing_count}
# Timezone conversion utility functions
def get_current_karachi_time():
    """Get the current time in Karachi timezone"""
    return datetime.now(karachi_tz)

def convert_to_utc(karachi_datetime):
    """Convert a Karachi timezone datetime to UTC for database storage"""
    if not karachi_datetime:
        return None
    
    # If the datetime doesn't have timezone info, assume it's in Karachi time
    if not karachi_datetime.tzinfo:
        karachi_datetime = karachi_tz.localize(karachi_datetime)
        
    # Convert to UTC
    return karachi_datetime.astimezone(pytz.UTC)

def convert_to_karachi(utc_datetime):
    """Convert a UTC datetime to Karachi timezone for display"""
    if not utc_datetime:
        return None
        
    # If the datetime doesn't have timezone info, assume it's in UTC
    if not utc_datetime.tzinfo:
        utc_datetime = utc_datetime.replace(tzinfo=pytz.UTC)
        
    # Convert to Karachi timezone
    return utc_datetime.astimezone(karachi_tz)

# Admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Forms
class NewEmployeeForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = EmailField('Email', validators=[DataRequired(), Email()])
    first_name = StringField('First Name', validators=[DataRequired()])
    last_name = StringField('Last Name', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField(
        'Confirm Password', 
        validators=[DataRequired(), EqualTo('password')]
    )
    submit = SubmitField('Create Employee')
    
    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user is not None:
            raise ValidationError('Please use a different username.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError('Please use a different email address.')

class DeadlineForm(FlaskForm):
    day_of_week = SelectField('Day of Week', choices=[
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'),
        (3, 'Thursday'), (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday')
    ], coerce=int)
    
    hour = SelectField('Hour', choices=[
        (1, '1'), (2, '2'), (3, '3'), (4, '4'), 
        (5, '5'), (6, '6'), (7, '7'), (8, '8'),
        (9, '9'), (10, '10'), (11, '11'), (12, '12')
    ], coerce=int)
    
    minute = SelectField('Minute', choices=[(i, f'{i:02d}') for i in range(0, 60)], coerce=int)
    
    am_pm = SelectField('AM/PM', choices=[
        ('AM', 'AM'), 
        ('PM', 'PM')
    ], default='PM')
    
    reminder_hours_before = IntegerField('Reminder Hours Before', validators=[
        DataRequired(), 
        NumberRange(min=1, max=72)
    ])
    submit = SubmitField('Save Settings')

# Make utility functions available to templates
@admin.app_context_processor
def inject_utilities():
    return dict(
        convert_to_karachi=convert_to_karachi,
        get_current_karachi_time=get_current_karachi_time
    )

# Routes
@admin.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Get date filter parameters from request
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    
    # Convert to date objects if provided
    start_date = None
    end_date = None
    
    if start_date_str:
        try:
            # Parse and convert to date object in Karachi time
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid start date format. Please use YYYY-MM-DD format.', 'warning')
    
    if end_date_str:
        try:
            # Parse and convert to date object in Karachi time
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid end date format. Please use YYYY-MM-DD format.', 'warning')
    
    # Pass date filters to your stats function
    stats = get_dashboard_stats(role='admin', start_date=start_date, end_date=end_date)
    # Add missing reports alert data
    missing_count = MissingReport.query.filter_by(resolved=False).count()

    return render_template(
        'admin/dashboard.html', 
        title='Admin Dashboard', 
        missing_count=missing_count,
        stats=stats,
    )

@admin.route('/employees')
@login_required
@admin_required
def employees():
    employees = User.query.filter_by(role='employee').all()
    return render_template('admin/employees.html', title='Manage Employees', employees=employees)

@admin.route('/employees/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_employee():
    form = NewEmployeeForm()
    if form.validate_on_submit():
        try:
            user = User(
                username=form.username.data,
                email=form.email.data,
                first_name=form.first_name.data,
                last_name=form.last_name.data,
                role='employee',
                is_active=True
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            
            # Get current time in Karachi timezone for notification
            now_karachi = get_current_karachi_time()
            now_utc = convert_to_utc(now_karachi)
            
            # Create welcome notification
            create_notification(
                user.id, 
                f"Welcome to GOODIGITAL, {user.first_name}! Your account has been created.",
                'info'
            )
            
            # Send welcome email - corrected to pass a single email string, not a list
            try:
                send_email_notification(
                    "Welcome to GOODIGITAL",
                    user.email,  # Remove the square brackets
                    f"""
                    <h3>Welcome to GOODIGITAL!</h3>
                    <p>Hello {user.first_name},</p>
                    <p>Your account has been created in the GOODIGITAL system. You can now log in with the following credentials:</p>
                    <p>Username: {user.username}<br>
                    Password: {form.password.data}</p>
                    """
                )
                flash(f'Employee "{form.username.data}" has been created successfully and email sent!', 'success')
            except Exception as e:
                # Handle email sending failure
                current_app.logger.error(f"Failed to send email: {str(e)}")
                flash(f'Employee "{form.username.data}" created but email notification failed.', 'warning')
                
            return redirect(url_for('admin.employees'))
            
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating employee: {str(e)}")
            flash(f'Error creating employee: {str(e)}', 'danger')
            
    return render_template('admin/new_employee.html', title='Add New Employee', form=form)

@admin.route('/employees/<int:employee_id>')
@login_required
@admin_required
def employee_details(employee_id):
    try:
        employee = User.query.filter_by(id=employee_id, role='employee').first_or_404()
        
        try:
            stats = get_employee_stats(employee_id)
        except Exception as stats_error:
            print(f"Error in get_employee_stats: {str(stats_error)}")
            # Provide empty stats as fallback
            stats = {
                'total_reports': 0,
                'approved_reports': 0,
                'pending_reports': 0,
                'rejected_reports': 0,
                'avg_response_time': 'N/A'
            }
        
        return render_template(
            'admin/employee_details.html', 
            title=f'Employee: {employee.first_name} {employee.last_name}', 
            employee=employee, 
            stats=stats,
            Report=Report  # Add this line to make Report available in the template
        )
    except Exception as e:
        print(f"ERROR in employee_details route: {str(e)}")
        # Return a simple error page
        return f"<h1>Error</h1><p>{str(e)}</p>", 500

@admin.route('/employees/<int:employee_id>/toggle_status', methods=['POST'])
@login_required
@admin_required
def toggle_employee_status(employee_id):
    employee = User.query.filter_by(id=employee_id, role='employee').first_or_404()
    employee.is_active = not employee.is_active
    db.session.commit()
    
    status = "activated" if employee.is_active else "deactivated"
    flash(f'Employee "{employee.username}" has been {status}.', 'success')
    
    # Notify employee
    message = f"Your account has been {status}."
    create_notification(employee.id, message, 'info' if employee.is_active else 'warning')
    
    # Send email notification
    send_email_notification(
        f"Account {status.capitalize()}",
        [employee.email],
        f"""
        <h3>Account {status.capitalize()}</h3>
        <p>Hello {employee.first_name},</p>
        <p>Your account has been {status} by an administrator.</p>
        {'<p>You can now log in to the system.</p>' if employee.is_active else '<p>You will not be able to log in until your account is reactivated.</p>'}
        """
    )
    
    return redirect(url_for('admin.employees'))

@admin.route('/employees/<int:employee_id>/reports')
@login_required
@admin_required
def employee_reports(employee_id):
    employee = User.query.filter_by(id=employee_id, role='employee').first_or_404()
    reports = Report.query.filter_by(user_id=employee_id).order_by(Report.submitted_at.desc()).all()
    
    # Convert report timestamps from UTC to Karachi time for display
    for report in reports:
        if report.submitted_at:
            report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    return render_template(
        'admin/employee_reports.html',
        title=f'Reports from {employee.first_name} {employee.last_name}',
        employee=employee,
        reports=reports
    )

@admin.route('/reports')
@login_required
@admin_required
def all_reports():
    try:
        # Get date filter parameters
        start_date_str = request.args.get('start_date', '')
        end_date_str = request.args.get('end_date', '')
        
        # Base query
        query = Report.query
        
        # Apply date filters if provided
        if start_date_str:
            try:
                # Parse the start date and localize it to Karachi timezone
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_date = karachi_tz.localize(start_date)
                # Convert to UTC for database query
                start_date_utc = start_date.astimezone(pytz.UTC)
                query = query.filter(Report.submitted_at >= start_date_utc)
            except ValueError:
                flash('Invalid start date format. Please use YYYY-MM-DD format.', 'warning')
        else:
            start_date_str = ''
        
        if end_date_str:
            try:
                # Parse the end date and localize it to Karachi timezone
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_date = karachi_tz.localize(end_date)
                # Add one day to include the end date fully (until midnight)
                end_date = end_date + timedelta(days=1)
                # Convert to UTC for database query
                end_date_utc = end_date.astimezone(pytz.UTC)
                query = query.filter(Report.submitted_at < end_date_utc)
            except ValueError:
                flash('Invalid end date format. Please use YYYY-MM-DD format.', 'warning')
        else:
            end_date_str = ''
        
        # Get all reports, ordered by submission date (newest first)
        reports = query.order_by(Report.submitted_at.desc()).all()
        
        # Convert report timestamps from UTC to Karachi time for display
        for report in reports:
            if report.submitted_at:
                # Store local time for template display (don't save to database)
                report.local_submitted_at = convert_to_karachi(report.submitted_at)
        
        return render_template(
            'admin/all_reports.html',
            title='All Reports',
            reports=reports,
            start_date=start_date_str,
            end_date=end_date_str
        )
    except Exception as e:
        # Log the error
        print(f"ERROR in all_reports: {str(e)}")
        # Return a user-friendly error page
        return render_template('error.html', 
                              title='Error Loading Reports',
                              message=f"There was a problem loading the reports: {str(e)}"), 500

@admin.route('/reports/<int:report_id>')
@login_required
@admin_required
def report_details(report_id):
    report = Report.query.get_or_404(report_id)
    employee = User.query.get(report.user_id)
    stats = get_report_stats(report_id)
    campaigns = Campaign.query.filter_by(report_id=report_id).all()
    
    # Convert timestamps to Karachi time
    if report.submitted_at:
        report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    return render_template(
        'admin/report_details.html',
        title=f'Report Details: {report.title}',
        report=report,
        employee=employee,
        stats=stats,
        campaigns=campaigns
    )

@admin.route('/reports/<int:report_id>/toggle_approval', methods=['POST'])
@login_required
@admin_required
def toggle_report_approval(report_id):
    report = Report.query.get_or_404(report_id)
    report.approved = not report.approved
    
    # Get admin notes from form
    report.admin_notes = request.form.get('admin_notes', '')
    
    db.session.commit()
    
    status = "approved" if report.approved else "unapproved"
    flash(f'Report "{report.title}" has been {status}.', 'success')
    
    # Notify employee
    employee = User.query.get(report.user_id)
    message = f"Your report '{report.title}' has been {status}."
    if report.admin_notes:
        message += f" Admin notes: {report.admin_notes}"
    
    create_notification(employee.id, message, 'success' if report.approved else 'warning')
    
    # Send email notification
    send_email_notification(
        f"Report {status.capitalize()}",
        [employee.email],
        f"""
        <h3>Report {status.capitalize()}</h3>
        <p>Hello {employee.first_name},</p>
        <p>Your report '{report.title}' has been {status} by an administrator.</p>
        {f'<p><strong>Admin notes:</strong> {report.admin_notes}</p>' if report.admin_notes else ''}
        """
    )
    
    return redirect(url_for('admin.report_details', report_id=report_id))

@admin.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    form = DeadlineForm()
    current_deadline = ReportDeadline.query.filter_by(is_active=True).first()
    
    if form.validate_on_submit():
        try:
            # Deactivate all other deadlines first to ensure only one active deadline
            ReportDeadline.query.update({'is_active': False})
            db.session.commit()
            
            if not current_deadline:
                current_deadline = ReportDeadline(is_active=True)
                db.session.add(current_deadline)
            else:
                current_deadline.is_active = True
            
            # Update deadline with form data
            current_deadline.day_of_week = form.day_of_week.data
            current_deadline.hour = form.hour.data
            current_deadline.minute = form.minute.data
            current_deadline.am_pm = form.am_pm.data
            current_deadline.reminder_hours_before = form.reminder_hours_before.data
            
            db.session.commit()
            
            # Format deadline for flash message
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            day_name = days[current_deadline.day_of_week]
            minute_str = f"{current_deadline.minute:02d}" if current_deadline.minute < 10 else str(current_deadline.minute)
            formatted = f"{day_name} at {current_deadline.hour}:{minute_str} {current_deadline.am_pm}"
            
            flash(f'Deadline settings updated to: {formatted}', 'success')
            # Also flash with the deadline category to ensure it's available in templates
            flash(formatted, 'deadline')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating settings: {str(e)}', 'danger')
        
        return redirect(url_for('admin.settings'))
    
    if request.method == 'GET' and current_deadline:
        form.day_of_week.data = current_deadline.day_of_week
        form.hour.data = current_deadline.hour
        form.minute.data = current_deadline.minute
        form.am_pm.data = current_deadline.am_pm
        form.reminder_hours_before.data = current_deadline.reminder_hours_before
    
    return render_template('admin/settings.html',
                          deadline_form=form,
                          current_deadline=current_deadline)

@admin.route('/employee/<int:employee_id>/dashboard')
@login_required
@admin_required
def employee_dashboard(employee_id):
    # Get the employee
    employee = User.query.get_or_404(employee_id)
    
    # Get date filter parameters
    start_date_str = request.args.get('start_date', '')
    end_date_str = request.args.get('end_date', '')
    
    # Parse dates if provided
    start_date = None
    end_date = None
    
    if start_date_str:
        try:
            # Parse and localize to Karachi time
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            start_date = karachi_tz.localize(start_date)
            # Convert to UTC for database query
            start_date = start_date.astimezone(pytz.UTC)
        except ValueError:
            flash('Invalid start date format', 'warning')
    
    if end_date_str:
        try:
            # Parse and localize to Karachi time
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date = karachi_tz.localize(end_date)
            # Add one day to include the end date fully (until midnight)
            end_date = end_date + timedelta(days=1)
            # Convert to UTC for database query
            end_date = end_date.astimezone(pytz.UTC)
        except ValueError:
            flash('Invalid end date format', 'warning')
    
    # Base queries with date filters
    reports_query = Report.query.filter_by(user_id=employee_id)
    if start_date:
        reports_query = reports_query.filter(Report.submitted_at >= start_date)
    if end_date:
        reports_query = reports_query.filter(Report.submitted_at < end_date)
    
    # Get reports for the employee with date filters
    reports = reports_query.order_by(Report.submitted_at.desc()).all()
    
    # Convert timestamps to Karachi time for display
    for report in reports:
        if report.submitted_at:
            report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    # Get campaigns for these reports
    campaign_ids = []
    for report in reports:
        for campaign in report.campaigns:
            campaign_ids.append(campaign.id)
    
    campaigns = Campaign.query.filter(Campaign.id.in_(campaign_ids)).all() if campaign_ids else []
    
    # Calculate statistics (same as employee dashboard)
    stats = {
        'total_reports': len(reports),
        'approved_reports': sum(1 for r in reports if r.approved),
        'total_campaigns': len(campaigns),
        'total_purchases': sum(c.purchases or 0 for c in campaigns),
        'total_cost': sum(c.cost_per_purchase * max(c.purchases or 0, 1) for c in campaigns if c.cost_per_purchase is not None),
        'recent_reports': reports[:5],  # Show first 5 reports
        'top_campaigns': sorted(campaigns, key=lambda c: c.purchases or 0, reverse=True)[:10]  # Top 10 by purchases
    }
    
    # Calculate average cost per purchase (avoid division by zero)
    if stats['total_purchases'] > 0:
        stats['avg_cost_per_purchase'] = stats['total_cost'] / stats['total_purchases']
    else:
        stats['avg_cost_per_purchase'] = 0
    
    # Add CPR distribution statistics
    stats['total_zero_campaigns'] = sum(1 for c in campaigns if c.purchases == 0 or c.purchases is None)
    
    # Debug campaign data
    print(f"Total campaigns: {len(campaigns)}")
    
    # Get campaigns with valid purchase and CPR values
    campaigns_with_valid_data = []
    for campaign in campaigns:
        # Check if campaign has valid purchase and CPR data
        if campaign.purchases is not None and campaign.purchases > 0 and campaign.cost_per_purchase is not None:
            # Try to get the campaign name from various possible attributes
            campaign_name = None
            for attr in ['name', 'title', 'campaign_name', 'campaign_title']:
                if hasattr(campaign, attr) and getattr(campaign, attr):
                    campaign_name = getattr(campaign, attr)
                    break
            
            if not campaign_name:
                # If no name attribute found, use ID as fallback
                campaign_name = f'Campaign #{campaign.id}'
            
            # Only add each campaign once (avoid duplicates)
            campaign_data = {
                'id': campaign.id,
                'name': campaign_name,
                'cost_per_purchase': campaign.cost_per_purchase,
                'purchases': campaign.purchases
            }
            
            # Check if this campaign is already in the list
            if not any(c['id'] == campaign.id for c in campaigns_with_valid_data):
                campaigns_with_valid_data.append(campaign_data)
    
    print(f"Campaigns with valid data: {len(campaigns_with_valid_data)}")
    
    # Sort by cost_per_purchase (CPR) in ascending order
    # Take all available campaigns (up to 10 max)
    campaign_count = min(len(campaigns_with_valid_data), 10)
    top_campaigns_by_lowest_cpr = sorted(
        campaigns_with_valid_data, 
        key=lambda c: c['cost_per_purchase'],
        reverse=False
    )[:campaign_count]
    
    # Debug the top campaigns
    print(f"Top campaigns by lowest CPR: {len(top_campaigns_by_lowest_cpr)}")
    for campaign in top_campaigns_by_lowest_cpr:
        print(f"  {campaign['name']}: CPR = {campaign['cost_per_purchase']}")
    
    # Add to stats
    stats['top_campaigns_by_lowest_cpr'] = top_campaigns_by_lowest_cpr
    
    # CPR ranges (considering campaigns with purchases)
    campaigns_with_purchases = [c for c in campaigns if c.purchases is not None and c.purchases > 0 and c.cost_per_purchase is not None]
    stats['campaigns_with_purchases'] = len(campaigns_with_purchases)
    
    stats['cpr_ranges'] = {
        'range_1_200': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase is not None and 
                         c.cost_per_purchase >= 1 and c.cost_per_purchase <= 200),
        'range_201_400': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase is not None and 
                           c.cost_per_purchase > 200 and c.cost_per_purchase <= 400),
        'range_401_600': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase is not None and 
                           c.cost_per_purchase > 400 and c.cost_per_purchase <= 600),
        'range_601_plus': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase is not None and 
                            c.cost_per_purchase > 600)
    }
    
    return render_template('admin/employee_dashboard.html',
                          title=f'{employee.first_name} {employee.last_name}\'s Dashboard',
                          stats=stats,
                          employee=employee)

# Utility function to format deadline time for display
def format_deadline():
    deadline = ReportDeadline.query.filter_by(is_active=True).first()
    if not deadline:
        return "No deadline set"
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", 
            "Friday", "Saturday", "Sunday"]
    return (f"{days[deadline.day_of_week]} at "
            f"{deadline.hour}:{deadline.minute:02d} "
            f"{'PM' if deadline.is_pm else 'AM'} (PKT)")

# Function to calculate the next deadline datetime in Karachi timezone
def get_next_deadline_datetime():
    deadline = ReportDeadline.query.filter_by(is_active=True).first()
    if not deadline:
        return None
    
    karachi_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(karachi_tz)
    deadline_hour = deadline.get_24h_time()
    
    days_ahead = deadline.day_of_week - now.weekday()
    if days_ahead <= 0:  # Already passed this week
        days_ahead += 7
    
    next_deadline = now.replace(
        hour=deadline_hour,
        minute=deadline.minute,
        second=0,
        microsecond=0
    ) + timedelta(days=days_ahead)
    
    return next_deadline
@admin.route('/missing-reports')
@login_required
@admin_required
def missing_reports():
    # Get all active missing reports
    missing = MissingReport.query.filter_by(resolved=False).all()
    
    for report in missing:
        if report.deadline_date:
            # Simply format the original datetime in 12-hour format
            report.formatted_deadline = report.deadline_date.strftime('%Y-%m-%d %I:%M %p')
    
    return render_template(
        'admin/missing_reports.html',
        missing=missing
    )
from flask import Response
import io
import csv

@admin.route('/reports/<int:report_id>/download')
@login_required
@admin_required
def download_report(report_id):
    report = Report.query.get_or_404(report_id)
    stats = get_report_stats(report_id)
    
    if 'error' in stats:
        flash(stats['error'], 'danger')
        return redirect(url_for('admin.reports'))

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Excel-style formatting for headers
    def bold(text):
        return f'**{text}**'  # Will show as bold in Excel

    # Report Header
    writer.writerow([bold('REPORT ANALYSIS')])
    writer.writerow([f"Employee: {report.user.first_name} {report.user.last_name}"])
    writer.writerow([f"Period: {report.week_start.strftime('%d %b %Y')} to {report.week_end.strftime('%d %b %Y')}"])
    writer.writerow([])

    # Summary Statistics
    writer.writerow([bold('SUMMARY STATISTICS')])
    writer.writerow([])
    writer.writerow([bold('Metric'), bold('Value')])
    writer.writerow(['Total Campaigns', stats['total_campaigns']])
    writer.writerow(['Campaigns With Purchases', stats['total_non_zero_campaigns']])
    writer.writerow(['Zero Purchase Campaigns', stats['total_zero_campaigns']])
    writer.writerow(['Total Purchases', stats['total_purchases']])
    writer.writerow(['Total Cost', f"Rs {stats['total_cost']:,.2f}"])
    writer.writerow(['Average CPR', f"Rs {stats['avg_cost_per_purchase']:.2f}"])
    writer.writerow([])

    # Campaign Performance
    writer.writerow([bold('TOP PERFORMING CAMPAIGNS')])
    writer.writerow([])
    writer.writerow([bold('By Purchases')])
    writer.writerow(['Campaign', 'Purchases', 'CPR', 'Total Cost'])
    for campaign in stats['top_campaigns_by_purchases']:
        writer.writerow([
            campaign.campaign_name,
            campaign.purchases,
            f"Rs {campaign.cost_per_purchase:.2f}",
            f"Rs {(campaign.purchases * campaign.cost_per_purchase):,.2f}"
        ])
    writer.writerow([])

    writer.writerow([bold('By Cost Efficiency')])
    writer.writerow(['Campaign', 'CPR', 'Purchases', 'Total Cost'])
    for campaign in stats['top_campaigns_by_cost_per_purchase']:
        writer.writerow([
            campaign.campaign_name,
            f"Rs {campaign.cost_per_purchase:.2f}",
            campaign.purchases,
            f"Rs {(campaign.purchases * campaign.cost_per_purchase):,.2f}"
        ])
    writer.writerow([])

    # All Campaigns
    writer.writerow([bold('ALL CAMPAIGNS')])
    writer.writerow(['Campaign', 'Purchases', 'CPR', 'Total Cost'])
    for campaign in stats['all_campaigns_by_cpr']:
        writer.writerow([
            campaign.campaign_name,
            campaign.purchases,
            f"Rs {campaign.cost_per_purchase:.2f}",
            f"Rs {(campaign.purchases * campaign.cost_per_purchase):,.2f}"
        ])
    writer.writerow([])

    # Zero Purchase Campaigns
    if stats['total_zero_campaigns'] > 0:
        writer.writerow([bold('ZERO PURCHASE CAMPAIGNS')])
        writer.writerow(['Campaign', 'Potential CPR', 'Potential Cost'])
        for campaign in stats['zero_purchase_campaigns']:
            writer.writerow([
                campaign.campaign_name,
                f"Rs {campaign.cost_per_purchase:.2f}" if campaign.cost_per_purchase else 'N/A',
                f"Rs {campaign.cost_per_purchase:,.2f}" if campaign.cost_per_purchase else 'N/A'
            ])

    output.seek(0)
    
    # Create filename
    filename = f"{report.user.username}_report_{report.week_start.strftime('%Y%m%d')}.csv"
    
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-disposition": f"attachment; filename={filename}",
            "Content-type": "text/csv; charset=utf-8"
        }
    )
@admin.route('/dashboard/download-report')
@login_required
@admin_required
def download_dashboard_report():
    try:
        # Get the date filters from request
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # Convert string dates to date objects if they exist
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = None
        
        # Get dashboard stats with filters
        stats = get_dashboard_stats(start_date=start_date, end_date=end_date)
        
        # Ensure stats has all required keys with default values
        required_stats = {
            'total_employees': 0,
            'active_employees': 0,
            'total_reports': 0,
            'reports_this_month': 0,
            'approval_rate': 0,
            'total_purchases': 0,
            'total_cost': 0,
            'monthly_purchases': 0,
            'monthly_cost': 0,
            'top_employees': [],
            'top_employees_by_good_cpr': [],
            'recent_reports': [],
            'top_campaigns_by_lowest_cpr': [],
            'total_campaigns': 0,
            'total_zero_campaigns': 0,
            'campaigns_with_purchases': 0,
            'cpr_ranges': {
                'range_1_200': 0,
                'range_201_400': 0,
                'range_401_600': 0,
                'range_601_plus': 0
            }
        }
        
        # Merge the actual stats with default values
        for key in required_stats:
            if key not in stats:
                stats[key] = required_stats[key]
            elif key == 'cpr_ranges':
                for subkey in required_stats['cpr_ranges']:
                    if subkey not in stats['cpr_ranges']:
                        stats['cpr_ranges'][subkey] = 0
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Helper functions for formatting
        def section_header(text):
            writer.writerow([])
            writer.writerow([text.upper()])
            writer.writerow([])
        
        def bold(text):
            return f"**{text}**"
        
        def currency(value):
            return f"Rs {value:,.2f}" if value else "Rs 0.00"
        
        def percentage(value):
            return f"{value:.1f}%" if value else "0.0%"
        
        # Report Header
        writer.writerow([bold("ADMIN DASHBOARD REPORT")])
        writer.writerow([f"Generated on: {datetime.now().strftime('%d %b %Y, %I:%M %p')}"])
        
        date_range = []
        if stats.get('start_date'):
            date_range.append(stats['start_date'].strftime('%d %b %Y'))
        if stats.get('end_date'):
            date_range.append(stats['end_date'].strftime('%d %b %Y'))
        
        if date_range:
            writer.writerow([f"Date Range: {' to '.join(date_range)}"])
        writer.writerow([])
        
        # Summary Statistics
        section_header("Summary Statistics")
        writer.writerow([bold("Metric"), bold("Total"), bold("This Month")])
        writer.writerow(["Employees", stats['total_employees'], ""])
        
        active_percentage = (stats['active_employees'] / stats['total_employees'] * 100) if stats['total_employees'] > 0 else 0
        writer.writerow(["Active Employees", stats['active_employees'], f"{active_percentage:.1f}%"])
        writer.writerow(["Total Reports", stats['total_reports'], stats['reports_this_month']])
        writer.writerow(["Approval Rate", percentage(stats['approval_rate']), ""])
        writer.writerow(["Total Purchases", "{:,}".format(stats['total_purchases']), 
                        "{:,}".format(stats['monthly_purchases'])])
        writer.writerow(["Total Cost", currency(stats['total_cost']), 
                        currency(stats['monthly_cost'])])
        
        # Employee Performance
        section_header("Employee Performance")
        writer.writerow([bold("Top Employees by Campaigns")])
        writer.writerow([bold("Employee"), bold("Email"), bold("Campaigns"), bold("Status")])
        
        for emp_data in stats['top_employees'][:5]:
            if isinstance(emp_data, tuple) and len(emp_data) == 2:
                emp, count = emp_data
                writer.writerow([
                    f"{getattr(emp, 'first_name', '')} {getattr(emp, 'last_name', '')}",
                    getattr(emp, 'email', ''),
                    count,
                    "Active" if getattr(emp, 'is_active', False) else "Inactive"
                ])
        
        writer.writerow([])
        writer.writerow([bold("Top Employees by CPR Under 300")])
        writer.writerow([bold("Employee"), bold("Good CPR %"), bold("Good/Total Campaigns"), bold("Status")])
        
        for emp_data in stats['top_employees_by_good_cpr'][:5]:
            writer.writerow([
                f"{emp_data['employee'].first_name} {emp_data['employee'].last_name}",
                f"{emp_data.get('good_cpr_percentage', 0):.1f}%",
                f"{emp_data.get('good_cpr_count', 0)}/{emp_data.get('total_campaign_count', 0)}",
                "Active" if emp_data['employee'].is_active else "Inactive"
            ])
        
        # Campaign Statistics
        section_header("Campaign Statistics")
        writer.writerow([bold("Total Campaigns:"), stats['total_campaigns']])
        writer.writerow([bold("With Purchases:"), stats['campaigns_with_purchases']])
        writer.writerow([bold("Zero Purchases:"), stats['total_zero_campaigns']])
        writer.writerow([])
        
        writer.writerow([bold("CPR Distribution")])
        writer.writerow([bold("Range"), bold("Campaigns"), bold("Percentage")])
        
        total_campaigns = stats['total_campaigns'] or 1  # Avoid division by zero
        writer.writerow(["Zero Purchases", stats['total_zero_campaigns'], 
                        percentage(stats['total_zero_campaigns'] / total_campaigns * 100)])
        writer.writerow(["Rs 1-200", stats['cpr_ranges']['range_1_200'], 
                        percentage(stats['cpr_ranges']['range_1_200'] / total_campaigns * 100)])
        writer.writerow(["Rs 201-400", stats['cpr_ranges']['range_201_400'], 
                        percentage(stats['cpr_ranges']['range_201_400'] / total_campaigns * 100)])
        writer.writerow(["Rs 401-600", stats['cpr_ranges']['range_401_600'], 
                        percentage(stats['cpr_ranges']['range_401_600'] / total_campaigns * 100)])
        writer.writerow(["Rs 601+", stats['cpr_ranges']['range_601_plus'], 
                        percentage(stats['cpr_ranges']['range_601_plus'] / total_campaigns * 100)])
        
        # Top Campaigns
        section_header("Top Campaigns by Lowest CPR")
        writer.writerow([bold("Campaign"), bold("CPR (Rs)"), bold("Purchases"), bold("Total Cost")])
        
        for campaign in stats['top_campaigns_by_lowest_cpr'][:20]:
            purchases = campaign.get('purchases', 0)
            cpr = campaign.get('cost_per_purchase', 0)
            writer.writerow([
                campaign.get('name', 'N/A'),
                f"{cpr:.2f}",
                purchases,
                currency(purchases * cpr)
            ])
        
        # Recent Reports
        section_header("Recent Reports")
        writer.writerow([bold("Title"), bold("Employee"), bold("Submitted At"), bold("Status")])
        
        for report in stats['recent_reports'][:5]:
            writer.writerow([
                report.title,
                f"{report.user.first_name} {report.user.last_name}",
                report.submitted_at.strftime('%d %b %Y, %I:%M %p'),
                "Approved" if report.approved else "Pending"
            ])
        
        output.seek(0)
        
        # Create filename with current date
        filename = f"dashboard_report_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-disposition": f"attachment; filename={filename}",
                "Content-type": "text/csv; charset=utf-8"
            }
        )
    
    except Exception as e:
        current_app.logger.error(f"Error generating dashboard report: {str(e)}", exc_info=True)
        flash("An error occurred while generating the report. Please try again.", "danger")
        return redirect(url_for('admin.dashboard'))
@admin.route('/send-reminder/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def send_reminder(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Get the most recent missing report for this user
        missing_report = MissingReport.query.filter_by(
            user_id=user_id, 
            resolved=False
        ).order_by(MissingReport.deadline_date.desc()).first()
        
        if not missing_report:
            return jsonify({'success': False, 'message': 'No unresolved missing report found for this user'})
        
        # Format the deadline for the email
        deadline_str = missing_report.formatted_deadline if hasattr(missing_report, 'formatted_deadline') else (
            missing_report.deadline_date.strftime('%Y-%m-%d %I:%M %p') if missing_report.deadline_date 
            else "the deadline"
        )
        
        # Create notification
        notification_message = f"Reminder: Your report for week {missing_report.report_week} is overdue"
        create_notification(user_id, notification_message, 'warning')
        
        # Send email
        email_subject = f"Reminder: Missing Report for Week {missing_report.report_week}"
        email_body = f"""
        <p>Dear {user.first_name},</p>
        <p>This is a reminder that your report for week {missing_report.report_week} is overdue. 
        The deadline was {deadline_str}.</p>
        <p>Please submit your report as soon as possible.</p>
        <p>Thank you,</p>
        <p>The Management Team</p>
        """
        
        send_email_notification(email_subject, user.email, email_body)
        
        # Log the reminder
        notification_log = NotificationLog(
            admin_id=current_user.id,
            employee_id=user_id,
            notification_type='reminder',
            details=f"Sent reminder for missing report {missing_report.id}",
            created_at=get_current_karachi_time()
        )
        db.session.add(notification_log)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        current_app.logger.error(f"Error sending reminder: {str(e)}")
        return jsonify({'success': False, 'message': str(e)}), 500

@admin.route('/send-reminders', methods=['POST'])
@login_required
@admin_required
def send_reminders_to_all():
    try:
        count = 0
        missing_reports = MissingReport.query.filter_by(resolved=False).all()
        
        # Log the bulk reminder action
        notification_log = NotificationLog(
            admin_id=current_user.id,
            notification_type='bulk_reminder',
            details=f"Sent bulk reminders to {len(missing_reports)} employees",
            created_at=get_current_karachi_time()
        )
        db.session.add(notification_log)
        
        for report in missing_reports:
            try:
                user = User.query.get(report.user_id)
                if not user:
                    continue
                
                # Create notification
                notification_message = f"Reminder: Your report for week {report.report_week} is overdue"
                create_notification(user.id, notification_message, 'warning')
                
                # Send email
                email_subject = f"Reminder: Missing Report for Week {report.report_week}"
                email_body = f"""
                <p>Dear {user.first_name},</p>
                <p>This is a reminder that your report for week {report.report_week} is overdue. 
                The deadline was {report.formatted_deadline}.</p>
                <p>Please submit your report as soon as possible.</p>
                <p>Thank you,</p>
                <p>The Management Team</p>
                """
                
                send_email_notification(email_subject, user.email, email_body)
                count += 1
                
                # Log individual reminder
                individual_log = NotificationLog(
                    admin_id=current_user.id,
                    employee_id=user.id,
                    notification_type='reminder',
                    details=f"Sent reminder for missing report {report.id}",
                    created_at=get_current_karachi_time()
                )
                db.session.add(individual_log)
                
            except Exception as e:
                current_app.logger.error(f"Error sending reminder to user {report.user_id}: {str(e)}")
                continue
        
        db.session.commit()
        return jsonify({'success': True, 'count': count})
    except Exception as e:
        current_app.logger.error(f"Error sending reminders: {str(e)}")
        return jsonify({'success': False, 'message': str(e), 'count': count}), 500   