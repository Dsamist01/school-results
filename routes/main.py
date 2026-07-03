from flask import Blueprint, redirect, url_for, render_template
from flask_login import login_required, current_user

from models import User

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    if current_user.is_admin():
        return redirect(url_for("admin.dashboard"))
    return redirect(url_for("teacher.dashboard"))
