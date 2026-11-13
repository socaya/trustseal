from flask_wtf import FlaskForm
from wtforms import SelectField, IntegerField
from wtforms.validators import DataRequired

class AssignUserRoleForm(FlaskForm):
    user_id = IntegerField('User ID', validators=[DataRequired()])
    role_id = SelectField('Role', coerce=int, validators=[DataRequired()])
