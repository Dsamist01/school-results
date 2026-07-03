import os
from flask import Flask, render_template
from flask_login import current_user

from config import Config
from extensions import db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(os.path.join(app.root_path, "instance"), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.teacher import teacher_bp
    from routes.results import results_bp
    from routes.main import main_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(teacher_bp, url_prefix="/teacher")
    app.register_blueprint(results_bp, url_prefix="/results")

    @app.context_processor
    def inject_globals():
        from models import SchoolSettings
        try:
            school = SchoolSettings.get()
        except Exception:
            school = None
        return dict(school=school, current_user=current_user)

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors.html", code=403, message="You don't have access to that page."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors.html", code=404, message="Page not found."), 404

    with app.app_context():
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "logos"), exist_ok=True)
        os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "students"), exist_ok=True)
        db.create_all()
        _migrate_new_columns()
        _seed_defaults()

    return app


def _migrate_new_columns():
    """Lightweight auto-migration: adds any columns that were added to the
    models after a person's database was first created, so existing
    installs don't need to delete their data to pick up updates."""
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    checks = [
        ("student", "photo_path", "VARCHAR(255) DEFAULT ''"),
        ("school_settings", "logo_path", "VARCHAR(255) DEFAULT ''"),
    ]
    for table, column, coltype in checks:
        if table not in inspector.get_table_names():
            continue
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        if column not in existing_cols:
            with db.engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))


def _seed_defaults():
    """Creates default grading scale & skill list on first run, if empty."""
    from models import GradeBand, Skill, SchoolSettings

    if SchoolSettings.query.count() == 0:
        db.session.add(SchoolSettings())

    if GradeBand.query.count() == 0:
        defaults = [
            (90, 100, "A+", "Outstanding"),
            (80, 89.99, "A", "Excellent"),
            (70, 79.99, "B+", "Very Good"),
            (60, 69.99, "B", "Good"),
            (50, 59.99, "C", "Average"),
            (40, 49.99, "D", "Below Average"),
            (0, 39.99, "F", "Fail"),
        ]
        for mn, mx, g, r in defaults:
            db.session.add(GradeBand(min_score=mn, max_score=mx, grade=g, remark=r))

    if Skill.query.count() == 0:
        default_skills = [
            "Punctuality", "Diligence", "Honesty", "Initiative", "Co-operativeness",
            "Legibility", "Accuracy", "Musical Skills", "Perseverance", "Self-Control",
            "Reliability", "Organisation Ability", "Curiosity", "Dexterity",
            "Sport & Games", "Drawing/Painting", "Responsibility", "Neatness",
            "Attendance", "Attentiveness", "Creativity", "Handling of Tools",
            "Physical Activities",
        ]
        for i, name in enumerate(default_skills):
            db.session.add(Skill(name=name, order=i))

    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
