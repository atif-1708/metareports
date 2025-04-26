from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from werkzeug.urls import url_parse as werkzeug_url_parse
from flask_wtf import FlaskForm
from wtforms.validators import DataRequired, Email, ValidationError
from app.models import User

auth = Blueprint('auth', __name__)

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Sign In')

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('employee.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Invalid username or password', 'danger')
            return redirect(url_for('auth.login'))
        
        if not user.is_active:
            flash('Your account has been deactivated. Please contact an administrator.', 'danger')
            return redirect(url_for('auth.login'))
        
        login_user(user, remember=form.remember_me.data)
        
        next_page = request.args.get('next')
        if not next_page or werkzeug_url_parse(next_page).netloc != '':
            if user.role == 'admin':
                next_page = url_for('admin.dashboard')
            else:
                next_page = url_for('employee.dashboard')
        
        return redirect(next_page)
    
    return render_template('login.html', title='Sign In', form=form)

@auth.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('auth.login'))

@auth.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    class ProfileForm(FlaskForm):
        email = StringField('Email', validators=[DataRequired(), Email()])
        submit = SubmitField('Update Profile')
        
        def validate_email(self, email):
            if email.data != current_user.email:
                user = User.query.filter_by(email=email.data).first()
                if user is not None:
                    raise ValidationError('Email already in use.')
    
    form = ProfileForm()
    if form.validate_on_submit():
        current_user.email = form.email.data
        from app.models import db
        db.session.commit()
        flash('Your profile has been updated.', 'success')
        return redirect(url_for('auth.profile'))
    elif request.method == 'GET':
        form.email.data = current_user.email
    
    return render_template('profile.html', title='Profile', form=form)

@auth.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    class PasswordForm(FlaskForm):
        current_password = PasswordField('Current Password', validators=[DataRequired()])
        new_password = PasswordField('New Password', validators=[DataRequired()])
        confirm_password = PasswordField('Confirm New Password', validators=[DataRequired()])
        submit = SubmitField('Change Password')
        
        def validate_confirm_password(self, confirm_password):
            if confirm_password.data != self.new_password.data:
                raise ValidationError('Passwords must match.')
    
    form = PasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'danger')
            return redirect(url_for('auth.change_password'))
        
        current_user.set_password(form.new_password.data)
        from app.models import db
        db.session.commit()
        flash('Your password has been updated.', 'success')
        return redirect(url_for('auth.profile'))
    
    return render_template('change_password.html', title='Change Password', form=form)
