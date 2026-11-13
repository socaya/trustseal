from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class StampUsageForm(FlaskForm):
    stamp_id = IntegerField('Stamp Id', validators=[DataRequired()])
    document_id = IntegerField('Document Id', validators=[DataRequired()])
    applied_by_id = IntegerField('Applied By Id', validators=[Optional()])
    applied_at = DateTimeField('Applied At', validators=[Optional()])
    page_number = IntegerField('Page Number', validators=[Optional()])
    coordinates = StringField('Coordinates', validators=[Optional()])
