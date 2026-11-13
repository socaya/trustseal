from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, BooleanField
from wtforms.validators import Optional

class UserForm(FlaskForm):
    username = StringField('Username', validators=[Optional()])
    email = StringField('Email', validators=[Optional()])
    first_name = StringField('First Name', validators=[Optional()])
    last_name = StringField('Last Name', validators=[Optional()])
    phone = StringField('Phone', validators=[Optional()])
    is_active = BooleanField('Is Active', validators=[Optional()])
    organization_id = IntegerField('Organization Id', validators=[Optional()])
    subscription_id = IntegerField('Subscription Id', validators=[Optional()])
