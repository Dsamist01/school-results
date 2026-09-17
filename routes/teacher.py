from flask import (Blueprint, render_template, redirect, url_for, request, flash, abort,
                    send_file)
from flask_login import login_required, current_user

from extensions import db
from models import (TeacherAssignment, ClassSubject, Student, Score, SchoolClass,
                     SchoolSettings, Skill, SkillRating)
from utils.xlsx_export import build_score_import_template
from utils.bulk_import import parse_score_file, match_students
from utils.grading import compute_student_result

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.route("/")
@login_required
def dashboard():
    if current_user.is_admin():
        assignments = (TeacherAssignment.query.all())
    else:
        assignments = TeacherAssignment.query.filter_by(teacher_id=current_user.id).all()
    form_classes = current_user.class_teacher_of if not current_user.is_admin() else \
        SchoolClass.query.all()

    # For each class a person is the form teacher of, also surface every subject in that
    # class as enterable (form teachers can enter all subjects for their own class).
    form_class_subjects = {}
    for c in form_classes:
        form_class_subjects[c.id] = (ClassSubject.query.filter_by(class_id=c.id)
                                      .order_by(ClassSubject.order).all())

    return render_template("teacher/dashboard.html", assignments=assignments,
                            form_classes=form_classes, form_class_subjects=form_class_subjects)


def _check_access(class_id, subject_id):
    if current_user.is_admin():
        return
    ok = TeacherAssignment.query.filter_by(
        teacher_id=current_user.id, class_id=class_id, subject_id=subject_id).first()
    if ok:
        return
    sc = SchoolClass.query.get(class_id)
    if sc and sc.form_teacher_id == current_user.id:
        return
    abort(403)


@teacher_bp.route("/scores/<int:class_id>/<int:subject_id>", methods=["GET", "POST"])
@login_required
def enter_scores(class_id, subject_id):
    _check_access(class_id, subject_id)
    sc = SchoolClass.query.get_or_404(class_id)
    cs = ClassSubject.query.filter_by(class_id=class_id, subject_id=subject_id).first_or_404()
    school = SchoolSettings.get()
    term, session = school.current_term, school.current_session

    students = Student.query.filter_by(class_id=class_id).order_by(Student.name).all()
    existing = {s.student_id: s for s in
                Score.query.filter_by(class_subject_id=cs.id, term=term, session=session).all()}

    if request.method == "POST":
        for student in students:
            test_raw = request.form.get(f"test_{student.id}", "").strip()
            exam_raw = request.form.get(f"exam_{student.id}", "").strip()
            test = float(test_raw) if test_raw else 0
            exam = float(exam_raw) if exam_raw else 0
            if test > 40 or exam > 60 or test < 0 or exam < 0:
                flash(f"Score out of range for {student.name} (Test max 40, Exam max 60). Row skipped.",
                      "danger")
                continue
            score = existing.get(student.id)
            if score:
                score.test, score.exam = test, exam
            else:
                db.session.add(Score(student_id=student.id, class_subject_id=cs.id,
                                      term=term, session=session, test=test, exam=exam))
        db.session.commit()
        flash("Scores saved.", "success")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, subject_id=subject_id))

    rows = []
    for student in students:
        sc_obj = existing.get(student.id)
        rows.append({"student": student, "test": sc_obj.test if sc_obj else "",
                     "exam": sc_obj.exam if sc_obj else ""})

    return render_template("teacher/enter_scores.html", sc=sc, subject=cs.subject, rows=rows,
                            term=term, session=session)


@teacher_bp.route("/scores/<int:class_id>/<int:subject_id>/template")
@login_required
def download_score_template(class_id, subject_id):
    _check_access(class_id, subject_id)
    sc = SchoolClass.query.get_or_404(class_id)
    cs = ClassSubject.query.filter_by(class_id=class_id, subject_id=subject_id).first_or_404()
    school = SchoolSettings.get()
    term, session = school.current_term, school.current_session

    students = Student.query.filter_by(class_id=class_id).order_by(Student.name).all()
    existing = {s.student_id: s for s in
                Score.query.filter_by(class_subject_id=cs.id, term=term, session=session).all()}

    buf = build_score_import_template(sc, cs.subject, students, existing, term, session)
    filename = f"{sc.name}_{cs.subject.name}_score_template.xlsx".replace(" ", "_")
    return send_file(buf, as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@teacher_bp.route("/scores/<int:class_id>/<int:subject_id>/import", methods=["POST"])
@login_required
def import_scores(class_id, subject_id):
    _check_access(class_id, subject_id)
    sc = SchoolClass.query.get_or_404(class_id)
    cs = ClassSubject.query.filter_by(class_id=class_id, subject_id=subject_id).first_or_404()
    school = SchoolSettings.get()
    term, session = school.current_term, school.current_session

    file = request.files.get("score_file")
    if not file or not file.filename:
        flash("Please choose a file to upload.", "danger")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, subject_id=subject_id))
    if not file.filename.lower().endswith((".xlsx", ".csv")):
        flash("Please upload an .xlsx or .csv file.", "danger")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, subject_id=subject_id))

    try:
        parsed = parse_score_file(file)
    except Exception:
        flash("Couldn't read that file. Make sure it has Name, Test, and Exam columns.", "danger")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, subject_id=subject_id))

    students = Student.query.filter_by(class_id=class_id).order_by(Student.name).all()
    matched, unmatched_rows, no_row_students = match_students(students, parsed)

    if not matched:
        flash("No student names in the file matched this class. Check spelling and try again, "
              "or download the template to make sure names match exactly.", "danger")
        return redirect(url_for("teacher.enter_scores", class_id=class_id, subject_id=subject_id))

    existing = {s.student_id: s for s in
                Score.query.filter_by(class_subject_id=cs.id, term=term, session=session).all()}

    rows = []
    fuzzy_count = 0
    for student in students:
        m = matched.get(student.id)
        if m:
            if not m["exact"]:
                fuzzy_count += 1
            rows.append({"student": student, "test": m["test"], "exam": m["exam"],
                         "imported": True, "fuzzy": not m["exact"]})
        else:
            sc_obj = existing.get(student.id)
            rows.append({"student": student, "test": sc_obj.test if sc_obj else "",
                         "exam": sc_obj.exam if sc_obj else "", "imported": False, "fuzzy": False})

    flash(f"Imported {len(matched)} of {len(students)} students from your file. "
          f"Review the values below, then click Save Scores to confirm.", "success")
    if fuzzy_count:
        flash(f"{fuzzy_count} name(s) were matched by closest spelling, not an exact match — "
              f"please double-check those rows.", "warning")
    if unmatched_rows:
        names = ", ".join(r["name"] for r in unmatched_rows[:10])
        flash(f"{len(unmatched_rows)} name(s) in your file didn't match anyone in this class: "
              f"{names}", "warning")
    if no_row_students:
        names = ", ".join(s.name for s in no_row_students[:10])
        flash(f"{len(no_row_students)} student(s) in this class had no row in your file: {names}",
              "warning")

    return render_template("teacher/enter_scores.html", sc=sc, subject=cs.subject, rows=rows,
                            term=term, session=session, import_preview=True)


@teacher_bp.route("/class/<int:class_id>/remarks", methods=["GET", "POST"])
@login_required
def class_remarks(class_id):
    sc = SchoolClass.query.get_or_404(class_id)
    if not current_user.is_admin() and sc.form_teacher_id != current_user.id:
        abort(403)
    school = SchoolSettings.get()
    term, session = school.current_term, school.current_session
    students = Student.query.filter_by(class_id=class_id).order_by(Student.name).all()
    skills = Skill.query.order_by(Skill.order).all()

    if request.method == "POST":
        student_id = int(request.form["student_id"])
        student = Student.query.get_or_404(student_id)
        
        # Attendance & Teacher Remark (editable by both Admin and Form Teacher)
        student.attendance_present = int(request.form.get("attendance_present") or 0)
        student.attendance_total = int(request.form.get("attendance_total") or 0)
        student.teacher_remark = request.form.get("teacher_remark", "")
        
        # Principal Remark (only editable by Admin)
        if current_user.is_admin():
            student.principal_remark = request.form.get("principal_remark", student.principal_remark)
            
        # Skill Ratings (editable by both Admin and Form Teacher)
        for sk in skills:
            rating_raw = request.form.get(f"skill_{sk.id}", "").strip()
            if rating_raw:
                rating = max(1, min(5, int(rating_raw)))
                sr = SkillRating.query.filter_by(student_id=student_id, skill_id=sk.id,
                                                  term=term, session=session).first()
                if sr:
                    sr.rating = rating
                else:
                    db.session.add(SkillRating(student_id=student_id, skill_id=sk.id,
                                                term=term, session=session, rating=rating))

        db.session.commit()
        flash(f"Remarks and skills saved for {student.name}.", "success")
        return redirect(url_for("teacher.class_remarks", class_id=class_id))

    ratings_map = {}
    for s in students:
        ratings_map[s.id] = {r.skill_id: r.rating for r in s.skill_ratings
                              if r.term == term and r.session == session}

    selected_id = request.args.get("student_id", type=int)
    selected_student = next((s for s in students if s.id == selected_id), None) if selected_id else None
    
    student_result_data = None
    if selected_student:
        student_result_data = compute_student_result(sc, selected_student, term, session)

    return render_template("teacher/class_remarks.html", sc=sc, students=students, skills=skills,
                            ratings_map=ratings_map, term=term, session=session,
                            selected_student=selected_student, student_result=student_result_data)