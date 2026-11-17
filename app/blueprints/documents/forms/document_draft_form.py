from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, BooleanField, SelectField, FileField, HiddenField
from wtforms.validators import DataRequired, Optional


def _optional_int(value):
    if value in (None, "", "None"):
        return None
    return int(value)


class DocumentDraftForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    content = TextAreaField('Content (HTML)', validators=[Optional()])
    document_type = SelectField('Document Type', coerce=_optional_int, validators=[Optional()])
    status = SelectField('Status', choices=[
        ('draft', 'Draft'),
        ('in_review', 'In Review'),
        ('ready', 'Ready')
    ], default='draft')
    is_template = BooleanField('Is Template')
    tags = StringField('Tags', validators=[Optional()])
    file = FileField('Upload File (optional)', validators=[Optional()])
