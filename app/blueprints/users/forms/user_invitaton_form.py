from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField
from wtforms.validators import Optional

class UserInvitationForm(FlaskForm):
    email = StringField('Email', validators=[Optional()])
    token = StringField('Token', validators=[Optional()])
    role = StringField('Role', validators=[Optional()])
    organization_id = IntegerField('Organization Id', validators=[Optional()])
    invited_by_id = IntegerField('Invited By Id', validators=[Optional()])