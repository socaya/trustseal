from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class ClientForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    email = StringField('Email', validators=[Optional()])
    phone = StringField('Phone', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    tax_id = StringField('Tax Id', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])
    organization_id = IntegerField('Organization Id', validators=[DataRequired()])
    is_active = BooleanField('Is Active', validators=[Optional()])