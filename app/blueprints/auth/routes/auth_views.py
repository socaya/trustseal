from flask import (
    render_template, request, redirect, url_for,
    flash, session, Blueprint, current_app
)
from flask_login import login_user, logout_user, login_required, current_user
from ..forms.login_form import LoginForm
from ..forms.registration_form import RegistrationForm
from ....services import api_client
from ....models.api_user import APILoginUser
from ....services.api_client import post_data, get_data

auth_views = Blueprint('auth_views', __name__, url_prefix='/auth')

# --- Register ---
@auth_views.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        payload = {
            "username": form.username.data,
            "email": form.email.data,
            "first_name": form.first_name.data,
            "last_name": form.last_name.data,
            "phone": form.phone.data,
            "password": form.password.data
        }
        current_app.logger.debug(f"🔧 Register API payload: {payload}")
        result = post_data("auth/register", data=payload)

        if result and not result.get("error") and "access_token" in result:
            flash("Account created successfully. Please log in.", "success")
            return redirect(url_for("auth_views.login"))

        flash(result.get("error", "Registration failed."), "danger")
    return render_template("auth/register.html", form=form)

# --- Login ---
@auth_views.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        payload = {
            "identifier": form.identifier.data,
            "password": form.password.data
        }

        # ⛳ Force login POST to the full API endpoint!
        result = api_client.post_data("auth/login", data=payload)

        current_app.logger.debug(f"🔄 Login result: {result}")

        if result.get("access_token"):
            # Save tokens
            session["access_token"] = result["access_token"]
            session["refresh_token"] = result.get("refresh_token")

            # Decode token and log in user
            from flask_jwt_extended import decode_token
            decoded = decode_token(result["access_token"])
            user_id = decoded.get("sub")

            from app.models import User
            user = User.query.get(user_id)
            if user:
                login_user(user)

            # Redirect to next or home
            next_url = request.args.get("next") or session.pop("next_url", None) or url_for("system.main_views.home")
            current_app.logger.debug(f"✅ Redirecting to: {next_url}")
            return redirect(next_url)

        flash(result.get("error") or "Login failed", "danger")

    return render_template("auth/login.html", form=form)

# --- Logout ---
@auth_views.route('/logout')
@login_required
def logout():
    user_id = current_user.get_id()
    logout_user()
    session.clear()
    flash("Logged out successfully.", "success")
    current_app.logger.info(f"👋 User ID {user_id} logged out.")
    return redirect(url_for("auth_views.login"))

# --- Profile ---
# The design-system profile UI lives at /app/profile (profile_views.show).
# Keep /auth/profile as a 301 redirect so any legacy bookmark still works.
@auth_views.route('/profile')
@login_required
def profile():
    return redirect(url_for("profile_views.show"), code=301)