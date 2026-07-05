from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, request, flash, abort, send_file
from flask_login import login_required, current_user

from extensions import db
from models import (User, SchoolClass, Subject, ClassSubject, TeacherAssignment,
                     Student, GradeBand, Skill, SchoolSettings)
from utils.uploads import save_image, delete_image
from utils.backup import build_backup_zip

admin_bp = Blueprint("admin", __name__)


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin():
            abort(403)
        return fn(*args, **kwargs)
    return wrapper


def _require_class_access(sc):
    """Allows admin, or the form teacher of this specific class. Aborts 403 otherwise."""
    if current_user.is_admin():
        return
    if sc.form_teacher_id == current_user.id:
        return
    abort(403)


# ---------------------------------------------------------------- dashboard
@admin_bp.route("/")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html",
                            class_count=SchoolClass.query.count(),
                            student_count=Student.query.count(),
                            teacher_count=User.query.filter_by(role="teacher").count(),
                            subject_count=Subject.query.count())


# ------------------------------------------------------------------ classes
@admin_bp.route("/classes", methods=["GET", "POST"])
@admin_required
def classes():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Class name is required.", "danger")
        elif SchoolClass.query.count() >= 20:
            flash("Maximum of 20 classes reached.", "danger")
        elif SchoolClass.query.filter_by(name=name).first():
            flash("A class with that name already exists.", "danger")
        else:
            db.session.add(SchoolClass(name=name))
            db.session.commit()
            flash(f"Class '{name}' added.", "success")
        return redirect(url_for("admin.classes"))

    all_classes = SchoolClass.query.order_by(SchoolClass.name).all()
    teachers = User.query.filter_by(role="teacher", active=True).order_by(User.name).all()
    return render_template("admin/classes.html", classes=all_classes, teachers=teachers)


@admin_bp.route("/classes/<int:class_id>/delete", methods=["POST"])
@admin_required
def delete_class(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    db.session.delete(sc)
    db.session.commit()
    flash(f"Class '{sc.name}' deleted.", "info")
    return redirect(url_for("admin.classes"))


@admin_bp.route("/classes/<int:class_id>/edit", methods=["POST"])
@admin_required
def edit_class(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    new_name = request.form.get("name", "").strip()
    if not new_name:
        flash("Class name can't be empty.", "danger")
    elif SchoolClass.query.filter(db.func.lower(SchoolClass.name) == new_name.lower(),
                                   SchoolClass.id != class_id).first():
        flash(f"A class named '{new_name}' already exists.", "warning")
    else:
        old_name = sc.name
        sc.name = new_name
        db.session.commit()
        flash(f"Renamed '{old_name}' to '{new_name}'.", "success")
    return redirect(url_for("admin.classes"))


@admin_bp.route("/classes/<int:class_id>/form-teacher", methods=["POST"])
@admin_required
def set_form_teacher(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    teacher_id = request.form.get("teacher_id") or None
    sc.form_teacher_id = int(teacher_id) if teacher_id else None
    db.session.commit()
    flash("Form teacher updated.", "success")
    return redirect(url_for("admin.classes"))


# ------------------------------------------------------------- class subjects
@admin_bp.route("/classes/<int:class_id>/subjects", methods=["GET", "POST"])
@login_required
def class_subjects(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    _require_class_access(sc)

    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        new_subject_name = request.form.get("new_subject_name", "").strip()

        if new_subject_name:
            subj = Subject.query.filter_by(name=new_subject_name).first()
            if not subj:
                subj = Subject(name=new_subject_name)
                db.session.add(subj)
                db.session.flush()
            subject_id = subj.id

        if subject_id:
            subject_id = int(subject_id)
            exists = ClassSubject.query.filter_by(class_id=class_id, subject_id=subject_id).first()
            if exists:
                flash("That subject is already part of this class.", "warning")
            else:
                max_order = db.session.query(db.func.max(ClassSubject.order)) \
                    .filter_by(class_id=class_id).scalar() or 0
                db.session.add(ClassSubject(class_id=class_id, subject_id=subject_id,
                                             order=max_order + 1))
                db.session.commit()
                flash("Subject added to class.", "success")
        return redirect(url_for("admin.class_subjects", class_id=class_id))

    current_subjects = (ClassSubject.query.filter_by(class_id=class_id)
                         .order_by(ClassSubject.order).all())
    used_ids = {cs.subject_id for cs in current_subjects}
    available_subjects = Subject.query.filter(~Subject.id.in_(used_ids)).order_by(Subject.name).all()
    teachers = User.query.filter_by(role="teacher", active=True).order_by(User.name).all()
    assignments = {a.subject_id: a.teacher_id for a in
                   TeacherAssignment.query.filter_by(class_id=class_id).all()}
    return render_template("admin/class_subjects.html", sc=sc, current_subjects=current_subjects,
                            available_subjects=available_subjects, teachers=teachers,
                            assignments=assignments)


@admin_bp.route("/classes/<int:class_id>/subjects/<int:cs_id>/remove", methods=["POST"])
@login_required
def remove_class_subject(class_id, cs_id):
    sc = SchoolClass.query.get_or_404(class_id)
    _require_class_access(sc)
    cs = ClassSubject.query.get_or_404(cs_id)
    db.session.delete(cs)
    db.session.commit()
    flash("Subject removed from class.", "info")
    return redirect(url_for("admin.class_subjects", class_id=class_id))


@admin_bp.route("/classes/<int:class_id>/subjects/<int:subject_id>/assign", methods=["POST"])
@login_required
def assign_subject_teacher(class_id, subject_id):
    sc = SchoolClass.query.get_or_404(class_id)
    _require_class_access(sc)
    teacher_id = request.form.get("teacher_id") or None
    existing = TeacherAssignment.query.filter_by(class_id=class_id, subject_id=subject_id).first()
    if teacher_id:
        if existing:
            existing.teacher_id = int(teacher_id)
        else:
            db.session.add(TeacherAssignment(class_id=class_id, subject_id=subject_id,
                                              teacher_id=int(teacher_id)))
    elif existing:
        db.session.delete(existing)
    db.session.commit()
    flash("Teacher assignment updated.", "success")
    return redirect(url_for("admin.class_subjects", class_id=class_id))


# ------------------------------------------------------------------ subjects
@admin_bp.route("/subjects", methods=["GET", "POST"])
@admin_required
def subjects():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Subject name is required.", "danger")
        elif Subject.query.filter(db.func.lower(Subject.name) == name.lower()).first():
            flash(f"'{name}' already exists in the subject list.", "warning")
        else:
            db.session.add(Subject(name=name))
            db.session.commit()
            flash(f"'{name}' added to the school's subject list.", "success")
        return redirect(url_for("admin.subjects"))

    all_subjects = Subject.query.order_by(Subject.name).all()
    # for each subject, which classes currently offer it (for display + delete safety)
    usage = {}
    for subj in all_subjects:
        classes_using = (SchoolClass.query.join(ClassSubject)
                          .filter(ClassSubject.subject_id == subj.id)
                          .order_by(SchoolClass.name).all())
        usage[subj.id] = classes_using
    return render_template("admin/subjects.html", subjects=all_subjects, usage=usage)


@admin_bp.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@admin_required
def delete_subject(subject_id):
    subj = Subject.query.get_or_404(subject_id)
    in_use = ClassSubject.query.filter_by(subject_id=subject_id).first()
    if in_use:
        flash(f"Can't delete '{subj.name}' — it's still assigned to one or more classes. "
              f"Remove it from those classes first (Classes → Manage subjects).", "danger")
    else:
        db.session.delete(subj)
        db.session.commit()
        flash(f"'{subj.name}' removed from the school's subject list.", "info")
    return redirect(url_for("admin.subjects"))


@admin_bp.route("/subjects/<int:subject_id>/edit", methods=["POST"])
@admin_required
def edit_subject(subject_id):
    subj = Subject.query.get_or_404(subject_id)
    new_name = request.form.get("name", "").strip()
    if not new_name:
        flash("Subject name can't be empty.", "danger")
    elif Subject.query.filter(db.func.lower(Subject.name) == new_name.lower(),
                               Subject.id != subject_id).first():
        flash(f"'{new_name}' already exists in the subject list.", "warning")
    else:
        old_name = subj.name
        subj.name = new_name
        db.session.commit()
        flash(f"Renamed '{old_name}' to '{new_name}'. This updates it everywhere it's used "
              f"(class timetables, report cards, spreadsheets).", "success")
    return redirect(url_for("admin.subjects"))


# ------------------------------------------------------------------ teachers
@admin_bp.route("/teachers", methods=["GET", "POST"])
@admin_required
def teachers():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "teacher")
        if not name or not email or len(password) < 6:
            flash("Name, email, and a password of at least 6 characters are required.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("That email is already registered.", "danger")
        else:
            u = User(name=name, email=email, role=role)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f"Account created for {name}.", "success")
        return redirect(url_for("admin.teachers"))

    all_users = User.query.order_by(User.role.desc(), User.name).all()
    return render_template("admin/teachers.html", users=all_users)


@admin_bp.route("/teachers/<int:user_id>/edit", methods=["POST"])
@admin_required
def edit_teacher(user_id):
    u = User.query.get_or_404(user_id)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", u.role)
    new_password = request.form.get("password", "").strip()

    if not name or not email:
        flash("Name and email are required.", "danger")
        return redirect(url_for("admin.teachers"))

    existing = User.query.filter(db.func.lower(User.email) == email, User.id != user_id).first()
    if existing:
        flash("That email is already used by another account.", "danger")
        return redirect(url_for("admin.teachers"))

    if u.id == current_user.id and role != "admin":
        flash("You can't remove your own admin access.", "warning")
        return redirect(url_for("admin.teachers"))

    u.name = name
    u.email = email
    u.role = role
    if new_password:
        if len(new_password) < 6:
            flash("New password must be at least 6 characters. Other changes were saved, "
                  "but the password was left unchanged.", "warning")
        else:
            u.set_password(new_password)
    db.session.commit()
    flash(f"Updated details for {u.name}.", "success")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_teacher(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You can't deactivate your own account.", "warning")
    else:
        u.active = not u.active
        db.session.commit()
        flash(f"{u.name} is now {'active' if u.active else 'inactive'}.", "info")
    return redirect(url_for("admin.teachers"))


@admin_bp.route("/teachers/<int:user_id>/delete", methods=["POST"])
@admin_required
def delete_teacher(user_id):
    u = User.query.get_or_404(user_id)
    if u.id == current_user.id:
        flash("You can't delete your own account.", "warning")
    else:
        db.session.delete(u)
        db.session.commit()
        flash("Account deleted.", "info")
    return redirect(url_for("admin.teachers"))


# ------------------------------------------------------------------ students
@admin_bp.route("/classes/<int:class_id>/students", methods=["GET", "POST"])
@login_required
def students(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    _require_class_access(sc)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        sex = request.form.get("sex", "")
        roll_no = request.form.get("roll_no", "").strip()
        if not name:
            flash("Student name is required.", "danger")
        else:
            student = Student(class_id=class_id, name=name, sex=sex, roll_no=roll_no)
            photo_file = request.files.get("photo")
            if photo_file and photo_file.filename:
                try:
                    student.photo_path = save_image(photo_file, "students") or ""
                except ValueError as e:
                    flash(str(e), "danger")
                    return redirect(url_for("admin.students", class_id=class_id))
            db.session.add(student)
            db.session.commit()
            flash(f"{name} added to {sc.name}.", "success")
        return redirect(url_for("admin.students", class_id=class_id))

    class_students = Student.query.filter_by(class_id=class_id).order_by(Student.name).all()
    return render_template("admin/students.html", sc=sc, students=class_students)


@admin_bp.route("/students/<int:student_id>/edit", methods=["POST"])
@login_required
def edit_student(student_id):
    student = Student.query.get_or_404(student_id)
    sc = SchoolClass.query.get_or_404(student.class_id)
    _require_class_access(sc)
    name = request.form.get("name", "").strip()
    if not name:
        flash("Student name can't be empty.", "danger")
    else:
        student.name = name
        student.sex = request.form.get("sex", "")
        student.roll_no = request.form.get("roll_no", "").strip()
        db.session.commit()
        flash(f"Updated details for {student.name}.", "success")
    return redirect(url_for("admin.students", class_id=student.class_id))


@admin_bp.route("/students/<int:student_id>/photo", methods=["POST"])
@login_required
def update_student_photo(student_id):
    student = Student.query.get_or_404(student_id)
    sc = SchoolClass.query.get_or_404(student.class_id)
    _require_class_access(sc)
    photo_file = request.files.get("photo")
    if not photo_file or not photo_file.filename:
        flash("Please choose a photo to upload.", "warning")
        return redirect(url_for("admin.students", class_id=student.class_id))
    try:
        new_path = save_image(photo_file, "students")
    except ValueError as e:
        flash(str(e), "danger")
        return redirect(url_for("admin.students", class_id=student.class_id))
    if new_path:
        delete_image(student.photo_path)
        student.photo_path = new_path
        db.session.commit()
        flash(f"Photo updated for {student.name}.", "success")
    return redirect(url_for("admin.students", class_id=student.class_id))


@admin_bp.route("/students/<int:student_id>/photo/remove", methods=["POST"])
@login_required
def remove_student_photo(student_id):
    student = Student.query.get_or_404(student_id)
    sc = SchoolClass.query.get_or_404(student.class_id)
    _require_class_access(sc)
    delete_image(student.photo_path)
    student.photo_path = ""
    db.session.commit()
    flash(f"Photo removed for {student.name}.", "info")
    return redirect(url_for("admin.students", class_id=student.class_id))


@admin_bp.route("/students/<int:student_id>/delete", methods=["POST"])
@login_required
def delete_student(student_id):
    s = Student.query.get_or_404(student_id)
    sc = SchoolClass.query.get_or_404(s.class_id)
    _require_class_access(sc)
    class_id = s.class_id
    delete_image(s.photo_path)
    db.session.delete(s)
    db.session.commit()
    flash("Student removed.", "info")
    return redirect(url_for("admin.students", class_id=class_id))


@admin_bp.route("/students/bulk-add/<int:class_id>", methods=["POST"])
@login_required
def bulk_add_students(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    _require_class_access(sc)
    raw = request.form.get("names", "")
    count = 0
    for line in raw.splitlines():
        name = line.strip()
        if name:
            db.session.add(Student(class_id=class_id, name=name))
            count += 1
    db.session.commit()
    flash(f"Added {count} students to {sc.name}. Don't forget to fill in Sex and Roll No. "
          f"for each using the edit (pencil) icon.", "success")
    return redirect(url_for("admin.students", class_id=class_id))


# --------------------------------------------------------------------- grading
@admin_bp.route("/grading", methods=["GET", "POST"])
@admin_required
def grading():
    if request.method == "POST":
        try:
            mn = float(request.form["min_score"])
            mx = float(request.form["max_score"])
            grade = request.form["grade"].strip()
            remark = request.form.get("remark", "").strip()
        except (KeyError, ValueError):
            flash("Please provide valid numeric ranges.", "danger")
            return redirect(url_for("admin.grading"))
        db.session.add(GradeBand(min_score=mn, max_score=mx, grade=grade, remark=remark))
        db.session.commit()
        flash("Grade band added.", "success")
        return redirect(url_for("admin.grading"))

    bands = GradeBand.query.order_by(GradeBand.min_score.desc()).all()
    return render_template("admin/grading.html", bands=bands)


@admin_bp.route("/grading/<int:band_id>/delete", methods=["POST"])
@admin_required
def delete_grade_band(band_id):
    b = GradeBand.query.get_or_404(band_id)
    db.session.delete(b)
    db.session.commit()
    return redirect(url_for("admin.grading"))


# ----------------------------------------------------------------------- skills
@admin_bp.route("/skills", methods=["GET", "POST"])
@admin_required
def skills():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name and not Skill.query.filter_by(name=name).first():
            max_order = db.session.query(db.func.max(Skill.order)).scalar() or 0
            db.session.add(Skill(name=name, order=max_order + 1))
            db.session.commit()
            flash("Skill added.", "success")
        return redirect(url_for("admin.skills"))

    all_skills = Skill.query.order_by(Skill.order).all()
    return render_template("admin/skills.html", skills=all_skills)


@admin_bp.route("/skills/<int:skill_id>/delete", methods=["POST"])
@admin_required
def delete_skill(skill_id):
    s = Skill.query.get_or_404(skill_id)
    db.session.delete(s)
    db.session.commit()
    return redirect(url_for("admin.skills"))


# --------------------------------------------------------------------- settings
@admin_bp.route("/settings", methods=["GET", "POST"])
@admin_required
def settings():
    school = SchoolSettings.get()
    if request.method == "POST":
        school.name = request.form.get("name", school.name)
        school.address = request.form.get("address", school.address)
        school.phone = request.form.get("phone", school.phone)
        school.email = request.form.get("email", school.email)
        school.motto = request.form.get("motto", school.motto)
        school.current_term = request.form.get("current_term", school.current_term)
        school.current_session = request.form.get("current_session", school.current_session)
        school.term_ends = request.form.get("term_ends", school.term_ends)
        school.resumption_date = request.form.get("resumption_date", school.resumption_date)

        logo_file = request.files.get("logo")
        if logo_file and logo_file.filename:
            try:
                new_path = save_image(logo_file, "logos")
                if new_path:
                    delete_image(school.logo_path)
                    school.logo_path = new_path
            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("admin.settings"))

        if request.form.get("remove_logo") == "1":
            delete_image(school.logo_path)
            school.logo_path = ""

        db.session.commit()
        flash("School settings updated.", "success")
        return redirect(url_for("admin.settings"))
    return render_template("admin/settings.html", school=school)


@admin_bp.route("/backup")
@admin_required
def download_backup():
    buf, filename = build_backup_zip()
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/zip")
