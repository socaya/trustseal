from flask import render_template, request, redirect, url_for, flash
from .. import subscriptions_bp
from ....services import api_client
from ..forms.payment_form import PaymentForm

@subscriptions_bp.route('/payments')
def view_payments():
    items = api_client.get_data("subscriptions/payments") or []
    return render_template("subscriptions/payments/list.html", items=items)

@subscriptions_bp.route('/payments/create', methods=['GET', 'POST'])
def create_payment_view():
    form = PaymentForm()
    if form.validate_on_submit():
        result = api_client.post_data("subscriptions/payments", data=form.data)
        if result and not result.get("error"):
            flash("Payment created.", "success")
            return redirect(url_for("subscriptions.view_payments"))
        flash(result.get("error", "Failed to create payment."), "danger")
    return render_template("subscriptions/payments/create.html", form=form)

@subscriptions_bp.route('/payments/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_payment_view(item_id):
    item = api_client.get_data(f"subscriptions/payments/{item_id}")
    if not item or item.get("error"):
        flash("Payment not found.", "danger")
        return redirect(url_for("subscriptions.view_payments"))

    form = PaymentForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"subscriptions/payments/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Payment updated.", "success")
            return redirect(url_for("subscriptions.view_payments"))
        flash(result.get("error", "Failed to update payment."), "danger")
    return render_template("subscriptions/payments/edit.html", form=form, item=item)

@subscriptions_bp.route('/payments/<int:item_id>/delete', methods=['POST'])
def delete_payment_view(item_id):
    result = api_client.delete_data(f"subscriptions/payments/{item_id}")
    if result.get("success"):
        flash("Payment deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete payment."), "danger")
    return redirect(url_for("subscriptions.view_payments"))