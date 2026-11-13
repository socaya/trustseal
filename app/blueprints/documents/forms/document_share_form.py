from flask_wtf import FlaskForm
from wtforms import StringField, BooleanField
from wtforms.validators import Optional

class DocumentShareForm(FlaskForm):
    shared_with_email = StringField('Email', validators=[Optional()])
    can_view = BooleanField('Can View')
    can_edit = BooleanField('Can Edit')
    can_sign = BooleanField('Can Sign')
    can_stamp = BooleanField('Can Stamp')
    can_download = BooleanField('Can Download')
    can_share = BooleanField('Can Share')
