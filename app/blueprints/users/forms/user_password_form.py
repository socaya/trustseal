from flask_wtf import FlaskForm
from wtforms import PasswordField
from wtforms.validators import Optional

class UserPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[Optional()])
