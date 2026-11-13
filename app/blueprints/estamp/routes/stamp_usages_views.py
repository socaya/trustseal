from flask import render_template, request, redirect, url_for, flash
from .. import estamp_bp
from ....services import api_client
from ..forms.stamp_usage_form import StampUsageForm

@estamp_bp.route('/stamp_usages')
def view_stamp_usages():
    items = api_client.get_data("estamps/usages") or []
    return render_template("estamps/usages/list.html", items=items)

@estamp_bp.route('/stamp_usages/create', methods=['GET', 'POST'])
def create_stamp_usage():
    form = StampUsageForm()
    if form.validate_on_submit():
        result = api_client.post_data("estamps/usages", data=form.data)
        if result and not result.get("error"):
            flash("StampUsage recorded.", "success")
            return redirect(url_for("estamp.view_stamp_usages"))
        flash(result.get("error", "Failed to record usage."), "danger")
    return render_template("estamps/usages/create.html", form=form)

@estamp_bp.route('/stamp_usages/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_stamp_usage(item_id):
    item = api_client.get_data(f"estamps/usages/{item_id}")
    if not item or item.get("error"):
        flash("Usage not found.", "danger")
        return redirect(url_for("estamp.view_stamp_usages"))

    form = StampUsageForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"estamps/usages/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("Usage updated.", "success")
            return redirect(url_for("estamp.view_stamp_usages"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("estamps/usages/edit.html", form=form, item=item)

@estamp_bp.route('/stamp_usages/<int:item_id>/delete', methods=['POST'])
def delete_stamp_usage(item_id):
    result = api_client.delete_data(f"estamps/usages/{item_id}")
    if result and result.get("success"):
        flash("Usage deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete usage."), "danger")
    return redirect(url_for("estamp.view_stamp_usages"))