from flask import render_template, request, redirect, url_for, flash
from .. import estamp_bp
from ....services import api_client
from ..forms.stamp_template_form import StampTemplateForm

@estamp_bp.route('/stamp_templates')
def view_stamp_templates():
    items = api_client.get_data("estamps/templates") or []
    return render_template("estamps/templates/list.html", items=items)

@estamp_bp.route('/stamp_templates/create', methods=['GET', 'POST'])
def create_stamp_template():
    form = StampTemplateForm()
    if form.validate_on_submit():
        result = api_client.post_data("estamps/templates", data=form.data)
        if result and not result.get("error"):
            flash("StampTemplate created.", "success")
            return redirect(url_for("estamp.view_stamp_templates"))
        flash(result.get("error", "Creation failed."), "danger")
    return render_template("estamps/templates/create.html", form=form)

@estamp_bp.route('/stamp_templates/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_stamp_template(item_id):
    item = api_client.get_data(f"estamps/templates/{item_id}")
    if not item or item.get("error"):
        flash("Template not found.", "danger")
        return redirect(url_for("estamp.view_stamp_templates"))

    form = StampTemplateForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"estamps/templates/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("StampTemplate updated.", "success")
            return redirect(url_for("estamp.view_stamp_templates"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("estamps/templates/edit.html", form=form, item=item)

@estamp_bp.route('/stamp_templates/<int:item_id>/delete', methods=['POST'])
def delete_stamp_template(item_id):
    result = api_client.delete_data(f"estamps/templates/{item_id}")
    if result and result.get("success"):
        flash("Template deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete template."), "danger")
    return redirect(url_for("estamp.view_stamp_templates"))