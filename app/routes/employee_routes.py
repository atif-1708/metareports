from datetime import datetime, timedelta
import os
import pytz
from flask import Blueprint, after_this_request, make_response, render_template, redirect, send_file, url_for, flash, request, current_app
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import StringField, DateField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.utils import secure_filename
from app.utils import get_pakistan_time
from functools import wraps

from app.models import db, Report, Campaign
from app.utils import allowed_file, generate_unique_filename, process_report_csv, get_dashboard_stats, get_report_stats, create_notification

# Define Karachi timezone
karachi_tz = pytz.timezone('Asia/Karachi')

employee = Blueprint('employee', __name__, url_prefix='/employee')

# Timezone conversion utility functions
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

# Make utility functions available to templates
@employee.app_context_processor
def inject_utilities():
    return dict(convert_to_karachi=convert_to_karachi)

# Employee required decorator
def employee_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'employee':
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Forms
class UploadReportForm(FlaskForm):
    title = StringField('Report Title', validators=[DataRequired()])
    week_start = DateField('Week Start Date', validators=[DataRequired()], format='%Y-%m-%d')
    week_end = DateField('Week End Date', validators=[DataRequired()], format='%Y-%m-%d')
    report_file = FileField('CSV Report File', validators=[
        FileRequired(),
        FileAllowed(['csv'], 'CSV files only!')
    ])
    submit = SubmitField('Upload Report')

# Routes
@employee.route('/dashboard')
@login_required
def dashboard():
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
    reports_query = Report.query.filter_by(user_id=current_user.id)
    if start_date:
        reports_query = reports_query.filter(Report.submitted_at >= start_date)
    if end_date:
        reports_query = reports_query.filter(Report.submitted_at < end_date)
    
    # Get reports for the current user with date filters
    reports = reports_query.order_by(Report.submitted_at.desc()).all()
    
    # Convert report timestamps from UTC to Karachi time for display
    for report in reports:
        if report.submitted_at:
            report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    # Get campaigns for these reports
    campaign_ids = set()  # Use a set to avoid duplicate IDs
    for report in reports:
        for campaign in report.campaigns:
            campaign_ids.add(campaign.id)
    
    campaign_ids = list(campaign_ids)  # Convert back to list for the query
    campaigns = Campaign.query.filter(Campaign.id.in_(campaign_ids)).all() if campaign_ids else []
    
    # Convert campaigns to JSON-serializable dictionaries
    campaign_dicts = []
    for c in campaigns:
        # Create a dictionary with only primitive types that can be serialized to JSON
        campaign_dict = {
            'id': c.id,
            'label': f"Campaign #{c.id}",
            'purchases': c.purchases if c.purchases is not None else 0,
            'cost_per_purchase': c.cost_per_purchase if c.cost_per_purchase is not None else 0
        }
        campaign_dicts.append(campaign_dict)
    
    # Calculate statistics
    total_cost = 0
    for c in campaigns:
        if c.cost_per_purchase is not None:
            if c.purchases == 0 or c.purchases is None:
                # For zero-purchase campaigns, add cost_per_purchase directly
                total_cost += c.cost_per_purchase
            else:
                # For campaigns with purchases, calculate normally
                total_cost += c.purchases * c.cost_per_purchase
    
    # Calculate statistics with JSON-serializable campaigns
    stats = {
        'total_reports': len(reports),
        'approved_reports': sum(1 for r in reports if r.approved),
        'total_campaigns': len(campaigns),
        'total_purchases': sum(c.purchases or 0 for c in campaigns),
        'total_cost': total_cost,
        'recent_reports': reports[:5],  # Show first 5 reports - these aren't being serialized to JSON
        'top_campaigns': campaign_dicts  # All campaigns, not just top 10 - we'll sort in the template
    }
    
    # Calculate average cost per purchase (avoid division by zero)
    if stats['total_purchases'] > 0:
        stats['avg_cost_per_purchase'] = stats['total_cost'] / stats['total_purchases']
    else:
        stats['avg_cost_per_purchase'] = 0
        
    # Add CPR distribution statistics
    stats['total_zero_campaigns'] = sum(1 for c in campaigns if c.purchases == 0 or c.purchases is None)
    stats['total_non_zero_campaigns'] = stats['total_campaigns'] - stats['total_zero_campaigns']
    
    # Get all campaigns with purchases > 0 for CPR calculations
    campaigns_with_purchases = [c for c in campaigns if c.purchases and c.purchases > 0]
    stats['campaigns_with_purchases'] = len(campaigns_with_purchases)

    # CPR ranges (only considering campaigns with purchases > 0)
    stats['cpr_ranges'] = {
        'range_1_200': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase and c.cost_per_purchase >= 1 and c.cost_per_purchase <= 200),
        'range_201_400': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase and c.cost_per_purchase > 200 and c.cost_per_purchase <= 400),
        'range_401_600': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase and c.cost_per_purchase > 400 and c.cost_per_purchase <= 600),
        'range_601_plus': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase and c.cost_per_purchase > 600)
    }
    
    # Add lowest CPR campaigns data with proper name handling
    # Use a dictionary to track unique campaigns by ID
    unique_campaigns = {}
    
    for campaign in campaigns:
        # Check if campaign has valid purchase and CPR data
        if (campaign.purchases is not None and 
            campaign.purchases > 0 and 
            campaign.cost_per_purchase is not None):
            
            # Only process this campaign if we haven't seen its ID before
            if campaign.id not in unique_campaigns:
                # Try to get the campaign name from the campaign model
                # This is the same logic we used in our first implementations
                campaign_name = None
                
                # Get campaign name or title from the database
                if hasattr(campaign, 'name') and campaign.name:
                    campaign_name = campaign.name
                elif hasattr(campaign, 'title') and campaign.title:
                    campaign_name = campaign.title
                elif hasattr(campaign, 'campaign_name') and campaign.campaign_name:
                    campaign_name = campaign.campaign_name
                
                # If no name is found, create a name from the report
                if not campaign_name and hasattr(campaign, 'report') and campaign.report:
                    report = campaign.report
                    # Convert report date to Karachi time for display
                    if hasattr(report, 'submitted_at') and report.submitted_at:
                        report_date = convert_to_karachi(report.submitted_at).strftime('%Y-%m-%d')
                    else:
                        report_date = 'Unknown'
                    campaign_name = f"Report {report.id} ({report_date})"
                
                # If still no name, use a default with the ID
                if not campaign_name:
                    campaign_name = f'Campaign #{campaign.id}'
                
                # Store this campaign in our unique campaigns dictionary
                unique_campaigns[campaign.id] = {
                    'id': campaign.id,
                    'name': campaign_name,
                    'cost_per_purchase': campaign.cost_per_purchase,
                    'purchases': campaign.purchases
                }
    
    # Convert the dictionary values to a list
    campaigns_with_valid_data = list(unique_campaigns.values())
    
    # Sort by cost_per_purchase (CPR) in ascending order
    # Take all available campaigns (up to 10 max)
    campaign_count = min(len(campaigns_with_valid_data), 10)
    stats['top_campaigns_by_lowest_cpr'] = sorted(
        campaigns_with_valid_data, 
        key=lambda c: c['cost_per_purchase'],
        reverse=False
    )[:campaign_count]
    
    return render_template('employee/dashboard.html', 
                          title='Dashboard', 
                          stats=stats)

@employee.route('/reports')
@login_required
@employee_required
def reports():
    reports = Report.query.filter_by(user_id=current_user.id).order_by(Report.submitted_at.desc()).all()
    
    # Convert report timestamps from UTC to Karachi time for display
    for report in reports:
        if report.submitted_at:
            report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    return render_template('employee/reports.html', title='My Reports', reports=reports)

@employee.route('/reports/upload', methods=['GET', 'POST'])
@login_required
@employee_required
def upload_report():
    form = UploadReportForm()
    
    # Set default dates for the previous week in Karachi time
    if request.method == 'GET':
        # Get current date in Karachi time
        today = get_pakistan_time().date()
        # Calculate previous Monday
        prev_monday = today - timedelta(days=today.weekday() + 7)
        # Calculate previous Sunday
        prev_sunday = prev_monday + timedelta(days=6)
        
        form.week_start.data = prev_monday
        form.week_end.data = prev_sunday
    
    if form.validate_on_submit():
        # Check if a report already exists for this week
        existing_report = Report.query.filter_by(
            user_id=current_user.id,
            week_start=form.week_start.data,
            week_end=form.week_end.data
        ).first()
        
        if existing_report:
            flash(f'A report for the selected week already exists: "{existing_report.title}".', 'warning')
            return redirect(url_for('employee.reports'))
        
        # Save the report file
        file = form.report_file.data
        if file and allowed_file(file.filename):
            original_filename = secure_filename(file.filename)
            unique_filename = generate_unique_filename(original_filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(filepath)
            
            # Get current time in Karachi timezone
            now_karachi = get_pakistan_time()
            # Convert to UTC for database storage
            now_utc = convert_to_utc(now_karachi)
            
            # Create new report
            report = Report(
                title=form.title.data,
                filename=unique_filename,
                original_filename=original_filename,
                week_start=form.week_start.data,
                week_end=form.week_end.data,
                user_id=current_user.id,
                submitted_at=now_utc  # Store UTC time in database
            )
            db.session.add(report)
            db.session.commit()
            
            # Process the CSV file
            success, message = process_report_csv(filepath, report.id)
            
            if success:
                flash(f'Report "{form.title.data}" has been uploaded successfully!', 'success')
                # Add after successful report creation
                from app.utils import resolve_missing_report
                resolve_missing_report(current_user.id, form.week_start.data, form.week_end.data)
                # Notify admin
                from app.models import User
                admins = User.query.filter_by(role='admin').all()
                for admin in admins:
                    create_notification(
                        admin.id,
                        f"New report uploaded: '{report.title}' by {current_user.first_name} {current_user.last_name}",
                        'info'
                    )
                
                return redirect(url_for('employee.report_details', report_id=report.id))
            else:
                # If there was an error processing the CSV, delete the report
                db.session.delete(report)
                db.session.commit()
                
                # Delete the file
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                flash(f'Error processing the CSV file: {message}', 'danger')
                return redirect(url_for('employee.upload_report'))
        else:
            flash('Invalid file format. Please upload a CSV file.', 'danger')
    
    return render_template('employee/upload_report.html', title='Upload Report', form=form)

@employee.route('/reports/<int:report_id>')
@login_required
@employee_required
def report_details(report_id):
    report = Report.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    stats = get_report_stats(report_id)
    campaigns = Campaign.query.filter_by(report_id=report_id).all()
    
    # Convert timestamp to Karachi time
    if report.submitted_at:
        report.local_submitted_at = convert_to_karachi(report.submitted_at)
    
    # Filter and sort campaigns with purchases by CPR
    campaigns_with_purchases = [c for c in campaigns if c.purchases > 0]
    sorted_campaigns = sorted(campaigns_with_purchases, key=lambda c: c.cost_per_purchase)
    
    return render_template(
        'employee/report_details.html',
        title=f'Report Details: {report.title}',
        report=report,
        stats=stats,
        campaigns=campaigns,
        sorted_campaigns_by_cpr=sorted_campaigns  # New sorted list
    )

@employee.route('/reports/<int:report_id>/download')
@login_required
@employee_required
def download_report(report_id):
    report = Report.query.filter_by(id=report_id, user_id=current_user.id).first_or_404()
    stats = get_report_stats(report_id)
    
    if 'error' in stats:
        flash(stats['error'], 'danger')
        return redirect(url_for('employee.reports'))

    import io
    import csv
    output = io.StringIO()
    writer = csv.writer(output)

    # Excel formatting for bold (using Excel syntax)
    def bold(text):
        return f'"{text}"'  # Excel will interpret quoted text as bold in some cases
        # Alternatively, for richer formatting you could generate an XLSX file instead

    # Write Report Summary Section
    writer.writerow([bold('REPORT SUMMARY')])
    writer.writerow([])
    writer.writerow([bold('Title:'), report.title])
    writer.writerow([bold('Period:'), 
                   f"{report.week_start.strftime('%d %b %Y')} - {report.week_end.strftime('%d %b %Y')}"])
    writer.writerow([bold('Submitted:'), 
                   getattr(report, 'local_submitted_at', report.submitted_at).strftime('%d %b %Y %H:%M')])
    writer.writerow([])
    
    # Key Metrics Section
    writer.writerow([bold('KEY METRICS')])
    writer.writerow([])
    writer.writerow([bold('Total Campaigns:'), stats['total_campaigns']])
    writer.writerow([bold('Campaigns With Purchases:'), stats['total_non_zero_campaigns']])
    writer.writerow([bold('Zero Purchase Campaigns:'), stats['total_zero_campaigns']])
    writer.writerow([bold('Total Purchases:'), stats['total_purchases']])
    writer.writerow([bold('Total Cost:'), f"Rs {stats['total_cost']:,.2f}"])
    writer.writerow([bold('Average CPR:'), f"Rs {stats['avg_cost_per_purchase']:.2f}"])
    writer.writerow([])
    
    # CPR Distribution Section
    writer.writerow([bold('CPR DISTRIBUTION')])
    writer.writerow([])
    writer.writerow([bold('Range'), bold('Campaigns'), bold('Percentage')])
    writer.writerow(['Zero Purchases', stats['cpr_ranges']['range_zero'], f"{stats['cpr_percentages']['range_zero']}%"])
    writer.writerow(['Rs 1-200', stats['cpr_ranges']['range_1_200'], f"{stats['cpr_percentages']['range_1_200']}%"])
    writer.writerow(['Rs 201-400', stats['cpr_ranges']['range_201_400'], f"{stats['cpr_percentages']['range_201_400']}%"])
    writer.writerow(['Rs 401-600', stats['cpr_ranges']['range_401_600'], f"{stats['cpr_percentages']['range_401_600']}%"])
    writer.writerow(['Rs 601+', stats['cpr_ranges']['range_601_plus'], f"{stats['cpr_percentages']['range_601_plus']}%"])
    writer.writerow([])
    
    # Top Campaigns Section
    writer.writerow([bold('TOP CAMPAIGNS BY PURCHASES')])
    writer.writerow([])
    writer.writerow([bold('Campaign Name'), bold('Purchases'), bold('CPR'), bold('Total Cost')])
    for campaign in stats['top_campaigns_by_purchases']:
        writer.writerow([
            campaign.campaign_name,
            campaign.purchases,
            f"Rs {campaign.cost_per_purchase:.2f}",
            f"Rs {campaign.purchases * campaign.cost_per_purchase:,.2f}" if campaign.purchases else f"Rs {campaign.cost_per_purchase:,.2f}"
        ])
    writer.writerow([])
    
    writer.writerow([bold('TOP CAMPAIGNS BY COST PER PURCHASE (BEST PERFORMING)')])
    writer.writerow([])
    writer.writerow([bold('Campaign Name'), bold('CPR'), bold('Purchases'), bold('Total Cost')])
    for campaign in stats['top_campaigns_by_cost_per_purchase']:
        writer.writerow([
            campaign.campaign_name,
            f"Rs {campaign.cost_per_purchase:.2f}",
            campaign.purchases,
            f"Rs {campaign.purchases * campaign.cost_per_purchase:,.2f}" if campaign.purchases else f"Rs {campaign.cost_per_purchase:,.2f}"
        ])
    writer.writerow([])
    
    # All Campaigns Section
    writer.writerow([bold('ALL CAMPAIGNS WITH PURCHASES (SORTED BY CPR)')])
    writer.writerow([])
    writer.writerow([bold('Campaign Name'), bold('CPR'), bold('Purchases'), bold('Total Cost')])
    for campaign in stats['all_campaigns_by_cpr']:
        writer.writerow([
            campaign.campaign_name,
            f"Rs {campaign.cost_per_purchase:.2f}",
            campaign.purchases,
            f"Rs {campaign.purchases * campaign.cost_per_purchase:,.2f}" if campaign.purchases else f"Rs {campaign.cost_per_purchase:,.2f}"
        ])
    writer.writerow([])
    
    # Zero Purchase Campaigns Section
    if stats['total_zero_campaigns'] > 0:
        writer.writerow([bold('ZERO PURCHASE CAMPAIGNS')])
        writer.writerow([])
        writer.writerow([bold('Campaign Name'), bold('Potential CPR'), bold('Potential Cost')])
        for campaign in stats['zero_purchase_campaigns']:
            writer.writerow([
                campaign.campaign_name,
                f"Rs {campaign.cost_per_purchase:.2f}" if campaign.cost_per_purchase else 'N/A',
                f"Rs {campaign.cost_per_purchase:,.2f}" if campaign.cost_per_purchase else 'N/A'
            ])
    
    output.seek(0)
    
    # Create response
    from flask import Response
    response = Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-disposition": f"attachment; filename=report_analysis_{report.title}.csv",
            "Content-type": "text/csv; charset=utf-8"
        }
    )
    
    return response