"""Authentication routes."""
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash

from app.auth import bp
from app.models import User


@bp.route("/register", methods=["GET", "POST"])
def register():
    """User registration."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("auth.register"))

        if User.exists(email):
            flash("A user with this email already exists.", "warning")
            return redirect(url_for("auth.register"))

        user = User.create(
            email=email,
            password_hash=generate_password_hash(password),
            created_at=datetime.utcnow().isoformat()
        )

        if user:
            login_user(user)
            flash("Registered and logged in!", "success")
            return redirect(url_for("main.index"))

        flash("Registration failed. Please try again.", "danger")
        return redirect(url_for("auth.register"))

    return render_template(
        "register.html",
        app_name=current_app.config['APP_NAME']
    )


@bp.route("/login", methods=["GET", "POST"])
def login():
    """User login."""
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        user_row = User.get_by_email(email)

        if not user_row or not check_password_hash(user_row["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return redirect(url_for("auth.login"))

        user = User(user_row)
        login_user(user)
        flash("Logged in.", "success")
        return redirect(url_for("main.index"))

    return render_template(
        "login.html",
        app_name=current_app.config['APP_NAME']
    )


@bp.route("/logout")
@login_required
def logout():
    """User logout."""
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("auth.login"))
