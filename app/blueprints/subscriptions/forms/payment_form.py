from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, BooleanField, DateTimeField, SelectField, DecimalField
from wtforms.validators import DataRequired, Optional, Email

class PaymentForm(FlaskForm):
    subscription_id = IntegerField('Subscription Id', validators=[DataRequired()])
    amount = DecimalField('Amount', validators=[DataRequired()])
    payment_method = StringField('Payment Method', validators=[Optional()])
    transaction_reference = StringField('Transaction Reference', validators=[Optional()])
    status = StringField('Status', validators=[Optional()])
    paid_at = DateTimeField('Paid At', validators=[Optional()])
    currency = StringField('Currency', validators=[Optional()])
    payer_email = StringField('Payer Email', validators=[Optional()])
    payer_phone = StringField('Payer Phone', validators=[Optional()])
