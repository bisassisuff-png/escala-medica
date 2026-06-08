from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login_manager

import sqlalchemy as sa


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    crm = db.Column(db.String(20), unique=True, nullable=True)
    login = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(200), unique=True, nullable=False)
    role = db.Column(sa.Enum('admin', 'medico', name='user_role'), nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    routines = db.relationship('DoctorRoutine', back_populates='doctor', lazy='dynamic')
    restrictions = db.relationship('DoctorRestriction', back_populates='doctor', lazy='dynamic')
    schedules = db.relationship('Schedule', back_populates='doctor', lazy='dynamic')
    location_links = db.relationship('DoctorLocationLink', back_populates='doctor', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_medico(self):
        return self.role == 'medico'

    def get_id(self):
        return str(self.id)

    def __repr__(self):
        return f'<User {self.login} ({self.role})>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
