from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class SignatureRequestForm(FlaskForm):
    document_id = IntegerField('Document Id', validators=[DataRequired()])
    sender_id = IntegerField('Sender Id', validators=[DataRequired()])
    status = SelectField('Status', validators=[Optional()])
    message = TextAreaField('Message', validators=[Optional()])
    due_date = DateTimeField('Due Date', validators=[Optional()])
    is_active = BooleanField('Is Active', validators=[Optional()])
