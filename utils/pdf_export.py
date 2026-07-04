import io
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                 Spacer, PageBreak, Image)

from flask import current_app
from models import SchoolSettings, Skill
from utils.grading import compute_student_result
from utils.uploads import resolve_upload_path

styles = getSampleStyleSheet()
TITLE = ParagraphStyle("title", parent=styles["Heading2"], alignment=TA_CENTER, spaceAfter=2)
SUBTITLE = ParagraphStyle("subtitle", parent=styles["Normal"], alignment=TA_CENTER, fontSize=9)
INFO = ParagraphStyle("info", parent=styles["Normal"], fontSize=9, leading=13)
SECTION = ParagraphStyle("section", parent=styles["Heading4"], spaceBefore=5, spaceAfter=3, fontSize=10)
SMALL = ParagraphStyle("small", parent=styles["Normal"], fontSize=8.5, leading=11)


def _safe_image(relative_path, max_w, max_h):
    """Loads an image saved under instance/uploads/ for use in a PDF,
    preserving aspect ratio within max_w x max_h. Returns None if the
    path is empty or the file can't be read (never raises)."""
    if not relative_path:
        return None
    try:
        full_path = resolve_upload_path(relative_path)
        if not full_path or not os.path.exists(full_path):
            return None
        img = Image(full_path)
        ratio = min(max_w / img.imageWidth, max_h / img.imageHeight)
        img.drawWidth = img.imageWidth * ratio
        img.drawHeight = img.imageHeight * ratio
        return img
    except Exception:
        return None


def _header_flowables(school, school_class, student, term, session):
    title_block = []
    title_block.append(Paragraph(school.name.upper(), TITLE))
    if school.address:
        title_block.append(Paragraph(school.address, SUBTITLE))
    contact_line = " | ".join(x for x in [school.phone, school.email] if x)
    if contact_line:
        title_block.append(Paragraph(contact_line, SUBTITLE))
    if school.motto:
        title_block.append(Paragraph(school.motto, SUBTITLE))
    title_block.append(Paragraph(f"{term} Report Sheet for {session} Session", SUBTITLE))

    logo_img = _safe_image(school.logo_path, 60, 60)
    photo_img = _safe_image(student.photo_path, 60, 70)

    header_row = [
        logo_img if logo_img else "",
        title_block,
        photo_img if photo_img else "",
    ]
    header_table = Table([header_row], colWidths=[70, 370, 70])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
    ]))

    flow = [header_table, Spacer(1, 6)]

    info_rows = [
        [f"Name: {student.name}", f"Sex: {student.sex or '-'}", f"Class: {school_class.name}"],
        [f"No. on Roll: {student.roll_no or '-'}", f"Term Ends: {school.term_ends or '_____'}",
         f"Next Resumption: {school.resumption_date or '_____'}"],
    ]
    info_table = Table(info_rows, colWidths=[170, 160, 170])
    info_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    flow.append(info_table)
    flow.append(Spacer(1, 6))
    return flow


def _subjects_table(result):
    head = ["Subject", "Test", "Exam", "Total", "Avg", "Position", "Grade", "Remark"]
    data = [head]
    for cs_id, sub in result["subjects"].items():
        data.append([
            sub["subject"], sub["test"], sub["exam"], sub["total"],
            sub["average"], sub["position"], sub["grade"], sub["remark"],
        ])
    t = Table(data, colWidths=[110, 35, 35, 38, 38, 48, 38, 75], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F6FA")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _summary_table(result):
    data = [[
        f"Grand Total: {result['grand_total']}/{result['max_total']}",
        f"Percentage: {result['percentage']}%",
        f"Overall Position: {result['overall_position']} of {result.get('class_size', '-')}",
    ]]
    t = Table(data, colWidths=[170, 160, 170])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF2CC")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def _skills_table(student, term, session):
    skills = Skill.query.order_by(Skill.order).all()
    if not skills:
        return None
    ratings = {sr.skill_id: sr.rating for sr in student.skill_ratings
               if sr.term == term and sr.session == session}
    rows = []
    pair = []
    for sk in skills:
        pair.append((sk.name, ratings.get(sk.id, "-")))
        if len(pair) == 3:
            rows.append(pair)
            pair = []
    if pair:
        while len(pair) < 3:
            pair.append(("", ""))
        rows.append(pair)

    data = [["Skill", "Rating", "Skill", "Rating", "Skill", "Rating"]]
    for row in rows:
        data.append([row[0][0], row[0][1], row[1][0], row[1][1], row[2][0], row[2][1]])
    t = Table(data, colWidths=[95, 38, 95, 38, 95, 38])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
        ("ALIGN", (5, 0), (5, -1), "CENTER"),
    ]))
    return t


def build_student_pdf(school_class, student, term, session):
    school = SchoolSettings.get()
    result = compute_student_result(school_class, student, term, session)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             topMargin=10 * mm, bottomMargin=10 * mm,
                             leftMargin=14 * mm, rightMargin=14 * mm)
    flow = []
    flow += _header_flowables(school, school_class, student, term, session)
    flow.append(_subjects_table(result))
    flow.append(Spacer(1, 6))
    flow.append(_summary_table(result))
    flow.append(Spacer(1, 4))
    flow.append(Paragraph(
        f"Attendance: {student.attendance_present or 0} out of {student.attendance_total or 0}",
        SMALL))

    skills_table = _skills_table(student, term, session)
    if skills_table:
        flow.append(Paragraph("Affective / Psychomotor Skills", SECTION))
        flow.append(skills_table)

    flow.append(Spacer(1, 6))
    remarks_data = [[
        Paragraph(f"<b>Teacher's Remark:</b><br/>{student.teacher_remark or '-'}", SMALL),
        Paragraph(f"<b>Principal's Remark:</b><br/>{student.principal_remark or '-'}", SMALL),
    ]]
    rt = Table(remarks_data, colWidths=[250, 250])
    rt.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    flow.append(rt)

    doc.build(flow)
    buf.seek(0)
    return buf


def build_class_pdfs(school_class, term, session):
    """Builds one multi-page PDF containing every student's report card."""
    from models import Student
    school = SchoolSettings.get()
    students = Student.query.filter_by(class_id=school_class.id).order_by(Student.name).all()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                             topMargin=10 * mm, bottomMargin=10 * mm,
                             leftMargin=14 * mm, rightMargin=14 * mm)
    flow = []
    for idx, student in enumerate(students):
        result = compute_student_result(school_class, student, term, session)
        flow += _header_flowables(school, school_class, student, term, session)
        flow.append(_subjects_table(result))
        flow.append(Spacer(1, 6))
        flow.append(_summary_table(result))
        skills_table = _skills_table(student, term, session)
        if skills_table:
            flow.append(Spacer(1, 4))
            flow.append(Paragraph("Affective / Psychomotor Skills", SECTION))
            flow.append(skills_table)
        if idx < len(students) - 1:
            flow.append(PageBreak())

    doc.build(flow)
    buf.seek(0)
    return buf
