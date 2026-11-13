from flask_wtf import FlaskForm
from wtforms.fields.simple import StringField, TextAreaField
from wtforms.validators import Optional


class RoleForm(FlaskForm):
    name = StringField('Name', validators=[Optional()])
    description = TextAreaField('Description', validators=[Optional()])
