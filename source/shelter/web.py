"""HTTP controller: request data in, service calls, rendered pages out."""

from functools import wraps
from sqlalchemy import or_
from flask import Blueprint, g, session, request, render_template, redirect, url_for, flash
from .models import (
    db,
    User,
    Animal,
    AdoptionApplication,
    MedicalRecord,
    Appointment,
    Adoption,
    AuditEvent,
)
from .services import ShelterService, DomainError, get, text, number

bp = Blueprint("web", __name__)


def login_required(role=None):
    def decorator(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            if not g.user:
                return redirect(url_for("web.login"))
            if role and g.user.role != role:
                raise DomainError(
                    (
                        "This page is only available to shelter staff."
                        if role == "staff"
                        else "Use an adopter account for this action."
                    ),
                    403,
                )
            return function(*args, **kwargs)

        return wrapped

    return decorator


def application_access(id_):
    record = get(AdoptionApplication, id_)
    if g.user.role != "staff" and record.user_id != g.user.id:
        raise DomainError("You cannot view another adopter’s application.", 403)
    return record


@bp.route("/")
def browse():
    query = Animal.query
    status = request.args.get("status", "available")
    if status not in ("available", "pending", "adopted", "all"):
        raise DomainError("Choose a valid animal status filter.")
    if status != "all":
        query = query.filter_by(status=status)
    term = request.args.get("q", "").strip()[:100]
    if term:
        query = query.filter(
            or_(
                Animal.name.icontains(term, autoescape=True),
                Animal.breed.icontains(term, autoescape=True),
            )
        )
    species, sex = request.args.get("species", ""), request.args.get("sex", "")
    if species:
        query = query.filter_by(species=species)
    if sex:
        query = query.filter_by(sex=sex)
    maximum = request.args.get("max_age", "")
    if maximum:
        query = query.filter(Animal.age_months <= number(maximum, "Maximum age", 0, 600))
    return render_template(
        "browse.html",
        animals=query.order_by(Animal.name).all(),
        term=term,
        available=Animal.query.filter_by(status="available").count(),
        selected_status=status,
    )


@bp.route("/animals/<int:id>")
def animal_detail(id):
    animal = get(Animal, id)
    medical = (
        MedicalRecord.query.filter_by(animal_id=id)
        .order_by(MedicalRecord.record_date.desc())
        .all()
        if g.user and g.user.role == "staff"
        else []
    )
    existing = (
        AdoptionApplication.query.filter_by(animal_id=id, user_id=g.user.id).first()
        if g.user and g.user.role == "adopter"
        else None
    )
    return render_template("animal.html", animal=animal, medical=medical, existing=existing)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # The browser cannot choose a staff role, even by forging a form field.
        user = ShelterService.register(request.form)
        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        flash("Your account is ready. Welcome to Pawhaven.", "success")
        return redirect(url_for("web.browse"))
    return render_template("auth.html", register=True)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = text(request.form.get("email"), "Email", 180).lower()
        password = str(request.form.get("password", ""))
        if len(password) > 128:
            raise DomainError("Incorrect email or password.", 401)
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            raise DomainError("Incorrect email or password.", 401)
        session.clear()
        session["user_id"] = user.id
        session.permanent = True
        return redirect(url_for("web.staff" if user.role == "staff" else "web.dashboard"))
    return render_template("auth.html", register=False)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.browse"))


@bp.route("/animals/<int:id>/apply", methods=["GET", "POST"])
@login_required("adopter")
def apply(id):
    animal = get(Animal, id)
    if request.method == "POST":
        record = ShelterService(g.user).submit_application(id, request.form)
        flash(
            "Application submitted. The shelter team will review your details.", "success"
        )
        return redirect(url_for("web.application", id=record.id))
    if not animal.is_available():
        raise DomainError("This animal is no longer accepting applications.", 409)
    return render_template("apply.html", animal=animal)


@bp.get("/dashboard")
@login_required()
def dashboard():
    if g.user.role == "staff":
        return redirect(url_for("web.staff"))
    applications = (
        AdoptionApplication.query.filter_by(user_id=g.user.id)
        .order_by(AdoptionApplication.created_at.desc())
        .all()
    )
    appointments = (
        Appointment.query.join(AdoptionApplication)
        .filter(AdoptionApplication.user_id == g.user.id)
        .order_by(Appointment.starts_at)
        .all()
    )
    return render_template(
        "dashboard.html", applications=applications, appointments=appointments
    )


@bp.get("/applications/<int:id>")
@login_required()
def application(id):
    record = application_access(id)
    events = AuditEvent.query.filter_by(application_id=id).order_by(AuditEvent.id).all()
    visits = (
        Appointment.query.filter_by(application_id=id).order_by(Appointment.starts_at).all()
    )
    return render_template("application.html", record=record, events=events, visits=visits)


@bp.post("/applications/<int:id>/review")
@login_required("staff")
def review(id):
    ShelterService(g.user).review_application(id, request.form)
    flash("Application decision saved.", "success")
    return redirect(url_for("web.application", id=id))


@bp.post("/applications/<int:id>/complete")
@login_required("staff")
def complete(id):
    if request.form.get("confirmed") != "yes":
        raise DomainError("Confirm that the animal has been placed with the adopter.")
    ShelterService(g.user).complete_adoption(id, request.form.get("version"))
    flash("Adoption completed and saved in history.", "success")
    return redirect(url_for("web.application", id=id))


@bp.get("/staff")
@login_required("staff")
def staff():
    return render_template(
        "staff.html",
        animals=Animal.query.order_by(Animal.name).all(),
        applications=AdoptionApplication.query.order_by(
            AdoptionApplication.created_at.desc()
        ).all(),
        appointments=Appointment.query.filter_by(status="scheduled")
        .order_by(Appointment.starts_at)
        .all(),
        adoptions=Adoption.query.order_by(Adoption.adopted_at.desc()).all(),
        pending=AdoptionApplication.query.filter_by(status="pending").count(),
        available=Animal.query.filter_by(status="available").count(),
    )


@bp.route("/staff/animals/new", methods=["GET", "POST"])
@bp.route("/staff/animals/<int:id>/edit", methods=["GET", "POST"])
@login_required("staff")
def edit_animal(id=None):
    record = get(Animal, id) if id else None
    if request.method == "POST":
        record = ShelterService(g.user).save_animal(request.form, id)
        flash("Animal profile saved.", "success")
        return redirect(url_for("web.animal_detail", id=record.id))
    return render_template("animal_form.html", record=record)


@bp.route("/staff/animals/<int:animal_id>/medical/new", methods=["GET", "POST"])
@bp.route("/staff/animals/<int:animal_id>/medical/<int:id>/edit", methods=["GET", "POST"])
@login_required("staff")
def medical(animal_id, id=None):
    animal = get(Animal, animal_id)
    record = get(MedicalRecord, id) if id else None
    if record and record.animal_id != animal_id:
        raise DomainError("Medical record not found for this animal.", 404)
    if request.method == "POST":
        ShelterService(g.user).save_medical(animal_id, request.form, id)
        flash("Medical record saved.", "success")
        return redirect(url_for("web.animal_detail", id=animal_id))
    return render_template("medical_form.html", animal=animal, record=record)


@bp.route("/applications/<int:application_id>/appointments/new", methods=["GET", "POST"])
@bp.route("/appointments/<int:id>/edit", methods=["GET", "POST"])
@login_required()
def appointment(application_id=None, id=None):
    record = get(Appointment, id) if id else None
    application_id = record.application_id if record else application_id
    app_record = application_access(application_id)
    if request.method == "POST":
        ShelterService(g.user).schedule(application_id, request.form, id)
        flash("Your visit is scheduled. Times are in America/Chicago.", "success")
        return redirect(url_for("web.application", id=application_id))
    return render_template("appointment_form.html", record=record, app_record=app_record)


@bp.post("/appointments/<int:id>/cancel")
@login_required()
def cancel_appointment(id):
    record = get(Appointment, id)
    application_access(record.application_id)
    ShelterService(g.user).cancel_appointment(id, request.form.get("version"))
    flash("Appointment cancelled.", "success")
    return redirect(url_for("web.application", id=record.application_id))
