from datetime import datetime
from app.extensions import db


class Location(db.Model):
    __tablename__ = 'locations'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text)
    scale_type = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    doctor_links = db.relationship('DoctorLocationLink', back_populates='location', lazy='dynamic')
    schedules = db.relationship('Schedule', back_populates='location', lazy='dynamic')

    def __repr__(self):
        return f'<Location {self.name}>'


class DoctorLocationLink(db.Model):
    __tablename__ = 'doctor_location_links'

    id = db.Column(db.Integer, primary_key=True)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('locations.id'), nullable=False)
    scale_type = db.Column(db.String(100))
    active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    doctor = db.relationship('User', back_populates='location_links')
    location = db.relationship('Location', back_populates='doctor_links')

    __table_args__ = (
        db.UniqueConstraint('doctor_id', 'location_id', 'scale_type', name='uq_doctor_location_scale'),
    )

    def __repr__(self):
        return f'<DoctorLocationLink doctor={self.doctor_id} location={self.location_id}>'
