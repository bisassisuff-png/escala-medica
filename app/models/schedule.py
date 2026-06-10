from datetime import datetime
from app.extensions import db
import sqlalchemy as sa


class DoctorWindowConfirmation(db.Model):
    """Registra que um médico confirmou rotinas/restrições para uma janela."""
    __tablename__ = 'doctor_window_confirmations'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    window_id = db.Column(db.Integer, db.ForeignKey('filling_windows.id'), nullable=False)
    confirmed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    doctor = db.relationship('User', foreign_keys=[doctor_id])
    window = db.relationship('FillingWindow', foreign_keys=[window_id],
                             back_populates='confirmations')

    __table_args__ = (
        db.UniqueConstraint('doctor_id', 'window_id', name='uq_doctor_window_confirmation'),
    )


class FillingWindow(db.Model):
    __tablename__ = 'filling_windows'

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False)
    open_at = db.Column(db.DateTime)
    close_at = db.Column(db.DateTime)
    status = db.Column(
        sa.Enum('draft', 'open', 'closed', 'published', name='window_status'),
        default='draft', nullable=False
    )
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    creator = db.relationship('User', foreign_keys=[created_by])
    routines = db.relationship('DoctorRoutine', back_populates='window', lazy='dynamic')
    restrictions = db.relationship('DoctorRestriction', back_populates='window', lazy='dynamic')
    schedules = db.relationship('Schedule', back_populates='window', lazy='dynamic')
    confirmations = db.relationship('DoctorWindowConfirmation', back_populates='window', lazy='dynamic')
    holidays = db.relationship('Holiday', back_populates='window', lazy='dynamic')

    def __repr__(self):
        return f'<FillingWindow {self.year} ({self.status})>'


class DoctorRoutine(db.Model):
    __tablename__ = 'doctor_routines'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    window_id = db.Column(db.Integer, db.ForeignKey('filling_windows.id'), nullable=False)
    frequency = db.Column(
        sa.Enum('weekly', 'biweekly', 'monthly', name='routine_frequency'),
        nullable=False
    )
    day_of_week = db.Column(db.Integer)      # 0=seg … 6=dom
    week_of_month = db.Column(db.Integer)    # 1-5, NULL se weekly
    scale_type = db.Column(db.String(100))
    confirmed = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    doctor = db.relationship('User', back_populates='routines')
    location = db.relationship('Location')
    window = db.relationship('FillingWindow', back_populates='routines')

    def __repr__(self):
        return f'<DoctorRoutine doctor={self.doctor_id} freq={self.frequency}>'


class DoctorRestriction(db.Model):
    __tablename__ = 'doctor_restrictions'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    window_id = db.Column(db.Integer, db.ForeignKey('filling_windows.id'), nullable=False)
    restricted_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    doctor = db.relationship('User', back_populates='restrictions')
    window = db.relationship('FillingWindow', back_populates='restrictions')

    __table_args__ = (
        db.UniqueConstraint('doctor_id', 'restricted_date', name='uq_doctor_restriction_date'),
    )

    def __repr__(self):
        return f'<DoctorRestriction doctor={self.doctor_id} date={self.restricted_date}>'


class Holiday(db.Model):
    __tablename__ = 'holidays'

    id = db.Column(db.Integer, primary_key=True)
    window_id = db.Column(db.Integer, db.ForeignKey('filling_windows.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    window = db.relationship('FillingWindow', back_populates='holidays')

    __table_args__ = (
        db.UniqueConstraint('window_id', 'date', 'name', name='uq_holiday_window_date_name'),
    )

    def __repr__(self):
        return f'<Holiday {self.name} {self.date}>'


class Schedule(db.Model):
    __tablename__ = 'schedules'

    id = db.Column(db.Integer, primary_key=True)
    window_id = db.Column(db.Integer, db.ForeignKey('filling_windows.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    scale_type = db.Column(db.String(100))
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    source = db.Column(
        sa.Enum('routine', 'generated', 'manual', name='schedule_source'),
        nullable=False
    )
    status = db.Column(
        sa.Enum('draft', 'approved', 'published', name='schedule_status'),
        default='draft', nullable=False
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    window = db.relationship('FillingWindow', back_populates='schedules')
    location = db.relationship('Location', back_populates='schedules')
    doctor = db.relationship('User', back_populates='schedules')
    swaps = db.relationship('ScheduleSwap', back_populates='schedule', lazy='dynamic')

    def __repr__(self):
        return f'<Schedule date={self.date} doctor={self.doctor_id} location={self.location_id}>'
