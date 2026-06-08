from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    login = StringField('Login', validators=[DataRequired(), Length(3, 100)])
    password = PasswordField('Senha', validators=[DataRequired()])
    remember = BooleanField('Manter conectado')
    submit = SubmitField('Entrar')
