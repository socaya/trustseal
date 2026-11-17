from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, BooleanField
from wtforms.validators import DataRequired, Optional


def _optional_int(value):
    if value in (None, "", "None"):
        return None
    return int(value)


class DocumentForm(FlaskForm):
    title = StringField('Title', validators=[DataRequired()])
    description = TextAreaField('Description', validators=[Optional()])
    content = TextAreaField('Content', validators=[Optional()])

    file = FileField('Upload File', validators=[
        Optional(),
        FileAllowed(['pdf', 'doc', 'docx', 'txt', 'png', 'jpg'], 'Only documents and images allowed.')
    ])

    document_type = SelectField('Document Type', coerce=_optional_int, validators=[Optional()])
    organization_id = SelectField('Organization', coerce=_optional_int, validators=[Optional()])
    client_id = SelectField('Client', coerce=_optional_int, validators=[Optional()])
    stamp_id = SelectField('Digital Stamp', coerce=_optional_int, validators=[Optional()])

    is_template = BooleanField('Is Template')
    is_shared = BooleanField('Is Shared')
    tags = StringField('Tags', validators=[Optional()])