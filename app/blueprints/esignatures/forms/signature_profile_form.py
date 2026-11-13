from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class SignatureProfileForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    user_id = IntegerField('User Id', validators=[Optional()])
    default = BooleanField('Default', validators=[Optional()])
    is_active = BooleanField('Is Active', validators=[Optional()])
