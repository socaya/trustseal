from flask import render_template, request, redirect, url_for, flash
from .. import subscriptions_bp
from ....services import api_client
from ..forms.subscription_plan_form import SubscriptionPlanForm

@subscriptions_bp.route('/plans')
def view_subscription_plans():
    items = api_client.get_data("subscriptions/plans") or []
    return render_template("subscriptions/plans/list.html", items=items)

@subscriptions_bp.route('/plans/create', methods=['GET', 'POST'])
def create_subscription_plan_view():
    form = SubscriptionPlanForm()
    if form.validate_on_submit():
        result = api_client.post_data("subscriptions/plans", data=form.data)
        if result and not result.get("error"):
            flash("Subscription plan created.", "success")
            return redirect(url_for("subscriptions.view_subscription_plans"))
        flash(result.get("error", "Failed to create plan."), "danger")
    return render_template("subscriptions/plans/create.html", form=form)

@subscriptions_bp.route('/plans/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_subscription_plan_view(item_id):
    item = api_client.get_data(f"subscriptions/plans/{item_id}")
    if not item or item.get("error"):
        flash("Plan not found.", "danger")
        return redirect(url_for("subscriptions.view_subscription_plans"))

    form = SubscriptionPlanForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"subscriptions/plans/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Plan updated.", "success")
            return redirect(url_for("subscriptions.view_subscription_plans"))
        flash(result.get("error", "Failed to update plan."), "danger")
    return render_template("subscriptions/plans/edit.html", form=form, item=item)

@subscriptions_bp.route('/plans/<int:item_id>/delete', methods=['POST'])
def delete_subscription_plan_view(item_id):
    result = api_client.delete_data(f"subscriptions/plans/{item_id}")
    if result.get("success"):
        flash("Subscription plan deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete plan."), "danger")
    return redirect(url_for("subscriptions.view_subscription_plans"))