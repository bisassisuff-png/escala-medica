from flask_wtf import FlaskForm
from wtforms import IntegerField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired, Optional, NumberRange
from datetime import datetime


class FillingWindowForm(FlaskForm):
    year = IntegerField('Ano da escala', validators=[
        DataRequired(), NumberRange(min=2024, max=2100)
    ], default=datetime.utcnow().year + 1)
    open_at = DateTimeLocalField('Abertura (opcional)', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    close_at = DateTimeLocalField('Encerramento (opcional)', format='%Y-%m-%dT%H:%M', validators=[Optional()])
    submit = SubmitField('Salvar')
