from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, ValidationError
from app.models.user import User
from app.models.location import Location


class DoctorForm(FlaskForm):
    name = StringField('Nome completo', validators=[DataRequired(), Length(2, 200)])
    crm = StringField('CRM', validators=[Optional(), Length(max=20)])
    login = StringField('Login', validators=[DataRequired(), Length(3, 100)])
    email = StringField('E-mail', validators=[DataRequired(), Email(), Length(max=200)])
    password = PasswordField('Senha', validators=[Optional(), Length(min=6)])
    submit = SubmitField('Salvar')

    def __init__(self, doctor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._doctor = doctor

    def validate_login(self, field):
        existing = User.query.filter_by(login=field.data).first()
        if existing and (self._doctor is None or existing.id != self._doctor.id):
            raise ValidationError('Este login já está em uso.')

    def validate_email(self, field):
        existing = User.query.filter_by(email=field.data).first()
        if existing and (self._doctor is None or existing.id != self._doctor.id):
            raise ValidationError('Este e-mail já está cadastrado.')

    def validate_crm(self, field):
        if not field.data:
            return
        existing = User.query.filter_by(crm=field.data).first()
        if existing and (self._doctor is None or existing.id != self._doctor.id):
            raise ValidationError('Este CRM já está cadastrado.')


class LocationForm(FlaskForm):
    name = StringField('Nome', validators=[DataRequired(), Length(2, 200)])
    address = TextAreaField('Endereço', validators=[Optional(), Length(max=500)])
    scale_type = StringField('Tipo de escala', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Salvar')


class DoctorLocationLinkForm(FlaskForm):
    doctor_id = SelectField('Médico', coerce=int, validators=[DataRequired()])
    location_id = SelectField('Local', coerce=int, validators=[DataRequired()])
    scale_type = StringField('Tipo de escala', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Salvar')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor_id.choices = [
            (u.id, f'{u.name} — CRM {u.crm or "s/n"}')
            for u in User.query.filter_by(role='medico', active=True).order_by(User.name).all()
        ]
        self.location_id.choices = [
            (l.id, l.name)
            for l in Location.query.filter_by(active=True).order_by(Location.name).all()
        ]
