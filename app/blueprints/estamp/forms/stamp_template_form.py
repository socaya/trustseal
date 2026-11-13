from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional

class StampTemplateForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    template_path = StringField('Template Path', validators=[Optional()])
    default_color = StringField('Default Color', validators=[Optional()])
    default_text = TextAreaField('Default Text', validators=[Optional()])
    type = StringField('Type', validators=[Optional()])
    is_active = BooleanField('Is Active', validators=[Optional()])
