from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SubmitField
from wtforms.validators import DataRequired

class DocumentTemplateForm(FlaskForm):
    name = StringField("Template Name", validators=[DataRequired()])
    content = TextAreaField("Content", validators=[DataRequired()])
    description = TextAreaField("Description")
    is_active = BooleanField("Active", default=True)
    submit = SubmitField("Save Template")
