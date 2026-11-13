from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, DateTimeField
from wtforms.validators import DataRequired, Optional, Email, URL

class OrganizationForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    legal_name = StringField('Legal Name', validators=[Optional()])
    registration_number = StringField('Registration Number', validators=[Optional()])
    tax_id = StringField('Tax ID', validators=[Optional()])
    country = StringField('Country', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    phone = StringField('Phone', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    website = StringField('Website', validators=[Optional(), URL()])
    logo_path = StringField('Logo Path', validators=[Optional()])
    type = SelectField('Type', choices=[('individual', 'Individual'), ('company', 'Company')], validators=[DataRequired()])
    is_verified = BooleanField('Verified')
    verified_at = DateTimeField('Verified At', validators=[Optional()])
    verification_notes = TextAreaField('Verification Notes', validators=[Optional()])
    is_active = BooleanField('Is Active')