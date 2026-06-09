from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.models.user import User
from app.forms.auth import LoginForm

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(_redirect_by_role(current_user))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(login=form.login.data, active=True).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or _redirect_by_role(user))
        flash('Login ou senha incorretos.', 'danger')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu do sistema.', 'info')
    return redirect(url_for('auth.login'))


def _redirect_by_role(user):
    if user.is_admin:
        return url_for('admin.dashboard')
    return url_for('doctor.dashboard')
