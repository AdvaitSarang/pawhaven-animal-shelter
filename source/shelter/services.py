"""Use-case services: authorize, validate, change related records, commit once."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import update
from .models import (
    db,
    User,
    Animal,
    AdoptionApplication,
    MedicalRecord,
    Appointment,
    Adoption,
    AuditEvent,
    utcnow,
)


class DomainError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def text(value, label, maximum=1000, minimum=1):
    value = str(value or "").strip()
    if not minimum <= len(value) <= maximum:
        raise DomainError(f"{label} must contain {minimum}–{maximum} characters.")
    return value


def number(value, label, minimum=0, maximum=1000000):
    if not re.fullmatch(r"\d+", str(value) if value is not None else ""):
        raise DomainError(f"{label} must be a whole number.")
    result = int(value)
    if not minimum <= result <= maximum:
        raise DomainError(f"{label} must be between {minimum} and {maximum}.")
    return result


def require_role(user, role):
    if user is None or user.role != role:
        raise DomainError("You do not have permission for this action.", 403)


def get(model, id_):
    result = db.session.get(model, id_)
    if result is None:
        raise DomainError("That record was not found.", 404)
    return result


def changed(result):
    if result.rowcount != 1:
        raise DomainError("This record changed. Reload the page and try again.", 409)


class AdoptionPolicy:
    @staticmethod
    def validate_submission(user, animal):
        require_role(user, "adopter")
        if not animal.is_available():
            raise DomainError("This animal is no longer available for applications.", 409)

    @staticmethod
    def validate_decision(application, decision):
        if decision not in ("approved", "rejected"):
            raise DomainError("Choose approve or reject.")
        if not application.can_review():
            raise DomainError("Only a pending application can be reviewed.", 409)


class AppointmentPolicy:
    @staticmethod
    def parse_slot(value):
        try:
            value = str(value)
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", value):
                raise ValueError()
            start = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        except ValueError:
            raise DomainError("Choose a valid appointment date and time.")
        now = datetime.now(ZoneInfo("America/Chicago")).replace(tzinfo=None)
        if not now < start <= now + timedelta(days=180):
            raise DomainError("Appointments must be in the next 180 days.")
        if start.minute not in (0, 30) or not 10 <= start.hour < 17:
            raise DomainError(
                "Choose a half-hour slot from 10:00 AM to 4:30 PM, shelter time."
            )
        return start


class ShelterService:
    def __init__(self, actor):
        self.actor = actor

    @staticmethod
    def register(data, role="adopter"):
        name = text(data.get("name"), "Name", 100)
        email = text(data.get("email"), "Email", 180).lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise DomainError("Enter a valid email address.")
        password = str(data.get("password", ""))
        if not 10 <= len(password) <= 128:
            raise DomainError("Use a password containing 10–128 characters.")
        if User.query.filter_by(email=email).first():
            raise DomainError("That email is already registered.", 409)
        if role not in ("adopter", "staff"):
            raise DomainError("Invalid account role.")
        user = User(name=name, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return user

    def animal_data(self, data):
        species, sex = data.get("species"), data.get("sex")
        if species not in ("Dog", "Cat", "Rabbit") or sex not in (
            "Female",
            "Male",
            "Unknown",
        ):
            raise DomainError("Choose a valid species and sex.")
        return dict(
            name=text(data.get("name"), "Name", 80),
            species=species,
            breed=text(data.get("breed"), "Breed", 80),
            sex=sex,
            age_months=number(data.get("age_months"), "Age in months", 0, 600),
            description=text(data.get("description"), "Description", 3000),
        )

    def save_animal(self, data, animal_id=None):
        require_role(self.actor, "staff")
        fields = self.animal_data(data)
        if animal_id:
            animal = get(Animal, animal_id)
            version = number(data.get("version"), "Version", 1)
            changed(
                db.session.execute(
                    update(Animal)
                    .where(Animal.id == animal.id, Animal.version == version)
                    .values(**fields, version=Animal.version + 1)
                )
            )
        else:
            animal = Animal(**fields)
            db.session.add(animal)
        db.session.commit()
        return animal

    def submit_application(self, animal_id, data):
        animal = get(Animal, animal_id)
        AdoptionPolicy.validate_submission(self.actor, animal)
        phone = text(data.get("phone"), "Phone", 30, 7)
        if not re.fullmatch(r"[0-9+(). -]+", phone):
            raise DomainError("Enter a valid contact phone.")
        housing = data.get("housing")
        if housing not in ("Own home", "Rent with permission", "Other approved housing"):
            raise DomainError("Choose your housing arrangement.")
        reason = text(data.get("reason"), "Adoption plan", 2000, 20)
        if AdoptionApplication.query.filter_by(
            user_id=self.actor.id, animal_id=animal_id
        ).first():
            raise DomainError("You already have an application for this animal.", 409)
        # The conditional write locks eligibility until the transaction finishes.
        changed(
            db.session.execute(
                update(Animal)
                .where(
                    Animal.id == animal_id,
                    Animal.status == "available",
                    Animal.version == animal.version,
                )
                .values(version=Animal.version + 1)
            )
        )
        application = AdoptionApplication(
            user_id=self.actor.id,
            animal_id=animal_id,
            phone=phone,
            housing=housing,
            reason=reason,
        )
        db.session.add(application)
        db.session.flush()  # Obtain its ID before inserting the linked event.
        db.session.add(
            AuditEvent(
                application_id=application.id,
                actor_id=self.actor.id,
                action="submitted",
                note="Application submitted for staff review.",
            )
        )
        db.session.commit()
        return application

    def review_application(self, application_id, data):
        require_role(self.actor, "staff")
        application = get(AdoptionApplication, application_id)
        decision = data.get("decision")
        AdoptionPolicy.validate_decision(application, decision)
        version = number(data.get("version"), "Version", 1)
        note = text(data.get("note"), "Review note", 1000, 3)
        # Reservation takes the animal lock before the application lock.
        if decision == "approved":
            changed(
                db.session.execute(
                    update(Animal)
                    .where(Animal.id == application.animal_id, Animal.status == "available")
                    .values(status="pending", version=Animal.version + 1)
                )
            )
        changed(
            db.session.execute(
                update(AdoptionApplication)
                .where(
                    AdoptionApplication.id == application_id,
                    AdoptionApplication.status == "pending",
                    AdoptionApplication.version == version,
                )
                .values(
                    status=decision,
                    review_note=note,
                    reviewer_id=self.actor.id,
                    reviewed_at=utcnow(),
                    version=AdoptionApplication.version + 1,
                )
            )
        )
        db.session.add(
            AuditEvent(
                application_id=application_id,
                actor_id=self.actor.id,
                action=decision,
                note=note,
            )
        )
        if decision == "approved":
            others = AdoptionApplication.query.filter(
                AdoptionApplication.animal_id == application.animal_id,
                AdoptionApplication.id != application_id,
                AdoptionApplication.status == "pending",
            ).all()
            for other in others:
                other_note = "Another application was selected for this animal."
                changed(
                    db.session.execute(
                        update(AdoptionApplication)
                        .where(
                            AdoptionApplication.id == other.id,
                            AdoptionApplication.status == "pending",
                            AdoptionApplication.version == other.version,
                        )
                        .values(
                            status="rejected",
                            review_note=other_note,
                            reviewer_id=self.actor.id,
                            reviewed_at=utcnow(),
                            version=AdoptionApplication.version + 1,
                        )
                    )
                )
                db.session.add(
                    AuditEvent(
                        application_id=other.id,
                        actor_id=self.actor.id,
                        action="rejected",
                        note=other_note,
                    )
                )
                self.cancel_related_appointments(other.id)
        else:
            self.cancel_related_appointments(application_id)
        db.session.commit()
        return application

    @staticmethod
    def cancel_related_appointments(application_id):
        db.session.execute(
            update(Appointment)
            .where(
                Appointment.application_id == application_id,
                Appointment.status == "scheduled",
            )
            .values(status="cancelled", active_slot=None, version=Appointment.version + 1)
        )

    def complete_adoption(self, application_id, version):
        require_role(self.actor, "staff")
        application = get(AdoptionApplication, application_id)
        if application.status != "approved":
            raise DomainError(
                "Only an approved application can become a completed adoption.", 409
            )
        changed(
            db.session.execute(
                update(Animal)
                .where(Animal.id == application.animal_id, Animal.status == "pending")
                .values(status="adopted", version=Animal.version + 1)
            )
        )
        changed(
            db.session.execute(
                update(AdoptionApplication)
                .where(
                    AdoptionApplication.id == application_id,
                    AdoptionApplication.status == "approved",
                    AdoptionApplication.version == number(version, "Version", 1),
                )
                .values(status="completed", version=AdoptionApplication.version + 1)
            )
        )
        adoption = Adoption(
            application_id=application.id,
            animal_id=application.animal_id,
            adopter_id=application.user_id,
            staff_id=self.actor.id,
        )
        db.session.add(adoption)
        db.session.add(
            AuditEvent(
                application_id=application_id,
                actor_id=self.actor.id,
                action="completed",
                note="Placement completed; adoption history saved.",
            )
        )
        self.cancel_related_appointments(application_id)
        db.session.commit()
        return adoption

    def save_medical(self, animal_id, data, record_id=None):
        require_role(self.actor, "staff")
        get(Animal, animal_id)
        try:
            when = date.fromisoformat(data.get("record_date", ""))
        except ValueError:
            raise DomainError("Choose a valid medical record date.")
        if when > date.today():
            raise DomainError("A completed medical record cannot have a future date.")
        fields = dict(
            record_date=when,
            kind=text(data.get("kind"), "Record type", 40),
            notes=text(data.get("notes"), "Notes", 3000),
            staff_id=self.actor.id,
        )
        if record_id:
            record = get(MedicalRecord, record_id)
            if record.animal_id != animal_id:
                raise DomainError("Medical record not found for this animal.", 404)
            changed(
                db.session.execute(
                    update(MedicalRecord)
                    .where(
                        MedicalRecord.id == record_id,
                        MedicalRecord.version == number(data.get("version"), "Version", 1),
                    )
                    .values(**fields, version=MedicalRecord.version + 1)
                )
            )
        else:
            record = MedicalRecord(animal_id=animal_id, **fields)
            db.session.add(record)
        db.session.commit()
        return record

    def appointment_application(self, application_id):
        application = get(AdoptionApplication, application_id)
        if not self.actor or (
            self.actor.role != "staff" and self.actor.id != application.user_id
        ):
            raise DomainError("You cannot manage another adopter’s appointment.", 403)
        return application

    def schedule(self, application_id, data, appointment_id=None):
        application = self.appointment_application(application_id)
        if application.status not in ("pending", "approved"):
            raise DomainError("Appointments require an active adoption application.", 409)
        starts = AppointmentPolicy.parse_slot(data.get("starts_at"))
        notes = text(data.get("notes"), "Visit notes", 500, 0)
        # Booking and a simultaneous review cannot silently cross each other.
        changed(
            db.session.execute(
                update(AdoptionApplication)
                .where(
                    AdoptionApplication.id == application_id,
                    AdoptionApplication.version == application.version,
                    AdoptionApplication.status.in_(["pending", "approved"]),
                )
                .values(version=AdoptionApplication.version + 1)
            )
        )
        fields = dict(
            starts_at=starts, active_slot=starts.strftime("%Y-%m-%dT%H:%M"), notes=notes
        )
        if appointment_id:
            record = get(Appointment, appointment_id)
            if record.application_id != application_id or record.status != "scheduled":
                raise DomainError("This appointment cannot be rescheduled.", 409)
            changed(
                db.session.execute(
                    update(Appointment)
                    .where(
                        Appointment.id == appointment_id,
                        Appointment.version == number(data.get("version"), "Version", 1),
                    )
                    .values(**fields, version=Appointment.version + 1)
                )
            )
        else:
            if Appointment.query.filter_by(
                application_id=application_id, status="scheduled"
            ).first():
                raise DomainError(
                    "Reschedule the existing visit instead of adding a second one.", 409
                )
            record = Appointment(application_id=application_id, **fields)
            db.session.add(record)
        db.session.commit()
        return record

    def cancel_appointment(self, appointment_id, version):
        record = get(Appointment, appointment_id)
        self.appointment_application(record.application_id)
        if record.status != "scheduled":
            raise DomainError("This appointment is already cancelled.", 409)
        changed(
            db.session.execute(
                update(Appointment)
                .where(
                    Appointment.id == appointment_id,
                    Appointment.version == number(version, "Version", 1),
                )
                .values(
                    status="cancelled", active_slot=None, version=Appointment.version + 1
                )
            )
        )
        db.session.commit()
