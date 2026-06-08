from datetime import datetime
from app.extensions import db
import sqlalchemy as sa


class ScheduleSwap(db.Model):
    __tablename__ = 'schedule_swaps'

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('schedules.id'), nullable=False)
    target_doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(
        sa.Enum('open', 'accepted', 'rejected', 'cancelled', name='swap_status'),
        default='open', nullable=False
    )
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    requester = db.relationship('User', foreign_keys=[requester_id])
    target_doctor = db.relationship('User', foreign_keys=[target_doctor_id])
    schedule = db.relationship('Schedule', back_populates='swaps')
    notifications = db.relationship('SwapNotification', back_populates='swap', lazy='dynamic')

    def __repr__(self):
        return f'<ScheduleSwap schedule={self.schedule_id} status={self.status}>'


class SwapNotification(db.Model):
    __tablename__ = 'swap_notifications'

    id = db.Column(db.Integer, primary_key=True)
    swap_id = db.Column(db.Integer, db.ForeignKey('schedule_swaps.id'), nullable=False)
    notified_doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    seen = db.Column(db.Boolean, default=False, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    swap = db.relationship('ScheduleSwap', back_populates='notifications')
    notified_doctor = db.relationship('User', foreign_keys=[notified_doctor_id])

    def __repr__(self):
        return f'<SwapNotification swap={self.swap_id} doctor={self.notified_doctor_id}>'
