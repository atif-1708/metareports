import os
import csv
import uuid
import pandas as pd
from datetime import datetime, time, timedelta
from sqlalchemy import and_
from werkzeug.utils import secure_filename
from flask import app, current_app, url_for
from flask_mail import Message
from app.models import MissingReport, db, User, Report, Campaign, Notification, ReportDeadline
from app import mail

def allowed_file(filename):
    """Check if the file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def generate_unique_filename(filename):
    """Generate a unique filename to prevent overwriting"""
    _, ext = os.path.splitext(filename)
    return f"{uuid.uuid4().hex}{ext}"

def process_report_csv(file_path, report_id):
    """Process the uploaded CSV file and store campaign data in the database"""
    try:
        # Read the CSV file with pandas
        df = pd.read_csv(file_path)
        
        # Validate the required columns exist
        required_columns = ['Campaign Name', 'Purchases', 'Cost Per Purchase']
        for col in required_columns:
            if col not in df.columns:
                return False, f"Missing required column: {col}"
        
        # Process each row and add to database
        for _, row in df.iterrows():
            campaign = Campaign(
                report_id=report_id,
                campaign_name=row['Campaign Name'],
                purchases=int(row['Purchases']),
                cost_per_purchase=float(row['Cost Per Purchase'])
            )
            db.session.add(campaign)
        
        db.session.commit()
        return True, "CSV processed successfully"
    
    except Exception as e:
        db.session.rollback()
        return False, f"Error processing CSV: {str(e)}"

def get_report_stats(report_id):
    """Get statistics for a specific report"""
    try:
        report = Report.query.get(report_id)
        if not report:
            return {'error': 'Report not found'}
            
        campaigns = Campaign.query.filter_by(report_id=report_id).all()
        
        # Separate zero purchase campaigns
        zero_purchase_campaigns = [c for c in campaigns if c.purchases == 0 or c.purchases is None]
        non_zero_purchase_campaigns = [c for c in campaigns if c.purchases > 0]
        
        # Calculate basic stats with all campaigns (including zero purchase campaigns)
        total_purchases = sum(c.purchases for c in campaigns if c.purchases is not None)
        
        # Calculate total cost including zero purchase campaigns
        total_cost = 0
        for c in campaigns:
            if c.cost_per_purchase is not None:
                if c.purchases > 0:
                    total_cost += c.purchases * c.cost_per_purchase
                else:
                    # Include cost for zero purchase campaigns (as if they had 1 purchase)
                    total_cost += c.cost_per_purchase
        
        avg_cost_per_purchase = total_cost / total_purchases if total_purchases > 0 else 0
        
        # Find top campaigns by purchases and cost
        top_campaigns_by_purchases = sorted(non_zero_purchase_campaigns, key=lambda c: c.purchases or 0, reverse=True)[:5]
        
        # Calculate total cost for each campaign for sorting
        for campaign in campaigns:
            if not hasattr(campaign, 'total_cost'):
                if campaign.purchases > 0 and campaign.cost_per_purchase is not None:
                    campaign.total_cost = campaign.purchases * campaign.cost_per_purchase
                elif campaign.cost_per_purchase is not None:
                    # For zero purchase campaigns, use cost_per_purchase as total cost
                    campaign.total_cost = campaign.cost_per_purchase
                else:
                    campaign.total_cost = 0
        
        # Sort by total cost (now including zero purchase campaigns)
        top_campaigns_by_cost = sorted(campaigns, key=lambda c: getattr(c, 'total_cost', 0) or 0, reverse=True)[:5]
        
        # Filter out campaigns with zero cost_per_purchase, then sort from low to high (for charts - top 10)
        non_zero_cost_campaigns = [c for c in non_zero_purchase_campaigns if c.cost_per_purchase and c.cost_per_purchase > 0]
        top_campaigns_by_cost_per_purchase = sorted(non_zero_cost_campaigns, key=lambda c: c.cost_per_purchase)[:10]
        
        # All campaigns with purchases sorted by CPR (for the table - all of them)
        all_campaigns_by_cpr = sorted(non_zero_cost_campaigns, key=lambda c: c.cost_per_purchase)
        
        # Count campaigns by CPR ranges
        cpr_ranges = {
            'range_zero': len(zero_purchase_campaigns),
            'range_1_200': 0,
            'range_201_400': 0,
            'range_401_600': 0,
            'range_601_plus': 0
        }
        
        for campaign in non_zero_purchase_campaigns:
            cpr = getattr(campaign, 'cost_per_purchase', 0)
            if not cpr or cpr <= 0:
                continue  # Skip zero or negative CPR
            elif cpr <= 200:
                cpr_ranges['range_1_200'] += 1
            elif cpr <= 400:
                cpr_ranges['range_201_400'] += 1
            elif cpr <= 600:
                cpr_ranges['range_401_600'] += 1
            else:
                cpr_ranges['range_601_plus'] += 1
        
        # Calculate percentages
        total_campaigns = len(campaigns)
        total_non_zero_campaigns = len(non_zero_purchase_campaigns)
        cpr_percentages = {}
        
        # Calculate percentage for zero purchase campaigns
        cpr_percentages['range_zero'] = round((cpr_ranges['range_zero'] / total_campaigns * 100), 1) if total_campaigns > 0 else 0
        
        # Calculate percentages for other ranges
        if total_non_zero_campaigns > 0:
            for key in ['range_1_200', 'range_201_400', 'range_401_600', 'range_601_plus']:
                cpr_percentages[key] = round((cpr_ranges[key] / total_non_zero_campaigns * 100), 1)
        else:
            for key in ['range_1_200', 'range_201_400', 'range_401_600', 'range_601_plus']:
                cpr_percentages[key] = 0
        
        return {
            'report': report,
            'total_campaigns': total_campaigns,
            'total_non_zero_campaigns': total_non_zero_campaigns,
            'total_zero_campaigns': len(zero_purchase_campaigns),
            'zero_purchase_campaigns': zero_purchase_campaigns,
            'all_campaigns_by_cpr': all_campaigns_by_cpr,
            'total_purchases': total_purchases,
            'total_cost': total_cost,  # Now includes zero purchase campaigns
            'avg_cost_per_purchase': avg_cost_per_purchase,
            'top_campaigns_by_purchases': top_campaigns_by_purchases,
            'top_campaigns_by_cost': top_campaigns_by_cost,  # Now includes zero purchase campaigns
            'top_campaigns_by_cost_per_purchase': top_campaigns_by_cost_per_purchase,
            'cpr_ranges': cpr_ranges,
            'cpr_percentages': cpr_percentages,
            'total_non_zero_cpr_campaigns': total_non_zero_campaigns
        }
    except Exception as e:
        # Log the error
        current_app.logger.error(f"Error in get_report_stats: {str(e)}")
        # Return a basic error dictionary with additional field
        return {
            'error': f"Error processing report stats: {str(e)}",
            'report': None,
            'total_campaigns': 0,
            'total_non_zero_campaigns': 0,
            'total_zero_campaigns': 0,
            'zero_purchase_campaigns': [],
            'all_campaigns_by_cpr': [],
            'total_purchases': 0,
            'total_cost': 0,
            'avg_cost_per_purchase': 0,
            'top_campaigns_by_purchases': [],
            'top_campaigns_by_cost': [],
            'top_campaigns_by_cost_per_purchase': [],
            'cpr_ranges': {
                'range_zero': 0,
                'range_1_200': 0, 
                'range_201_400': 0, 
                'range_401_600': 0, 
                'range_601_plus': 0
            },
            'cpr_percentages': {
                'range_zero': 0,
                'range_1_200': 0, 
                'range_201_400': 0, 
                'range_401_600': 0, 
                'range_601_plus': 0
            },
            'total_non_zero_cpr_campaigns': 0
        }
def get_employee_stats(user_id):
    """Get statistics for a specific employee"""
    reports = Report.query.filter_by(user_id=user_id).all()
    
    if not reports:
        return {
            'total_reports': 0,
            'approved_reports': 0,
            'total_campaigns': 0,
            'total_purchases': 0,
            'total_cost': 0,
            'avg_cost_per_purchase': 0,
            'recent_reports': [],
            'top_campaigns': []
        }
    
    # Calculate basic stats
    total_reports = len(reports)
    approved_reports = sum(1 for r in reports if r.approved)
    
    # Get all campaigns for the employee
    all_campaigns = []
    for report in reports:
        campaigns = Campaign.query.filter_by(report_id=report.id).all()
        all_campaigns.extend(campaigns)
    
    total_campaigns = len(all_campaigns)
    
    # Calculate purchases (only count actual purchases)
    total_purchases = sum(c.purchases for c in all_campaigns if c.purchases is not None and c.purchases > 0)
    
    # Calculate total cost including zero purchase campaigns
    # Using the same approach as the admin dashboard
    total_cost = 0
    for c in all_campaigns:
        if c.cost_per_purchase is not None:
            # Include cost even if purchases = 0
            total_cost += c.cost_per_purchase * max(c.purchases or 0, 1)  # Use at least 1 purchase for calculation
    
    # Calculate average cost per purchase for non-zero campaigns
    non_zero_cost = 0
    for c in all_campaigns:
        if c.purchases is not None and c.purchases > 0 and c.cost_per_purchase is not None:
            non_zero_cost += c.purchases * c.cost_per_purchase
    
    avg_cost_per_purchase = non_zero_cost / total_purchases if total_purchases > 0 else 0
    
    # Recent reports (last 5)
    recent_reports = sorted(reports, key=lambda r: r.submitted_at, reverse=True)[:5]
    
    # Top campaigns overall
    top_campaigns = sorted(all_campaigns, key=lambda c: c.purchases or 0, reverse=True)[:10]
    
    return {
        'total_reports': total_reports,
        'approved_reports': approved_reports,
        'total_campaigns': total_campaigns,
        'total_purchases': total_purchases,
        'total_cost': total_cost,
        'avg_cost_per_purchase': avg_cost_per_purchase,
        'recent_reports': recent_reports,
        'top_campaigns': top_campaigns
    }
def get_dashboard_stats(user_id=None, role='employee', start_date=None, end_date=None):
    """Get dashboard statistics based on role with optional date filtering"""
    try:
        today = datetime.utcnow().date()
        start_of_month = datetime(today.year, today.month, 1).date()
        end_of_month = (datetime(today.year, today.month + 1, 1) - timedelta(days=1)).date() if today.month < 12 else datetime(today.year, 12, 31).date()
        
        # Initialize default stats dictionary
        stats = {
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
            'top_employees_by_campaigns': [],
            'top_employees_by_good_cpr': [],  # Using good_cpr to match template
            'recent_reports': [],
            'top_campaigns': [],
            'top_campaigns_by_lowest_cpr': [], # New field for lowest CPR campaigns
            'start_date': start_date if start_date else None,
            'end_date': end_date,
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

        if role == 'admin':
            # Get all employees once
            employees = User.query.filter_by(role='employee').all()
            stats['total_employees'] = len(employees)
            stats['active_employees'] = sum(1 for e in employees if e.is_active)

            # Base reports query with date filtering
            reports_query = Report.query
            if start_date:
                reports_query = reports_query.filter(Report.submitted_at >= datetime.combine(start_date, datetime.min.time()))
            if end_date:
                reports_query = reports_query.filter(Report.submitted_at <= datetime.combine(end_date, datetime.max.time()))
            
            all_reports = reports_query.all()
            stats['total_reports'] = len(all_reports)

            # Calculate approval rate
            approved_reports = sum(1 for r in all_reports if r.approved)
            stats['approval_rate'] = (approved_reports / stats['total_reports']) * 100 if stats['total_reports'] > 0 else 0

            # Get reports for period (current month if no dates specified)
            if start_date or end_date:
                reports_in_period = all_reports
            else:
                reports_in_period = Report.query.filter(
                    Report.submitted_at >= datetime.combine(start_of_month, datetime.min.time()),
                    Report.submitted_at <= datetime.combine(end_of_month, datetime.max.time())
                ).all()
            stats['reports_this_month'] = len(reports_in_period)

            # Get all campaigns with their reports in one query
            all_campaigns = Campaign.query.join(Report).filter(
                Report.id.in_([r.id for r in all_reports])
            ).all()
            
            # Calculate purchase and cost metrics - including zero purchase campaigns
            stats['total_purchases'] = sum(c.purchases for c in all_campaigns)
            
            # Calculate total cost including zero purchase campaigns
            total_cost = 0
            for c in all_campaigns:
                # Include cost even if purchases = 0
                total_cost += c.cost_per_purchase * max(c.purchases, 1)  # Use at least 1 purchase for calculation
            stats['total_cost'] = total_cost
            
            # Calculate monthly costs
            monthly_cost = 0
            for c in all_campaigns:
                if c.report in reports_in_period:
                    # Include cost even if purchases = 0 
                    monthly_cost += c.cost_per_purchase * max(c.purchases, 1)  # Use at least 1 purchase for calculation
            
            stats['monthly_purchases'] = sum(c.purchases for c in all_campaigns if c.report in reports_in_period)
            stats['monthly_cost'] = monthly_cost

            # Get top employees by report count
            employee_report_counts = []
            for emp in employees:
                report_count = Report.query.filter_by(user_id=emp.id).count()
                employee_report_counts.append((emp, report_count))
            
            # Get top employees by campaign count
            employee_campaign_counts = []
            for emp in employees:
                reports_query = Report.query.filter_by(user_id=emp.id)
                if start_date:
                   reports_query = reports_query.filter(Report.submitted_at >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                   reports_query = reports_query.filter(Report.submitted_at <= datetime.combine(end_date, datetime.max.time()))
                # Count campaigns from filtered reports
                campaign_count = Campaign.query.join(Report).filter(
                   Report.user_id == emp.id,
                   Report.id.in_([r.id for r in reports_query.all()])
                ).count()
                employee_campaign_counts.append((emp, campaign_count))
            stats['top_employees'] = sorted(employee_campaign_counts, key=lambda x: x[1], reverse=True)[:5]
            
            # Good CPR calculation
            employee_good_cpr_data = []
            min_campaign_threshold = 1  # Lower threshold for testing - can increase in production
            
            for emp in employees:
                # Get all reports for this employee within date range
                emp_reports_query = Report.query.filter_by(user_id=emp.id)
                if start_date:
                    emp_reports_query = emp_reports_query.filter(Report.submitted_at >= datetime.combine(start_date, datetime.min.time()))
                if end_date:
                    emp_reports_query = emp_reports_query.filter(Report.submitted_at <= datetime.combine(end_date, datetime.max.time()))
                
                # Get all campaigns for these reports
                report_ids = [r.id for r in emp_reports_query.all()]
                if not report_ids:  # Skip if no reports
                    continue
                    
                emp_campaigns = Campaign.query.filter(Campaign.report_id.in_(report_ids)).all()
                
                total_campaigns = len(emp_campaigns)
                if total_campaigns < min_campaign_threshold:
                    continue  # Skip employees with too few campaigns
                
                # Calculate good CPR metrics
                campaigns_with_purchases = [c for c in emp_campaigns if c.purchases > 0]
                good_cpr_campaigns = [c for c in campaigns_with_purchases if c.cost_per_purchase <= 300]
                
                # Calculate percentage based on TOTAL campaigns, not just ones with purchases
                if total_campaigns > 0:
                    good_cpr_percentage = (len(good_cpr_campaigns) / total_campaigns) * 100
                else:
                    good_cpr_percentage = 0
                
                # Add data for this employee
                employee_good_cpr_data.append({
                    'employee': emp,
                    'good_cpr_percentage': good_cpr_percentage,
                    'good_cpr_count': len(good_cpr_campaigns),
                    'total_campaign_count': total_campaigns,  # All campaigns including zero purchases
                    'campaigns_with_purchases': len(campaigns_with_purchases)  # Only campaigns with purchases
                })
            
            # Sort by percentage of good CPR campaigns (descending)
            stats['top_employees_by_good_cpr'] = sorted(
                employee_good_cpr_data,
                key=lambda x: x['good_cpr_percentage'],
                reverse=True
            )[:5]

            # Get recent reports and top campaigns
            stats['recent_reports'] = sorted(all_reports, key=lambda r: r.submitted_at, reverse=True)[:5]
            stats['top_campaigns'] = sorted(all_campaigns, key=lambda c: c.purchases, reverse=True)[:10]
            
            # Add campaign statistics
            stats['total_campaigns'] = len(all_campaigns)
            stats['total_zero_campaigns'] = sum(1 for c in all_campaigns if c.purchases == 0)
            campaigns_with_purchases = [c for c in all_campaigns if c.purchases > 0]
            stats['campaigns_with_purchases'] = len(campaigns_with_purchases)
            
            # CPR ranges (only considering campaigns with purchases > 0)
            stats['cpr_ranges'] = {
                'range_1_200': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase >= 1 and c.cost_per_purchase <= 200),
                'range_201_400': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase > 200 and c.cost_per_purchase <= 400),
                'range_401_600': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase > 400 and c.cost_per_purchase <= 600),
                'range_601_plus': sum(1 for c in campaigns_with_purchases if c.cost_per_purchase > 600)
            }
            
            # NEW: Top Campaigns by Lowest CPR logic 
            # Filter for campaigns with valid purchase and CPR data
            campaigns_with_valid_data = []
            
            # Use a dictionary to track unique campaigns by ID
            unique_campaigns = {}
            
            for campaign in all_campaigns:
                # Check if campaign has valid purchase and CPR data
                if campaign.purchases is not None and campaign.purchases > 0 and campaign.cost_per_purchase is not None:
                    # Only process this campaign if we haven't seen its ID before
                    if campaign.id not in unique_campaigns:
                        # Try to get the campaign name from various possible attributes
                        campaign_name = None
                        for attr in ['name', 'title', 'campaign_name', 'campaign_title']:
                            if hasattr(campaign, attr) and getattr(campaign, attr):
                                campaign_name = getattr(campaign, attr)
                                break
                        
                        if not campaign_name:
                            # If no name attribute found, use ID as fallback
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
            campaign_count = min(len(campaigns_with_valid_data), 20)
            stats['top_campaigns_by_lowest_cpr'] = sorted(
                campaigns_with_valid_data, 
                key=lambda c: c['cost_per_purchase'],
                reverse=False
            )[:campaign_count]
            
            return stats

    except Exception as e:
        current_app.logger.error(f"Error in get_dashboard_stats: {str(e)}", exc_info=True)
        # Return the default stats structure with error info
        stats['error'] = str(e)
        return stats

    # Handle employee role case
    return get_employee_stats(user_id)

def create_notification(user_id, message, category='info'):
    """Create a new notification for a user"""
    notification = Notification(
        user_id=user_id,
        message=message,
        category=category,
        is_read=False
    )
    db.session.add(notification)
    db.session.commit()
    return notification

def send_email_notification(subject, recipient, body):
    """Send an email notification
    
    Args:
        subject (str): Email subject
        recipient (str): Single email address or list of email addresses
        body (str): HTML content of the email
    """
    try:
        current_app.logger.info(f"Attempting to send email to {recipient}")
        
        # Handle both single recipient or list of recipients
        recipients_list = recipient if isinstance(recipient, list) else [recipient]
        
        msg = Message(
            subject=subject,
            sender=current_app.config['MAIL_DEFAULT_SENDER'],
            recipients=recipients_list,
            html=body
        )
        
        current_app.logger.info("Email message created, attempting to send...")
        mail.send(msg)
        current_app.logger.info("Email sent successfully")
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send email: {str(e)}")
        return False
# In utils.py (add these functions)
from datetime import datetime
import pytz

def utc_to_local(utc_dt):
    """Convert UTC datetime to local timezone"""
    from flask import current_app
    
    # Return None if datetime is None
    if utc_dt is None:
        return None
    
    local_tz = pytz.timezone(current_app.config.get('TIMEZONE', 'Asia/Karachi'))
    
    # Make sure the datetime is timezone-aware and in UTC
    if utc_dt.tzinfo is None:
        utc_dt = pytz.utc.localize(utc_dt)
    
    # Convert to local time
    return utc_dt.astimezone(local_tz)

def local_to_utc(local_dt):
    """Convert local datetime to UTC"""
    from flask import current_app
    
    # Return None if datetime is None
    if local_dt is None:
        return None
    
    local_tz = pytz.timezone(current_app.config.get('TIMEZONE', 'Asia/Karachi'))
    
    # If the datetime is naive (no timezone), assume it's in local time
    if local_dt.tzinfo is None:
        local_dt = local_tz.localize(local_dt)
    
    # Convert to UTC
    return local_dt.astimezone(pytz.utc)
# In utils.py
from datetime import datetime, timedelta
import pytz

def get_pakistan_time():
    """
    Returns current time in Pakistan timezone.
    Use this instead of datetime.utcnow() throughout the application.
    """
    # Get UTC time
    utc_now = datetime.utcnow()
    
    # Add Pakistan offset (+5 hours)
    pakistan_time = utc_now + timedelta(hours=5)
    
    return pakistan_time
def get_local_now():
    """Get current time in local timezone"""
    now_utc = datetime.utcnow()
    return utc_to_local(now_utc)
# Add this function to utils.py
def check_for_missed_deadline():
    """
    Check for missed reports at deadline time and notify admin
    Should be called by a scheduler at the report deadline time
    """
    from app.models import User, Report, MissingReport, ReportDeadline
    from app import db
    
    # Get active deadline
    deadline = ReportDeadline.query.filter_by(is_active=True).first()
    if not deadline:
        return
    
    # Get Karachi time
    karachi_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(karachi_tz)
    
    # Calculate the week's start (Monday)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=6)
    
    # Find active employees who haven't submitted reports for this week
    employees = User.query.filter_by(role='employee', is_active=True).all()
    for employee in employees:
        # Check if employee has submitted a report for this week
        if not Report.query.filter_by(user_id=employee.id, 
                                    week_start=week_start.date()).first():
            # Create missing report record
            missing = MissingReport(
                user_id=employee.id,
                report_week=f"{week_start.date()} to {week_end.date()}",
                deadline_date=now,
                created_at=now
            )
            db.session.add(missing)
            
            # Notify administrators
            admins = User.query.filter_by(role='admin', is_active=True).all()
            for admin in admins:
                # Create notification
                create_notification(
                user_id=admin.id,
                message=f"Employee {employee.first_name} {employee.last_name} has missed their report deadline"
               )

                
                # Send email notification
                send_email_notification(
                    to_email=admin.email,
                    subject="Missed Report Alert",
                    body=f"Employee {employee.name} has missed their report deadline for the week of {week_start.date()} to {week_end.date()}."
                )
                
    db.session.commit()
def resolve_missing_report(user_id, week_start, week_end):
    """Mark a missing report as resolved"""
    from app.models import MissingReport, db
    import logging
    
    # Ensure date formatting is consistent
    if isinstance(week_start, datetime):
        week_start = week_start.date()
    if isinstance(week_end, datetime):
        week_end = week_end.date()
        
    # Format week string
    week_str = f"{week_start} to {week_end}"
    
    logging.info(f"Attempting to resolve missing report for user {user_id}, week {week_str}")
    
    # Find any matching unresolved missing report
    missing = MissingReport.query.filter_by(
        user_id=user_id,
        report_week=week_str,
        resolved=False
    ).first()
    
    if missing:
        logging.info(f"Found missing report {missing.id}, marking as resolved")
        missing.resolved = True
        db.session.commit()
        return True
    
    # Try alternative format if first attempt failed
    alt_week_str = f"{week_start.strftime('%Y-%m-%d')} to {week_end.strftime('%Y-%m-%d')}"
    missing = MissingReport.query.filter_by(
        user_id=user_id,
        report_week=alt_week_str,
        resolved=False
    ).first()
    
    if missing:
        logging.info(f"Found missing report {missing.id} with alternative format, marking as resolved")
        missing.resolved = True
        db.session.commit()
        return True
    
    # Last resort: look for any unresolved reports for this user
    all_missing = MissingReport.query.filter_by(
        user_id=user_id,
        resolved=False
    ).all()
    
    for m in all_missing:
        logging.info(f"Checking missing report {m.id} with week {m.report_week}")
        # Resolve it if found
        m.resolved = True
        db.session.commit()
        logging.info(f"Resolved missing report {m.id} using last resort method")
        return True
        
    logging.info(f"No unresolved missing reports found for user {user_id}")
    return False
def check_missing_reports():
    """
    Check for missing reports on Saturday at midnight.
    Creates records for employees who haven't submitted reports for the previous week.
    """
    from app.models import User, Report, MissingReport
    from app import db
    import pytz
    from datetime import datetime, timedelta
    
    karachi_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(karachi_tz)
    
    # Check if it's time to run (Saturday 00:00 PKT)
    if now.weekday() != 5 or now.hour != 0:
        return
    
    # Calculate last week's Monday
    last_monday = now - timedelta(days=now.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    
    for employee in User.query.filter_by(role='employee', is_active=True).all():
        if not Report.query.filter_by(user_id=employee.id, 
                                   week_start=last_monday.date()).first():
            # Create missing report record
            missing = MissingReport(
                user_id=employee.id,
                report_week=f"{last_monday.date()} to {last_sunday.date()}",
                deadline_date=now,  # Using current time as deadline for records from weekly check
                created_at=now,
                resolved=False
            )
            db.session.add(missing)
    
    db.session.commit()

def check_deadline_and_notify():
    """
    Check if the current time is a deadline time, and if so, check for missing reports
    and notify admins immediately. This function is intended to be run hourly.
    """
    from app.models import User, Report, MissingReport, ReportDeadline
    from app import db
    import pytz
    from datetime import datetime, timedelta
    import logging
    
    logging.info("Running check_deadline_and_notify")
    
    # Get active deadline
    deadline = ReportDeadline.query.filter_by(is_active=True).first()
    if not deadline:
        logging.info("No active deadline found")
        return
    
    # Get Karachi time
    karachi_tz = pytz.timezone('Asia/Karachi')
    now = datetime.now(karachi_tz)
    
    # Check if this is the deadline time (same day of week and hour)
    if now.weekday() != deadline.day_of_week:
        logging.info(f"Not deadline day. Current: {now.weekday()}, Deadline: {deadline.day_of_week}")
        return  # Not the right day
    
    deadline_hour = deadline.get_24h_hour()
    if now.hour != deadline_hour:
        logging.info(f"Not deadline hour. Current: {now.hour}, Deadline: {deadline_hour}")
        return  # Not the right hour
    
    # Only proceed if we're within 5 minutes after the deadline
    if now.minute < deadline.minute or now.minute > deadline.minute + 5:
        logging.info(f"Not within deadline window. Current minute: {now.minute}, Deadline minute: {deadline.minute}")
        return
    
    logging.info("Deadline check criteria met, proceeding with employee check")
    
    # Calculate the week's start (Monday) and end (Sunday)
    days_since_monday = now.weekday()
    week_start = (now - timedelta(days=days_since_monday)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    week_end = week_start + timedelta(days=6)
    
    # Debug info
    logging.info(f"Checking week: {week_start.date()} to {week_end.date()}")
    
    # Find employees who haven't submitted reports for this week
    employees = User.query.filter_by(role='employee', is_active=True).all()
    admins = User.query.filter_by(role='admin', is_active=True).all()
    
    missing_employees = []  # Track employees who miss deadlines
    
    for employee in employees:
        try:
            # Check if employee has submitted a report for this week
            report_exists = Report.query.filter(
                Report.user_id == employee.id,
                Report.week_start == week_start.date()
            ).first()
            
            logging.info(f"Checking employee {employee.id}: {employee.first_name} {employee.last_name} - Report exists: {report_exists is not None}")
            
            if not report_exists:
                # Check if a missing report already exists for this employee this week
                report_week_str = f"{week_start.date()} to {week_end.date()}"
                existing_report = MissingReport.query.filter_by(
                    user_id=employee.id,
                    report_week=report_week_str,
                    resolved=False
                ).first()
                
                logging.info(f"Missing report already exists: {existing_report is not None}")
                
                if not existing_report:
                    # Create missing report record
                    deadline_time = now.replace(
                        hour=deadline_hour,
                        minute=deadline.minute,
                        second=0,
                        microsecond=0
                    )
                    
                    missing = MissingReport(
                        user_id=employee.id,
                        report_week=report_week_str,
                        deadline_date=deadline_time,
                        created_at=now,
                        resolved=False
                    )
                    db.session.add(missing)
                    
                    # Add to our tracking list
                    missing_employees.append({
                        'id': employee.id,
                        'name': f"{employee.first_name} {employee.last_name}",
                        'missing_report_id': missing.id if missing else None
                    })
                    
                    # Commit after each employee to ensure the record is saved
                    # even if there's an error with the next employee
                    db.session.commit()
                    
                    logging.info(f"Created missing report for employee {employee.id}")
        except Exception as e:
            logging.error(f"Error processing employee {employee.id}: {str(e)}")
            # Continue with next employee
    
    # Now notify admins about all missing employees
    logging.info(f"Total employees with missing reports: {len(missing_employees)}")
    
    if missing_employees:
        for admin in admins:
            try:
                for employee in missing_employees:
                    # Create notification for each missing employee
                    create_notification(
                        user_id=admin.id,
                        message=f"Employee {employee['name']} has missed their report deadline",
                    )
                
                # Send a single email with all missing employees
                if len(missing_employees) > 0:
                    missing_list = "\n".join([f"- {emp['name']}" for emp in missing_employees])
                    send_email_notification(
                        subject=f"Missed Report Alert: {len(missing_employees)} employees",
                        recipient=admin.email,
                        body=f"""Hello Admin,

The following employees have missed their report deadline for the week of {week_start.date()} to {week_end.date()}:

{missing_list}

Please follow up with these employees.
"""
                    )
                    logging.info(f"Sent email notification to admin {admin.id}")
            except Exception as e:
                logging.error(f"Error notifying admin {admin.id}: {str(e)}")
    
    logging.info("Deadline check completed")
    # Add this function to your utils.py or create a new file for helper functions
def get_formatted_deadline():
    """
    Gets the current deadline and formats it as a readable string.
    Returns a default message if no deadline is set.
    """
    
    current_deadline = ReportDeadline.query.filter_by(is_active=True).first()
    if not current_deadline:
        return "No deadline set"
    
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    day_name = days[current_deadline.day_of_week]
    minute_str = f"{current_deadline.minute:02d}" if current_deadline.minute < 10 else str(current_deadline.minute)
    
    return f"{day_name} at {current_deadline.hour}:{minute_str} {current_deadline.am_pm}"
