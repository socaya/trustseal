from flask_wtf import FlaskForm
from wtforms import StringField, SelectField
from wtforms.validators import DataRequired, Optional

class DocumentPartyForm(FlaskForm):
    role = SelectField('Role', choices=[
        ('signer', 'Signer'),
        ('reviewer', 'Reviewer'),
        ('approver', 'Approver'),
        ('cc', 'CC')
    ], validators=[DataRequired()])
    user_id = StringField('User ID (optional)', validators=[Optional()])
    external_email = StringField('External Email (optional)', validators=[Optional()])
