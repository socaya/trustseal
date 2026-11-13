from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from app.blueprints.system import system_bp

main_views = Blueprint('main_views', __name__)

@main_views.route('/')
def home():
    if not current_user.is_authenticated:
        return redirect(url_for('auth_views.login'))
    return render_template("dashboard.html")