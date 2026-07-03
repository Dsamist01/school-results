from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """One-time route to create the first admin account. Disabled once an
    admin already exists."""
    if User.query.filter_by(role="admin").count() > 0:
        flash("Setup already completed. Please log in.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Please fill all fields. Password must be at least 6 characters.", "danger")
            return render_template("auth/setup.html")
        if User.query.filter_by(email=email).first():
            flash("That email is already in use.", "danger")
            return render_template("auth/setup.html")
        user = User(name=name, email=email, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Admin account created. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/setup.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if User.query.filter_by(role="admin").count() == 0:
        return redirect(url_for("auth.setup"))

    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.active and user.check_password(password):
            login_user(user)
            return redirect(url_for("main.index"))
        flash("Invalid email or password.", "danger")

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
