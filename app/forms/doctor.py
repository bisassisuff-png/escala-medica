from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, ValidationError
from datetime import date

DAY_CHOICES = [
    (0, 'Segunda-feira'), (1, 'Terça-feira'), (2, 'Quarta-feira'),
    (3, 'Quinta-feira'), (4, 'Sexta-feira'), (5, 'Sábado'), (6, 'Domingo'),
]
WEEK_CHOICES = [
    (1, '1ª semana'), (2, '2ª semana'), (3, '3ª semana'),
    (4, '4ª semana'), (5, '5ª semana'),
]
FREQ_CHOICES = [
    ('weekly', 'Semanal (toda semana)'),
    ('biweekly', 'Quinzenal (a cada 2 semanas)'),
    ('monthly', 'Mensal (uma vez por mês)'),
]


class DoctorRoutineForm(FlaskForm):
    location_id = SelectField('Local de atendimento', coerce=int, validators=[DataRequired()])
    scale_type = StringField('Tipo de escala', validators=[Optional()])
    frequency = SelectField('Frequência', choices=FREQ_CHOICES, validators=[DataRequired()])
    day_of_week = SelectField('Dia da semana', choices=DAY_CHOICES, coerce=int, validators=[DataRequired()])
    week_of_month = SelectField('Semana do mês', choices=[(0, '—')] + WEEK_CHOICES,
                                coerce=int, validators=[Optional()])
    submit = SubmitField('Adicionar rotina')

    def __init__(self, doctor=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if doctor:
            from app.models.location import DoctorLocationLink
            links = (DoctorLocationLink.query
                     .filter_by(doctor_id=doctor.id, active=True)
                     .join(DoctorLocationLink.location)
                     .order_by('name')
                     .all())
            self.location_id.choices = [(lk.location_id, lk.location.name) for lk in links]
        else:
            self.location_id.choices = []

    def validate_week_of_month(self, field):
        if self.frequency.data in ('biweekly', 'monthly') and not field.data:
            raise ValidationError('Informe a semana do mês para esta frequência.')


class DoctorRestrictionForm(FlaskForm):
    restricted_date = DateField('Data de restrição', validators=[DataRequired()])
    reason = TextAreaField('Motivo (opcional)', validators=[Optional()])
    submit = SubmitField('Adicionar restrição')

    def validate_restricted_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('A data não pode ser no passado.')
