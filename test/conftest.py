import pytest
from shelter import create_app
from shelter.models import db, User, Animal

PASSWORD = "Demo password 246!"


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-only-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + str(tmp_path / "test.db"),
            "CSRF_ENABLED": False,
        }
    )
    with application.app_context():
        db.create_all()
        for name, email, role in [
            ("Staff", "staff@example.test", "staff"),
            ("Alex", "alex@example.test", "adopter"),
            ("Sam", "sam@example.test", "adopter"),
        ]:
            user = User(name=name, email=email, role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
        db.session.add_all(
            [
                Animal(
                    name="Maple",
                    species="Dog",
                    breed="Labrador mix",
                    age_months=30,
                    sex="Female",
                    description="A gentle companion who enjoys walks.",
                ),
                Animal(
                    name="Milo",
                    species="Cat",
                    breed="Shorthair",
                    age_months=18,
                    sex="Male",
                    description="A curious and playful cat.",
                ),
            ]
        )
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def sign_in(client, email="alex@example.test"):
    return client.post("/login", data={"email": email, "password": PASSWORD})


def application_data():
    return {
        "phone": "+1 817 555 0100",
        "housing": "Own home",
        "reason": "I can provide a quiet home, daily care and regular veterinary visits.",
    }


def apply_to(client, animal_id=1):
    response = client.post(f"/animals/{animal_id}/apply", data=application_data())
    assert response.status_code == 302
    return int(response.headers["Location"].rsplit("/", 1)[1])


def version_of(app, model, record_id):
    with app.app_context():
        return db.session.get(model, record_id).version
