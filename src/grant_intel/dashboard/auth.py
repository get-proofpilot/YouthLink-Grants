"""Flask-Login authentication for single admin user."""

import os

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

auth_bp = Blueprint("auth", __name__)


class AdminUser(UserMixin):
    """Single admin user for dashboard access."""

    def __init__(self):
        self.id = "admin"


def init_login_manager(app):
    """Initialize Flask-Login with the app."""
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Please log in to access the dashboard."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == "admin":
            return AdminUser()
        return None


def verify_credentials(username: str, password: str) -> bool:
    """Verify admin credentials against environment variables."""
    expected_user = os.getenv("DASHBOARD_USERNAME", "admin")
    password_hash = os.getenv("DASHBOARD_PASSWORD_HASH", "")

    if not password_hash:
        raise RuntimeError(
            "DASHBOARD_PASSWORD_HASH is not set. "
            "Generate one with: python -c \"from grant_intel.dashboard.auth import hash_password; print(hash_password('yourpassword'))\""
        )

    return username == expected_user and check_password_hash(password_hash, password)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if verify_credentials(username, password):
            login_user(AdminUser())
            next_page = request.args.get("next")
            # Validate next_page is a relative URL to prevent open redirect
            if next_page and (not next_page.startswith("/") or next_page.startswith("//")):
                next_page = None
            return redirect(next_page or url_for("main.home"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))


def hash_password(password: str) -> str:
    """Generate a password hash for storing in .env.

    Usage: python -c "from grant_intel.dashboard.auth import hash_password; print(hash_password('mypassword'))"
    """
    return generate_password_hash(password)
