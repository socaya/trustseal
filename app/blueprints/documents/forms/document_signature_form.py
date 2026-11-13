from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Optional

class DocumentSignatureForm(FlaskForm):
    signature_type = SelectField('Signature Type', choices=[
        ('drawn', 'Drawn'),
        ('uploaded', 'Uploaded'),
        ('text', 'Text')
    ], validators=[DataRequired()])
    signature_data = TextAreaField('Signature Data (SVG or text)', validators=[DataRequired()])
    ip_address = StringField('IP Address', validators=[Optional()])
