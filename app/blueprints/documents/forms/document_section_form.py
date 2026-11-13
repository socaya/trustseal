from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired

class DocumentSectionForm(FlaskForm):
    document_id = IntegerField("Document ID", validators=[DataRequired()])
    section_title = StringField("Section Title", validators=[DataRequired()])
    section_content = TextAreaField("Section Content", validators=[DataRequired()])
    order = IntegerField("Order")
    submit = SubmitField("Save Section")