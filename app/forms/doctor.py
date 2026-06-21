from flask_wtf import FlaskForm
from wtforms import DateField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Optional, ValidationError
from datetime import date


class DoctorRestrictionForm(FlaskForm):
    restricted_date = DateField('Data de restrição', validators=[DataRequired()])
    reason = TextAreaField('Motivo (opcional)', validators=[Optional()])
    submit = SubmitField('Adicionar restrição')

    def validate_restricted_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError('A data não pode ser no passado.')
