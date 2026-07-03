"""Core computation logic: totals, class averages, subject positions,
grades, and overall positions for a class in a given term/session."""

from models import Student, Score, ClassSubject, GradeBand


def ordinal(n):
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def compute_class_results(school_class, term, session):
    """Returns a structured dict with every student's per-subject and
    overall results for the given class/term/session, fully computed
    (totals, class subject averages, subject positions, grades, overall
    position)."""
    class_subjects = (ClassSubject.query
                       .filter_by(class_id=school_class.id)
                       .order_by(ClassSubject.order)
                       .all())
    students = (Student.query
                .filter_by(class_id=school_class.id)
                .order_by(Student.name)
                .all())

    # Pull every score for this class/term/session in one go.
    cs_ids = [cs.id for cs in class_subjects]
    scores = (Score.query
              .filter(Score.class_subject_id.in_(cs_ids))
              .filter_by(term=term, session=session)
              .all() if cs_ids else [])

    # score_map[student_id][class_subject_id] = Score
    score_map = {}
    for sc in scores:
        score_map.setdefault(sc.student_id, {})[sc.class_subject_id] = sc

    # Per-subject: collect totals (only for students who have an entered score)
    # to compute class average and rank/position.
    subject_totals = {cs.id: [] for cs in class_subjects}  # cs_id -> [(student_id, total)]
    for student in students:
        srow = score_map.get(student.id, {})
        for cs in class_subjects:
            sc = srow.get(cs.id)
            if sc is not None and (sc.test or sc.exam):
                subject_totals[cs.id].append((student.id, sc.total))

    subject_average = {}
    subject_position = {}  # cs_id -> {student_id: position_int}
    for cs in class_subjects:
        entries = subject_totals[cs.id]
        if entries:
            avg = sum(t for _, t in entries) / len(entries)
        else:
            avg = 0
        subject_average[cs.id] = avg

        ranked = sorted(entries, key=lambda e: e[1], reverse=True)
        pos_map = {}
        prev_score, prev_rank = None, 0
        for idx, (sid, total) in enumerate(ranked, start=1):
            if total == prev_score:
                pos_map[sid] = prev_rank
            else:
                pos_map[sid] = idx
                prev_rank = idx
                prev_score = total
        subject_position[cs.id] = pos_map

    # Build per-student rows
    student_rows = []
    grand_totals = []
    for student in students:
        srow = score_map.get(student.id, {})
        subject_results = {}
        grand_total = 0
        subjects_with_scores = 0
        for cs in class_subjects:
            sc = srow.get(cs.id)
            test = sc.test if sc else 0
            exam = sc.exam if sc else 0
            total = (test or 0) + (exam or 0)
            grade, remark = GradeBand.grade_for(total)
            position = subject_position[cs.id].get(student.id)
            subject_results[cs.id] = {
                "subject": cs.subject.name,
                "test": test,
                "exam": exam,
                "total": total,
                "average": round(subject_average[cs.id], 1),
                "position": ordinal(position) if position else "-",
                "grade": grade if (sc is not None) else "-",
                "remark": remark if (sc is not None) else "-",
            }
            if sc is not None and (sc.test or sc.exam):
                grand_total += total
                subjects_with_scores += 1
        percentage = (grand_total / (len(class_subjects) * 100) * 100) if class_subjects else 0
        student_rows.append({
            "student": student,
            "subjects": subject_results,
            "grand_total": grand_total,
            "max_total": len(class_subjects) * 100,
            "percentage": round(percentage, 1),
            "subjects_with_scores": subjects_with_scores,
        })
        grand_totals.append((student.id, grand_total))

    # Overall position based on grand total (only meaningful once scores exist)
    ranked_overall = sorted(grand_totals, key=lambda e: e[1], reverse=True)
    overall_pos_map = {}
    prev_score, prev_rank = None, 0
    for idx, (sid, total) in enumerate(ranked_overall, start=1):
        if total == prev_score:
            overall_pos_map[sid] = prev_rank
        else:
            overall_pos_map[sid] = idx
            prev_rank = idx
            prev_score = total
    for row in student_rows:
        row["overall_position"] = ordinal(overall_pos_map.get(row["student"].id, len(students)))

    return {
        "class_subjects": class_subjects,
        "students": student_rows,
        "class_size": len(students),
    }


def compute_student_result(school_class, student, term, session):
    """Convenience wrapper: full class results filtered down to one student."""
    full = compute_class_results(school_class, term, session)
    for row in full["students"]:
        if row["student"].id == student.id:
            row["class_size"] = full["class_size"]
            return row
    return None
