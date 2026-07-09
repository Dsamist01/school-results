from flask import Blueprint, render_template, redirect, url_for, request, abort, send_file
from flask_login import login_required, current_user

from models import SchoolClass, Student, SchoolSettings, TeacherAssignment
from utils.grading import compute_class_results, compute_student_result
from utils.xlsx_export import build_class_workbook
from utils.pdf_export import build_student_pdf, build_class_pdfs

results_bp = Blueprint("results", __name__)


def _check_class_access(class_id):
    if current_user.is_admin():
        return
    sc = SchoolClass.query.get_or_404(class_id)
    is_form_teacher = sc.form_teacher_id == current_user.id
    is_assigned = TeacherAssignment.query.filter_by(
        teacher_id=current_user.id, class_id=class_id).first() is not None
    if not (is_form_teacher or is_assigned):
        abort(403)


@results_bp.route("/class/<int:class_id>")
@login_required
def class_results(class_id):
    _check_class_access(class_id)
    sc = SchoolClass.query.get_or_404(class_id)
    school = SchoolSettings.get()
    data = compute_class_results(sc, school.current_term, school.current_session)
    return render_template("results/class_results.html", sc=sc, data=data,
                            term=school.current_term, session=school.current_session)


@results_bp.route("/class/<int:class_id>/export/xlsx")
@login_required
def export_class_xlsx(class_id):
    # Only admins can export Excel spreadsheets
    if not current_user.is_admin():
        abort(403)
        
    sc = SchoolClass.query.get_or_404(class_id)
    school = SchoolSettings.get()
    buf = build_class_workbook(sc, school.current_term, school.current_session, school.name)
    filename = f"{sc.name}_{school.current_term}_{school.current_session}.xlsx".replace(" ", "_")
    return send_file(buf, as_attachment=True, download_name=filename,
                      mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@results_bp.route("/class/<int:class_id>/export/pdf")
@login_required
def export_class_pdf(class_id):
    # Only admins can export bulk PDF report packs
    if not current_user.is_admin():
        abort(403)
        
    sc = SchoolClass.query.get_or_404(class_id)
    school = SchoolSettings.get()
    buf = build_class_pdfs(sc, school.current_term, school.current_session)
    filename = f"{sc.name}_ReportCards_{school.current_term}_{school.current_session}.pdf".replace(" ", "_")
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")


@results_bp.route("/student/<int:student_id>")
@login_required
def student_result(student_id):
    student = Student.query.get_or_404(student_id)
    _check_class_access(student.class_id)
    sc = SchoolClass.query.get_or_404(student.class_id)
    school = SchoolSettings.get()
    result = compute_student_result(sc, student, school.current_term, school.current_session)
    return render_template("results/student_result.html", sc=sc, student=student, result=result,
                            term=school.current_term, session=school.current_session)


@results_bp.route("/student/<int:student_id>/export/pdf")
@login_required
def export_student_pdf(student_id):
    # Only admins can export standalone report card PDFs
    if not current_user.is_admin():
        abort(403)
        
    student = Student.query.get_or_404(student_id)
    sc = SchoolClass.query.get_or_404(student.class_id)
    school = SchoolSettings.get()
    buf = build_student_pdf(sc, student, school.current_term, school.current_session)
    filename = f"{student.name}_{school.current_term}_{school.current_session}.pdf".replace(" ", "_")
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")