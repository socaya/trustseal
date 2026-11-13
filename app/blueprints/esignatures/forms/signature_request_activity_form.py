from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class SignatureRequestActivityForm(FlaskForm):
    request_id = IntegerField('Request Id', validators=[DataRequired()])
    user_id = IntegerField('User Id', validators=[Optional()])
    action = StringField('Action', validators=[DataRequired()])
    details = TextAreaField('Details', validators=[Optional()])
    timestamp = DateTimeField('Timestamp', validators=[Optional()])
