from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Email, Optional, ValidationError
from app.models.user import User


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
    scale_type = StringField('Tipo de escala', validators=[Optional(), Length(max=100)])
    submit = SubmitField('Salvar')
