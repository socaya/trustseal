from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class DigitalStampForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    image_path = StringField('Image Path', validators=[Optional()])
    color = StringField('Color', validators=[Optional()])
    organization_id = IntegerField('Organization Id', validators=[Optional()])
    is_active = BooleanField('Is Active', validators=[Optional()])