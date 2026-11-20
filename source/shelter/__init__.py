"""Flask application factory and local setup commands."""

import os
import secrets
from pathlib import Path
from datetime import timedelta
import click
from flask import Flask, g, session, request, render_template
from flask_bootstrap import Bootstrap5
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from .models import db, User, Animal
from .services import DomainError, ShelterService


@event.listens_for(Engine, "connect")
def sqlite_foreign_keys(connection, record):
    if connection.__class__.__module__.startswith("sqlite3"):
        connection.execute("PRAGMA foreign_keys=ON")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    secret_path = Path(app.instance_path) / "session-secret.txt"
    secret = os.getenv("SECRET_KEY")
    if not secret:
        if not secret_path.exists():
            try:
                with secret_path.open("x") as stream:
                    stream.write(secrets.token_hex(32))
                secret_path.chmod(0o600)
            except FileExistsError:
                pass
        secret = secret_path.read_text().strip()
    app.config.from_mapping(
        SECRET_KEY=secret,
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL", "sqlite:///shelter.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
        BOOTSTRAP_SERVE_LOCAL=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        MAX_CONTENT_LENGTH=32 * 1024,
        CSRF_ENABLED=True,
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    Bootstrap5(app)

    @app.before_request
    def load_user_and_check_csrf():
        g.user = (
            db.session.get(User, session["user_id"]) if session.get("user_id") else None
        )
        session.setdefault("csrf_token", secrets.token_urlsafe(32))
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            token = request.form.get("csrf_token", "")
            if not secrets.compare_digest(
                token.encode("utf-8"), session["csrf_token"].encode("utf-8")
            ):
                raise DomainError("This form expired. Reload the page and try again.", 403)

    @app.after_request
    def response_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if g.get("user") or request.path in ("/login", "/register"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(DomainError)
    def domain_error(error):
        db.session.rollback()
        return (
            render_template("error.html", message=str(error), code=error.status),
            error.status,
        )

    @app.errorhandler(IntegrityError)
    def database_conflict(error):
        db.session.rollback()
        return (
            render_template(
                "error.html",
                code=409,
                message=(
                    "This change conflicts with an existing record. The email or application may already exist, "
                    "or the appointment slot may have just been taken. No partial changes were saved."
                ),
            ),
            409,
        )

    @app.errorhandler(404)
    def not_found(error):
        return (
            render_template("error.html", code=404, message="This page was not found."),
            404,
        )

    from .web import bp

    app.register_blueprint(bp)

    @app.cli.command("init-db")
    def init_db():
        """Create missing tables. Does not delete existing records."""
        db.create_all()
        click.echo("Database tables are ready.")

    @app.cli.command("create-staff")
    @click.option("--name", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_staff(name, email, password):
        """Provision staff locally; public registration always creates adopters."""
        try:
            ShelterService.register(
                dict(name=name, email=email, password=password), role="staff"
            )
        except DomainError as error:
            raise click.ClickException(str(error))
        click.echo("Staff account created.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Add fictional animals and one staff account to a completely empty database."""
        if User.query.first() or Animal.query.first():
            click.echo("Demo seed skipped: records already exist. Nothing was overwritten.")
            return
        password = secrets.token_urlsafe(12)
        staff = User(name="Demo Shelter Staff", email="staff@example.test", role="staff")
        staff.set_password(password)
        db.session.add(staff)
        animals = [
            (
                "Maple",
                "Dog",
                "Labrador mix",
                30,
                "Female",
                "An affectionate walking companion. Maple loves sniffing trails and relaxing beside people. A calm introduction helps her settle into a new home.",
            ),
            (
                "Milo",
                "Cat",
                "Domestic shorthair",
                18,
                "Male",
                "Curious, playful and happiest near a sunny window. Milo enjoys feather toys and gentle company.",
            ),
            (
                "Clover",
                "Rabbit",
                "Mini lop",
                12,
                "Female",
                "A gentle rabbit who enjoys fresh hay and room to explore. Clover needs a safe indoor enclosure and patient handling.",
            ),
            (
                "Benny",
                "Dog",
                "Terrier mix",
                48,
                "Male",
                "A cheerful small dog who enjoys short walks and food puzzles. Benny would suit a home with a steady routine.",
            ),
            (
                "Olive",
                "Cat",
                "Domestic longhair",
                60,
                "Female",
                "A quiet companion who enjoys brushing and peaceful afternoons. Olive prefers a relaxed household.",
            ),
            (
                "Teddy",
                "Dog",
                "Shepherd mix",
                10,
                "Male",
                "A bright young dog with energy to spare. Teddy needs daily exercise, positive training and a family ready to teach him.",
            ),
        ]
        for name, species, breed, age, sex, description in animals:
            db.session.add(
                Animal(
                    name=name,
                    species=species,
                    breed=breed,
                    age_months=age,
                    sex=sex,
                    description=description,
                )
            )
        db.session.commit()
        click.echo(
            "Fictional demonstration records added. Copy these LOCAL demo credentials:"
        )
        click.echo("Staff email: staff@example.test")
        click.echo("Staff password: " + password)
        click.echo(
            "Adopters can register through the website. To add another staff account, use create-staff."
        )

    return app
