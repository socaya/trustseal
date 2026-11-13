from flask_wtf import FlaskForm
from wtforms import IntegerField, TextAreaField, SubmitField
from wtforms.validators import DataRequired

class DocumentCommentForm(FlaskForm):
    document_id = IntegerField("Document ID", validators=[DataRequired()])
    user_id = IntegerField("User ID")
    comment = TextAreaField("Comment", validators=[DataRequired()])
    submit = SubmitField("Submit Comment")
