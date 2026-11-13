from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, DateTimeField, BooleanField, SubmitField
from wtforms.validators import DataRequired

class DocumentReminderForm(FlaskForm):
    document_id = IntegerField("Document ID", validators=[DataRequired()])
    user_id = IntegerField("User ID")
    email = StringField("Email")
    phone = StringField("Phone")
    send_email = BooleanField("Send Email")
    send_sms = BooleanField("Send SMS")
    remind_at = DateTimeField("Remind At", format='%Y-%m-%d %H:%M:%S', validators=[DataRequired()])
    message = StringField("Reminder Message")
    submit = SubmitField("Save Reminder")