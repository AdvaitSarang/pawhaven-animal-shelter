# Pawhaven

Animal Shelter and Adoption Management System for a local classroom demonstration.

## Features

- Adopter registration and login, with separately provisioned staff accounts.
- Animal search, filtering, profiles and staff profile maintenance.
- Adoption applications, staff approval/rejection, and private status tracking.
- Staff medical records and meet-and-greet appointments.
- Separate placement confirmation, adoption history and audit records.
- Local animal photos, with species illustrations as the fallback.

Approval reserves an animal. Completing the placement changes the animal to
Adopted and creates its adoption-history record. The demo uses fictional data.

## Repository folders

| Folder | Contents |
| --- | --- |
| `source/` | Flask app, templates, CSS, photos, dependencies and setup scripts |
| `test/` | pytest cases, fixtures, Windows test runner and optional browser check |
| `docs/` | Requirements baseline and model diagrams |

The app uses Python, Flask, Jinja, Bootstrap-Flask, SQLAlchemy and SQLite.
SQLite is the verified demo backend. MySQL setup material is included for future
integration; a live MySQL run has not been verified.

## Run on Windows

Python 3.12 or later and a browser are required. The project was also run with
Python 3.14 on the presentation laptop. Install dependencies before class.

Open a PowerShell terminal in the repository, then run:

```powershell
cd source
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app shelter init-db
.\.venv\Scripts\python.exe -m flask --app shelter seed-demo
.\.venv\Scripts\python.exe -m flask --app shelter run --host 127.0.0.1 --port 5000
```

Alternatively, run `source/setup_windows.bat` once, then
`source/start_windows.bat` to start the app.

Open <http://127.0.0.1:5000> on the same computer and keep the server terminal
running. For local SQLite, use a terminal without a custom `DATABASE_URL` or
`COOKIE_SECURE=1` setting. Dependencies are installed from the internet initially;
the prepared app serves its page styles and animal photos locally.

### Demo accounts and data

The first seed adds six animals and a staff account at `staff@example.test` with
a randomly generated password. Save the displayed password privately. Repeating
the seed leaves existing records unchanged. Existing local database changes,
including a renamed staff email, are specific to that local database.

Adopters register through the website. Public registration cannot create staff.
To provision another staff account, run the following inside `source/` and answer
the prompts:

```powershell
.\.venv\Scripts\python.exe -m flask --app shelter create-staff
```

The SQLite database is created at `source/instance/shelter.db`. No database,
session secret, staff password or virtual environment is distributed here.
Use separate browser profiles or an incognito window for adopter and staff.

## Run tests

Open a second terminal inside `source/`:

```powershell
.\.venv\Scripts\python.exe -m pytest -v ..\test
```

The suite contains 29 cases, including parameterized time-validation cases.
Tests use temporary databases rather than the running demo database. The Windows
wrapper is `test/run_tests_windows.bat`.

The optional browser replay is `test/browser/check_local.py`. It requires
Playwright and an installed Chromium browser. Its output folder is created during
the run; historical results and screenshots are not bundled in this source copy.

## Photos and documentation

The photo sources, authors and licenses are retained at
`source/shelter/static/photos/credits.html` and `sources.json`. The photos are
prepared local assets, not an arbitrary photo-upload feature. The shared template
update removes the visible sample badges and the extra footer items.

`docs/requirements-baseline.md` is the original requirements baseline; it records
its own verification limits. Design models are under `docs/diagrams/`.
The progress/final reports and their evidence archives are separate deliverables.

