from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db


class User(UserMixin, db.Model):
    """Admin or Teacher account."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="teacher")  # 'admin' or 'teacher'
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    assignments = db.relationship("TeacherAssignment", backref="teacher", lazy=True,
                                   cascade="all, delete-orphan")
    class_teacher_of = db.relationship("SchoolClass", backref="form_teacher", lazy=True,
                                        foreign_keys="SchoolClass.form_teacher_id")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def is_admin(self):
        return self.role == "admin"


class SchoolSettings(db.Model):
    """Singleton-style table holding school identity & current term info."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), default="Your School Name")
    address = db.Column(db.String(255), default="")
    phone = db.Column(db.String(100), default="")
    email = db.Column(db.String(150), default="")
    motto = db.Column(db.String(150), default="")
    logo_path = db.Column(db.String(255), default="")
    current_term = db.Column(db.String(50), default="1st Term")
    current_session = db.Column(db.String(20), default="2025/2026")
    resumption_date = db.Column(db.String(50), default="")

    @staticmethod
    def get():
        s = SchoolSettings.query.first()
        if not s:
            s = SchoolSettings()
            db.session.add(s)
            db.session.commit()
        return s


class SchoolClass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)  # e.g. "Basic 4"
    form_teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)

    students = db.relationship("Student", backref="school_class", lazy=True,
                                cascade="all, delete-orphan")
    class_subjects = db.relationship("ClassSubject", backref="school_class", lazy=True,
                                      cascade="all, delete-orphan")


class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)


class ClassSubject(db.Model):
    """A subject offered within a specific class (subjects vary per class)."""
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)
    order = db.Column(db.Integer, default=0)  # display order on report card

    subject = db.relationship("Subject")
    scores = db.relationship("Score", backref="class_subject", lazy=True,
                              cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("class_id", "subject_id", name="uq_class_subject"),)


class TeacherAssignment(db.Model):
    """Which teacher enters scores for which class+subject."""
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subject.id"), nullable=False)

    school_class = db.relationship("SchoolClass")
    subject = db.relationship("Subject")

    __table_args__ = (db.UniqueConstraint("teacher_id", "class_id", "subject_id",
                                           name="uq_teacher_class_subject"),)


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey("school_class.id"), nullable=False)
    name = db.Column(db.String(150), nullable=False)
    sex = db.Column(db.String(10), default="")
    roll_no = db.Column(db.String(20), default="")
    photo_path = db.Column(db.String(255), default="")
    fees_balance = db.Column(db.String(50), default="")
    next_fees = db.Column(db.String(50), default="")
    attendance_present = db.Column(db.Integer, default=0)
    attendance_total = db.Column(db.Integer, default=0)
    teacher_remark = db.Column(db.Text, default="")
    principal_remark = db.Column(db.Text, default="")

    scores = db.relationship("Score", backref="student", lazy=True, cascade="all, delete-orphan")
    skill_ratings = db.relationship("SkillRating", backref="student", lazy=True,
                                     cascade="all, delete-orphan")


class Score(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    class_subject_id = db.Column(db.Integer, db.ForeignKey("class_subject.id"), nullable=False)
    term = db.Column(db.String(50), nullable=False)
    session = db.Column(db.String(20), nullable=False)
    test = db.Column(db.Float, default=0)   # out of 40
    exam = db.Column(db.Float, default=0)   # out of 60

    __table_args__ = (db.UniqueConstraint("student_id", "class_subject_id", "term", "session",
                                           name="uq_score_unique"),)

    @property
    def total(self):
        return (self.test or 0) + (self.exam or 0)


class Skill(db.Model):
    """Configurable list of affective/psychomotor skills rated on each report card."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    order = db.Column(db.Integer, default=0)


class SkillRating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("student.id"), nullable=False)
    skill_id = db.Column(db.Integer, db.ForeignKey("skill.id"), nullable=False)
    term = db.Column(db.String(50), nullable=False)
    session = db.Column(db.String(20), nullable=False)
    rating = db.Column(db.Integer, default=0)  # 1-5 scale

    skill = db.relationship("Skill")

    __table_args__ = (db.UniqueConstraint("student_id", "skill_id", "term", "session",
                                           name="uq_skill_rating_unique"),)


class GradeBand(db.Model):
    """Configurable grading scale, e.g. 90-100 = A+, Outstanding."""
    id = db.Column(db.Integer, primary_key=True)
    min_score = db.Column(db.Float, nullable=False)
    max_score = db.Column(db.Float, nullable=False)
    grade = db.Column(db.String(10), nullable=False)
    remark = db.Column(db.String(50), default="")

    @staticmethod
    def grade_for(total):
        bands = GradeBand.query.order_by(GradeBand.min_score.desc()).all()
        for b in bands:
            if b.min_score <= total <= b.max_score:
                return b.grade, b.remark
        return "F", "Fail"
