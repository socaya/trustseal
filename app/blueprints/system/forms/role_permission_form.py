from flask_wtf import FlaskForm
from wtforms.fields.numeric import IntegerField
from wtforms.validators import Optional


class RolePermissionForm(FlaskForm):
    role_id = IntegerField('Role Id', validators=[Optional()])
    permission_id = IntegerField('Permission Id', validators=[Optional()])