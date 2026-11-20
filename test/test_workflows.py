"""Behavioral evidence. Tests use temporary SQLite databases, never user records."""

import re
from datetime import date, datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import IntegrityError
from shelter.models import (
    db,
    User,
    Animal,
    AdoptionApplication,
    Appointment,
    MedicalRecord,
    Adoption,
    AuditEvent,
)
from shelter.services import number, DomainError, AppointmentPolicy
from conftest import sign_in, apply_to, application_data, version_of


def next_slot(days=2, hour=10, minute=0):
    return (
        (datetime.now(ZoneInfo("America/Chicago")) + timedelta(days=days))
        .replace(hour=hour, minute=minute, second=0, microsecond=0)
        .strftime("%Y-%m-%dT%H:%M")
    )


def decide(client, app, record_id, decision="approved", version=None):
    version = version or version_of(app, AdoptionApplication, record_id)
    return client.post(
        f"/applications/{record_id}/review",
        data={
            "decision": decision,
            "version": version,
            "note": "Home and care plan reviewed.",
        },
    )


def book(client, record_id, slot=None):
    return client.post(
        f"/applications/{record_id}/appointments/new",
        data={
            "starts_at": slot or next_slot(),
            "notes": "Meet the animal and discuss care.",
        },
    )


def test_T01_registration_hashes_password_and_prevents_role_escalation(client, app):
    response = client.post(
        "/register",
        data={
            "name": "New Adopter",
            "email": "NEW@example.test",
            "password": "A long password 123!",
            "role": "staff",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user = User.query.filter_by(email="new@example.test").one()
        assert user.role == "adopter"
        assert user.password_hash != "A long password 123!"
        assert user.check_password("A long password 123!")
    assert client.get("/staff").status_code == 403


def test_T02_login_logout_and_duplicate_email(client, app):
    assert (
        client.post(
            "/login", data={"email": "alex@example.test", "password": "wrong"}
        ).status_code
        == 401
    )
    assert sign_in(client).status_code == 302
    assert client.get("/dashboard").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302
    assert (
        client.post(
            "/register",
            data={
                "name": "Duplicate",
                "email": "Alex@example.test",
                "password": "Long enough 123",
            },
        ).status_code
        == 409
    )


def test_T03_csrf_missing_unicode_and_valid_token(client, app):
    app.config["CSRF_ENABLED"] = True
    assert client.post("/login", data={"email": "alex@example.test"}).status_code == 403
    assert client.post("/logout", data={"csrf_token": "invalid♥"}).status_code == 403
    client.get("/login")
    with client.session_transaction() as session:
        token = session["csrf_token"]
    assert client.post("/logout", data={"csrf_token": token}).status_code == 302


def test_T04_browse_filters_and_literal_search(client, app):
    response = client.get("/?species=Cat&sex=Male&max_age=24")
    assert response.status_code == 200
    assert b"Milo" in response.data and b"Maple" not in response.data.replace(
        b"Try Maple or Labrador", b""
    )
    assert b"No matches this time" in client.get("/?q=%25").data
    assert client.get("/?max_age=-1").status_code == 400
    assert client.get("/?status=invalid").status_code == 400


def test_T05_staff_animal_create_edit_stale_guard_and_escaped_output(client, app):
    assert client.get("/staff/animals/new").status_code == 302
    sign_in(client)
    assert client.post("/staff/animals/new", data={}).status_code == 403
    sign_in(client, "staff@example.test")
    data = dict(
        name="<script>alert(1)</script>",
        species="Rabbit",
        breed="Lop",
        sex="Unknown",
        age_months="0",
        description="A friendly young rabbit.",
    )
    response = client.post("/staff/animals/new", data=data)
    assert response.status_code == 302
    location = response.headers["Location"]
    assert b"&lt;script&gt;" in client.get(location).data
    animal_id = int(location.rsplit("/", 1)[1])
    data.update(name="Clover", version=1)
    assert client.post(f"/staff/animals/{animal_id}/edit", data=data).status_code == 302
    data["name"] = "Stale overwrite"
    assert client.post(f"/staff/animals/{animal_id}/edit", data=data).status_code == 409
    with app.app_context():
        assert db.session.get(Animal, animal_id).name == "Clover"


def test_T06_application_saved_with_event_and_duplicate_blocked(client, app):
    sign_in(client)
    record_id = apply_to(client)
    assert client.get(f"/applications/{record_id}").status_code == 200
    assert client.post("/animals/1/apply", data=application_data()).status_code == 409
    with app.app_context():
        assert AdoptionApplication.query.count() == 1
        assert AuditEvent.query.filter_by(action="submitted").count() == 1
        assert db.session.get(Animal, 1).status == "available"


def test_T07_private_records_are_owner_or_staff_only(client, app):
    sign_in(client)
    record_id = apply_to(client)
    assert book(client, record_id).status_code == 302
    with app.app_context():
        visit_id = Appointment.query.one().id
    sign_in(client, "sam@example.test")
    assert client.get(f"/applications/{record_id}").status_code == 403
    assert client.get(f"/appointments/{visit_id}/edit").status_code == 403
    assert (
        client.post(f"/appointments/{visit_id}/cancel", data={"version": 1}).status_code
        == 403
    )
    assert client.post(f"/applications/{record_id}/review", data={}).status_code == 403
    assert client.post(f"/applications/{record_id}/complete", data={}).status_code == 403
    assert b"Maple" not in client.get("/dashboard").data
    sign_in(client, "staff@example.test")
    assert client.get(f"/applications/{record_id}").status_code == 200


def test_T08_approval_reserves_animal_and_closes_other_applications(client, app):
    sign_in(client)
    first = apply_to(client)
    sign_in(client, "sam@example.test")
    second = apply_to(client)
    assert book(client, second).status_code == 302
    sign_in(client, "staff@example.test")
    assert decide(client, app, first).status_code == 302
    with app.app_context():
        assert db.session.get(Animal, 1).status == "pending"
        assert db.session.get(AdoptionApplication, first).status == "approved"
        assert db.session.get(AdoptionApplication, second).status == "rejected"
        assert Appointment.query.one().active_slot is None
        assert Appointment.query.one().status == "cancelled"
        assert AuditEvent.query.filter_by(action="rejected").count() == 1
    assert decide(client, app, second).status_code == 409


def test_T09_rejection_keeps_animal_available_and_releases_slot(client, app):
    sign_in(client)
    record_id = apply_to(client)
    assert book(client, record_id).status_code == 302
    sign_in(client, "staff@example.test")
    assert decide(client, app, record_id, "rejected").status_code == 302
    with app.app_context():
        assert db.session.get(Animal, 1).status == "available"
        assert Appointment.query.one().status == "cancelled"
    assert book(client, record_id).status_code == 409


def test_T10_stale_review_rolls_back_animal_reservation(client, app):
    sign_in(client)
    record_id = apply_to(client)
    old_version = version_of(app, AdoptionApplication, record_id)
    assert book(client, record_id).status_code == 302
    sign_in(client, "staff@example.test")
    assert decide(client, app, record_id, version=old_version).status_code == 409
    with app.app_context():
        assert db.session.get(Animal, 1).status == "available"
        assert db.session.get(AdoptionApplication, record_id).status == "pending"
        assert AuditEvent.query.filter_by(action="approved").count() == 0


def test_T11_completion_creates_one_history_record_atomically(client, app):
    sign_in(client)
    record_id = apply_to(client)
    assert book(client, record_id).status_code == 302
    sign_in(client, "staff@example.test")
    assert decide(client, app, record_id).status_code == 302
    version = version_of(app, AdoptionApplication, record_id)
    url = f"/applications/{record_id}/complete"
    assert client.post(url, data={"version": version}).status_code == 400
    assert (
        client.post(url, data={"version": version, "confirmed": "yes"}).status_code == 302
    )
    assert (
        client.post(url, data={"version": version, "confirmed": "yes"}).status_code == 409
    )
    with app.app_context():
        assert Adoption.query.count() == 1
        assert (
            Adoption.query.one().adopter_id
            == User.query.filter_by(email="alex@example.test").one().id
        )
        assert db.session.get(Animal, 1).status == "adopted"
        assert db.session.get(AdoptionApplication, record_id).status == "completed"
        assert Appointment.query.one().status == "cancelled"
    assert b"Alex" in client.get("/staff").data


def test_T12_stale_completion_cannot_partially_adopt_animal(client, app):
    sign_in(client)
    record_id = apply_to(client)
    sign_in(client, "staff@example.test")
    decide(client, app, record_id)
    old_version = version_of(app, AdoptionApplication, record_id)
    assert book(client, record_id).status_code == 302
    response = client.post(
        f"/applications/{record_id}/complete",
        data={"version": old_version, "confirmed": "yes"},
    )
    assert response.status_code == 409
    with app.app_context():
        assert db.session.get(Animal, 1).status == "pending"
        assert db.session.get(AdoptionApplication, record_id).status == "approved"
        assert Adoption.query.count() == 0


def test_T13_ineligible_and_invalid_applications_are_rejected(client, app):
    sign_in(client)
    bad = application_data()
    bad["reason"] = "short"
    assert client.post("/animals/1/apply", data=bad).status_code == 400
    record_id = apply_to(client)
    sign_in(client, "staff@example.test")
    decide(client, app, record_id)
    sign_in(client, "sam@example.test")
    assert client.get("/animals/1/apply").status_code == 409
    assert client.post("/animals/1/apply", data=application_data()).status_code == 409
    with app.app_context():
        assert AdoptionApplication.query.count() == 1


def test_T14_medical_create_update_validation_and_staff_privacy(client, app):
    sign_in(client)
    assert client.get("/staff/animals/1/medical/new").status_code == 403
    sign_in(client, "staff@example.test")
    data = {
        "record_date": date.today().isoformat(),
        "kind": "Vaccination",
        "notes": "Private clinical note.",
    }
    assert client.post("/staff/animals/1/medical/new", data=data).status_code == 302
    with app.app_context():
        record_id = MedicalRecord.query.one().id
    data.update(notes="Updated private clinical note.", version=1)
    assert (
        client.post(f"/staff/animals/1/medical/{record_id}/edit", data=data).status_code
        == 302
    )
    assert (
        client.post(f"/staff/animals/1/medical/{record_id}/edit", data=data).status_code
        == 409
    )
    assert client.get(f"/staff/animals/2/medical/{record_id}/edit").status_code == 404
    data["record_date"] = (date.today() + timedelta(days=1)).isoformat()
    assert client.post("/staff/animals/1/medical/new", data=data).status_code == 400
    sign_in(client)
    assert b"Private clinical note" not in client.get("/animals/1").data
    assert b"Updated private clinical note" not in client.get("/animals/1").data


def test_T15_appointments_reschedule_cancel_and_slot_reuse(client, app):
    sign_in(client)
    record_id = apply_to(client)
    slot = next_slot()
    assert book(client, record_id, slot).status_code == 302
    with app.app_context():
        visit_id = Appointment.query.one().id
    assert book(client, record_id, next_slot(hour=11)).status_code == 409
    assert (
        client.post(
            f"/appointments/{visit_id}/edit",
            data={"starts_at": next_slot(hour=11), "version": 1},
        ).status_code
        == 302
    )
    assert (
        client.post(
            f"/appointments/{visit_id}/edit",
            data={"starts_at": next_slot(hour=12), "version": 1},
        ).status_code
        == 409
    )
    assert (
        client.post(f"/appointments/{visit_id}/cancel", data={"version": 2}).status_code
        == 302
    )
    assert (
        client.post(f"/appointments/{visit_id}/cancel", data={"version": 2}).status_code
        == 409
    )
    assert book(client, record_id, slot).status_code == 302


def test_T16_slot_conflict_rolls_back_application_version(client, app):
    sign_in(client)
    first = apply_to(client)
    assert book(client, first).status_code == 302
    sign_in(client, "sam@example.test")
    second = apply_to(client, 2)
    old_version = version_of(app, AdoptionApplication, second)
    assert book(client, second).status_code == 409
    assert version_of(app, AdoptionApplication, second) == old_version
    with app.app_context():
        assert Appointment.query.count() == 1


@pytest.mark.parametrize(
    "slot",
    [
        "bad",
        "2000-01-01T10:00",
        next_slot(hour=9),
        next_slot(minute=15),
        next_slot(days=181),
    ],
)
def test_T17_invalid_visit_times_are_blocked(client, app, slot):
    sign_in(client)
    record_id = apply_to(client)
    assert book(client, record_id, slot).status_code == 400
    with app.app_context():
        assert Appointment.query.count() == 0


def test_T18_competing_approvals_have_one_winner(client, app):
    sign_in(client)
    first = apply_to(client)
    sign_in(client, "sam@example.test")
    second = apply_to(client)
    with app.app_context():
        engine = db.engine
        staff_id = User.query.filter_by(role="staff").one().id
    barrier = Barrier(2)

    def pause_before_reservation(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE animals SET status="):
            barrier.wait(timeout=10)

    event.listen(engine, "before_cursor_execute", pause_before_reservation)

    def approve(record_id):
        browser = app.test_client()
        with browser.session_transaction() as session:
            session["user_id"] = staff_id
        return browser.post(
            f"/applications/{record_id}/review",
            data={"version": 1, "decision": "approved", "note": "Concurrent review test."},
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(approve, [first, second]))
    finally:
        event.remove(engine, "before_cursor_execute", pause_before_reservation)
    assert sorted(results) == [302, 409]
    with app.app_context():
        assert AdoptionApplication.query.filter_by(status="approved").count() == 1
        assert AdoptionApplication.query.filter_by(status="rejected").count() == 1
        assert db.session.get(Animal, 1).status == "pending"


def test_T19_competing_bookings_have_one_winner(client, app):
    sign_in(client)
    first = apply_to(client)
    sign_in(client, "sam@example.test")
    second = apply_to(client, 2)
    with app.app_context():
        engine = db.engine
        staff_id = User.query.filter_by(role="staff").one().id
    barrier = Barrier(2)

    def pause_before_write(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE applications SET version="):
            barrier.wait(timeout=10)

    event.listen(engine, "before_cursor_execute", pause_before_write)

    def reserve(record_id):
        browser = app.test_client()
        with browser.session_transaction() as session:
            session["user_id"] = staff_id
        return book(browser, record_id).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, [first, second]))
    finally:
        event.remove(engine, "before_cursor_execute", pause_before_write)
    assert sorted(results) == [302, 409]
    with app.app_context():
        assert Appointment.query.filter_by(status="scheduled").count() == 1


def test_T20_templates_static_assets_and_response_headers(client, app):
    for path in [
        "/",
        "/animals/1",
        "/login",
        "/register",
        "/static/style.css",
        "/static/dog.svg",
        "/static/cat.svg",
        "/static/rabbit.svg",
    ]:
        assert client.get(path).status_code == 200, path
    html = client.get("/").get_data(as_text=True)
    css_paths = re.findall(r'href="([^\"]+\.css[^\"]*)"', html)
    assert len(css_paths) == 2
    for path in css_paths:
        assert path.startswith("/") and client.get(path).status_code == 200
    sign_in(client)
    record_id = apply_to(client)
    for path in [
        "/dashboard",
        f"/applications/{record_id}",
        f"/applications/{record_id}/appointments/new",
        "/animals/2/apply",
    ]:
        assert client.get(path).status_code == 200, path
    sign_in(client, "staff@example.test")
    for path in [
        "/staff",
        "/staff/animals/new",
        "/staff/animals/1/edit",
        "/staff/animals/1/medical/new",
        f"/applications/{record_id}",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["Cache-Control"] == "no-store"
        assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert client.get("/missing").status_code == 404


def test_T21_foreign_keys_and_unique_constraints_are_active(app):
    with app.app_context():
        db.session.add(
            AdoptionApplication(
                user_id=999,
                animal_id=1,
                phone="1234567890",
                housing="Own home",
                reason="Test invalid foreign key.",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        db.session.add(
            User(
                name="Duplicate",
                email="alex@example.test",
                role="adopter",
                password_hash="irrelevant",
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        assert AdoptionApplication.query.count() == 0


def test_T22_demo_seed_does_not_overwrite_existing_records(app):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0 and "skipped" in result.output
    with app.app_context():
        assert User.query.count() == 3 and Animal.query.count() == 2


def test_T23_numeric_age_boundary_accepts_newborn_rejects_decimal():
    assert number(0, "Age", 0, 600) == 0
    assert number("600", "Age", 0, 600) == 600
    for value in ["1.5", "-1", "601", None]:
        with pytest.raises(DomainError):
            number(value, "Age", 0, 600)


def test_T24_staff_is_blocked_from_adopter_submission(client, app):
    sign_in(client, "staff@example.test")
    assert client.get("/animals/1/apply").status_code == 403
    assert client.post("/animals/1/apply", data=application_data()).status_code == 403
    with app.app_context():
        assert AdoptionApplication.query.count() == 0


def test_T25_real_form_tokens_survive_login_and_application_round_trip(client, app):
    app.config["CSRF_ENABLED"] = True

    def token_from(path):
        html = client.get(path).get_data(as_text=True)
        match = re.search(r'name="csrf_token" value="([^\"]+)"', html)
        assert match and match.group(1)
        return match.group(1)

    login_token = token_from("/login")
    assert (
        client.post(
            "/login",
            data={
                "email": "alex@example.test",
                "password": "Demo password 246!",
                "csrf_token": login_token,
            },
        ).status_code
        == 302
    )
    apply_token = token_from("/animals/1/apply")
    assert apply_token != login_token
    fields = application_data()
    fields["csrf_token"] = apply_token
    response = client.post("/animals/1/apply", data=fields, follow_redirects=True)
    assert response.status_code == 200 and b"Application submitted." in response.data
