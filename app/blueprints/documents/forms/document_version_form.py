from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class DocumentVersionForm(FlaskForm):
    version_number = StringField('Version Number', validators=[DataRequired()])
    file_path = StringField('File Path', validators=[DataRequired()])
    uploaded_by_id = IntegerField('Uploaded By Id', validators=[Optional()])
    document_id = IntegerField('Document Id', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
