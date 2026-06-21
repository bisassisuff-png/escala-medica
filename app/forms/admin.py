from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField
from wtforms.validators import DataRequired, Length, Email, Optional, ValidationError
from app.models.user import User


class DoctorForm(FlaskForm):
    name = StringField('Nome completo', validators=[DataRequired(), Length(2, 200)])
    crm = StringField('CRM', validators=[Optional(), Length(max=20)])
    phone = StringField('Telefone', validators=[Optional(), Length(max=30)])
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
    submit = SubmitField('Salvar')


class AdminRoutineForm(FlaskForm):
    doctor_id = SelectField('Médico', coerce=int, validators=[DataRequired()])
    frequency = SelectField('Frequência', choices=[
        ('weekly', 'Semanal'), ('biweekly', 'Quinzenal'), ('monthly', 'Mensal'),
    ], validators=[DataRequired()])
    week_of_month = SelectField('Semana', choices=[
        (0, '—'), (1, '1ª'), (2, '2ª'), (3, '3ª'), (4, '4ª'), (5, '5ª'),
    ], coerce=int, validators=[Optional()])
    submit = SubmitField('Adicionar')

    def __init__(self, doctor_choices=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor_id.choices = doctor_choices or []

    def validate_week_of_month(self, field):
        if self.frequency.data in ('biweekly', 'monthly') and not field.data:
            raise ValidationError('Informe a semana do mês para esta frequência.')
