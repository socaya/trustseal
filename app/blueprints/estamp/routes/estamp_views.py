from flask import render_template, request, redirect, url_for, flash
from .. import estamp_bp
from ....services import api_client
from ..forms.digital_stamp_form import DigitalStampForm

@estamp_bp.route('/estamps')
def view_digital_stamps():
    items = api_client.get_data("estamps") or []
    return render_template("estamps/list.html", items=items)

@estamp_bp.route('/estamps/create', methods=['GET', 'POST'])
def create_digital_stamp():
    form = DigitalStampForm()
    if form.validate_on_submit():
        result = api_client.post_data("estamps", data=form.data)
        if result and not result.get("error"):
            flash("DigitalStamp created.", "success")
            return redirect(url_for("estamp.view_digital_stamps"))
        flash(result.get("error", "Failed to create stamp."), "danger")
    return render_template("estamps/create.html", form=form)

@estamp_bp.route('/estamps/<int:item_id>/edit', methods=['GET', 'POST'])
def edit_digital_stamp(item_id):
    item = api_client.get_data(f"estamps/{item_id}")
    if not item or item.get("error"):
        flash("Stamp not found.", "danger")
        return redirect(url_for("estamp.view_digital_stamps"))

    form = DigitalStampForm(data=item)
    if request.method == 'POST' and form.validate_on_submit():
        result = api_client.put_data(f"estamps/{item_id}", data=form.data)
        if result and not result.get("error"):
            flash("DigitalStamp updated.", "success")
            return redirect(url_for("estamp.view_digital_stamps"))
        flash(result.get("error", "Update failed."), "danger")
    return render_template("estamps/edit.html", form=form, item=item)

@estamp_bp.route('/estamps/<int:item_id>/delete', methods=['POST'])
def delete_digital_stamp(item_id):
    result = api_client.delete_data(f"estamps/{item_id}")
    if result and result.get("success"):
        flash("DigitalStamp deleted.", "success")
    else:
        flash(result.get("error", "Failed to delete stamp."), "danger")
    return redirect(url_for("estamp.view_digital_stamps"))