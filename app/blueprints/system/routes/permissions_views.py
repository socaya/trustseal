from flask import render_template, request, redirect, url_for, flash
from .. import system_bp
from ....services import api_client

@system_bp.route('/permissions')
def view_permissions():
    items = api_client.get_data("permissions") or []
    return render_template("system/permissions/list.html", items=items)
