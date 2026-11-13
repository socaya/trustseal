from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional

class DocumentActivityForm(FlaskForm):
    action = StringField('Action', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    performed_by_id = IntegerField('Performed By Id', validators=[Optional()])
    timestamp = DateTimeField('Timestamp', validators=[Optional()])
    document_id = IntegerField('Document Id', validators=[Optional()])