from flask import render_template, request, redirect, url_for, flash
from .. import subscriptions_bp
from ....services import api_client
from ..forms.subscription_form import SubscriptionForm

@subscriptions_bp.route('/subscriptions')
def view_subscriptions():
    items = api_client.get_data("subscriptions") or []
    return render_template("subscriptions/list.html", items=items)

@subscriptions_bp.route('/subscriptions/create', methods=['GET', 'POST'])
def create_subscription_view():
    form = SubscriptionForm()
    if form.validate_on_submit():
        result = api_client.post_data("subscriptions", data=form.data)
        if result and not result.get("error"):
            flash("Subscription created.", "success")
            return redirect(url_for("subscriptions.view_subscriptions"))
        flash(result.get("error", "Failed to create subscription."), "danger")
    return render_template("subscriptions/create.html", form=form)

@subscriptions_bp.route('/subscriptions/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_subscription_view(item_id):
    item = api_client.get_data(f"subscriptions/{item_id}")
    if not item or item.get("error"):
        flash("Subscription not found.", "danger")
        return redirect(url_for("subscriptions.view_subscriptions"))

    form = SubscriptionForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"subscriptions/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Subscription updated.", "success")
            return redirect(url_for("subscriptions.view_subscriptions"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("subscriptions/edit.html", form=form, item=item)

@subscriptions_bp.route('/subscriptions/<int:item_id>/delete', methods=['POST'])
def delete_subscription_view(item_id):
    result = api_client.delete_data(f"subscriptions/{item_id}")
    if result.get("success"):
        flash("Subscription deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete subscription."), "danger")
    return redirect(url_for("subscriptions.view_subscriptions"))