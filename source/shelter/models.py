"""Relational entities. Business transactions live in services.py."""

from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(15), nullable=False, default="adopter")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (db.CheckConstraint("role IN ('adopter','staff')", name="valid_role"),)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Animal(db.Model):
    __tablename__ = "animals"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    species = db.Column(db.String(15), nullable=False)
    breed = db.Column(db.String(80), nullable=False)
    age_months = db.Column(db.Integer, nullable=False)
    sex = db.Column(db.String(10), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(15), nullable=False, default="available")
    version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (
        db.CheckConstraint("species IN ('Dog','Cat','Rabbit')", name="valid_species"),
        db.CheckConstraint("sex IN ('Female','Male','Unknown')", name="valid_sex"),
        db.CheckConstraint(
            "status IN ('available','pending','adopted')", name="animal_status"
        ),
        db.CheckConstraint("age_months BETWEEN 0 AND 600", name="valid_age"),
    )

    def is_available(self):
        return self.status == "available"

    @property
    def age_label(self):
        return (
            f"{self.age_months} months"
            if self.age_months < 24
            else f"{self.age_months // 12} years"
        )


class AdoptionApplication(db.Model):
    __tablename__ = "applications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id"), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    housing = db.Column(db.String(30), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(15), nullable=False, default="pending")
    review_note = db.Column(db.Text, nullable=False, default="")
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    version = db.Column(db.Integer, nullable=False, default=1)
    user = db.relationship(User, foreign_keys=[user_id])
    animal = db.relationship(Animal)
    reviewer = db.relationship(User, foreign_keys=[reviewer_id])
    __table_args__ = (
        db.UniqueConstraint("user_id", "animal_id", name="one_application_per_animal"),
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','completed')",
            name="application_status",
        ),
    )

    def can_review(self):
        return self.status == "pending"


class MedicalRecord(db.Model):
    __tablename__ = "medical_records"
    id = db.Column(db.Integer, primary_key=True)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False)
    kind = db.Column(db.String(40), nullable=False)
    notes = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    animal = db.relationship(Animal)
    staff = db.relationship(User)


class Appointment(db.Model):
    __tablename__ = "appointments"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    # A NULL active_slot releases the slot when an appointment is cancelled.
    active_slot = db.Column(db.String(16), unique=True)
    status = db.Column(db.String(15), nullable=False, default="scheduled")
    notes = db.Column(db.String(500), nullable=False, default="")
    version = db.Column(db.Integer, nullable=False, default=1)
    application = db.relationship(AdoptionApplication)
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('scheduled','cancelled')", name="appointment_status"
        ),
    )


class Adoption(db.Model):
    __tablename__ = "adoptions"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(
        db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False
    )
    animal_id = db.Column(
        db.Integer, db.ForeignKey("animals.id"), unique=True, nullable=False
    )
    adopter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    staff_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    adopted_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    application = db.relationship(AdoptionApplication)
    animal = db.relationship(Animal)
    adopter = db.relationship(User, foreign_keys=[adopter_id])
    staff = db.relationship(User, foreign_keys=[staff_id])


class AuditEvent(db.Model):
    __tablename__ = "audit_events"
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    action = db.Column(db.String(40), nullable=False)
    note = db.Column(db.String(1000), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    actor = db.relationship(User)
