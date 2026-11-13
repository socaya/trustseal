from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class SubscriptionForm(FlaskForm):
    plan_id = IntegerField('Plan Id', validators=[DataRequired()])
    organization_id = IntegerField('Organization Id', validators=[DataRequired()])
    start_date = DateTimeField('Start Date', validators=[DataRequired()])
    end_date = DateTimeField('End Date', validators=[DataRequired()])
    is_active = BooleanField('Is Active', validators=[Optional()])
    payment_method = StringField('Payment Method', validators=[Optional()])
    auto_renew = BooleanField('Auto Renew', validators=[Optional()])
    notes = TextAreaField('Notes', validators=[Optional()])