import os
from flask import Flask, render_template
from app.extensions import db, migrate, login_manager, csrf
from config import config


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    from app.models import (  # noqa: F401
        User, Location, DoctorLocationLink,
        DoctorWindowConfirmation, FillingWindow, DoctorRoutine, DoctorRestriction, Schedule,
        ScheduleSwap, SwapNotification, AuditLog,
    )

    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.doctor import doctor_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(doctor_bp)

    from flask_wtf.csrf import generate_csrf
    from markupsafe import Markup

    @app.context_processor
    def inject_helpers():
        def csrf_token_field():
            return Markup(f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">')
        return dict(csrf_token_field=csrf_token_field)

    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    return app
