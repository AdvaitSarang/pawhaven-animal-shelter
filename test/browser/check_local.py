"""Exercise the local browser UI in a fresh, disposable SQLite database.

Optional tooling: playwright, plus its Chromium browser, or supply
--browser-executable. Run from any directory with the app requirements installed.
The check starts its own loopback server; stop any other app using the chosen port.
"""
import argparse
from pathlib import Path
import json
import os
import platform
import re
import secrets
import sqlite3
import statistics
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "source"))
from shelter import create_app

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser-executable")
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--out", type=Path, default=root / "test" / "results" / "browser-rerun")
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["SECRET_KEY"] = secrets.token_hex(32)
        os.environ["DATABASE_URL"] = "sqlite:///" + str((Path(tmp) / "demo.db").resolve())
        os.environ["COOKIE_SECURE"] = "0"
        app = create_app()
        runner = app.test_cli_runner()
        assert runner.invoke(args=["init-db"]).exit_code == 0
        seeded = runner.invoke(args=["seed-demo"])
        assert seeded.exit_code == 0
        staff_pw = re.search(r"Staff password: ([^\r\n]+)", seeded.output).group(1)
        server = make_server("127.0.0.1", args.port, app, threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{args.port}"
        try:
            with sync_playwright() as pw:
                opts = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]}
                if args.browser_executable:
                    opts["executable_path"] = args.browser_executable
                browser = pw.chromium.launch(**opts)
                ctx = browser.new_context(viewport={"width": 1390, "height": 865}, device_scale_factor=1)
                pg = ctx.new_page()
                pg.set_default_timeout(10000)
                def snap(name):
                    pg.screenshot(path=str(out / name), animations="disabled")
                def has(s):
                    assert s in pg.locator("body").inner_text(), s
                def login(email,pwd):
                    pg.goto(base+"/login")
                    pg.locator('[name=email]').fill(email)
                    pg.locator('[name=password]').fill(pwd)
                    pg.locator('form button[type=submit], form button.btn-primary').last.click()
                pg.goto(base+"/")
                pg.get_by_role("link",name=re.compile("Meet the animals")).first.click()
                pg.get_by_role("link",name="Maple",exact=True).first.click()
                assert pg.url.endswith("/animals/1")
                observed = {"browser": browser.version, "python": platform.python_version(),
                            "os": platform.system(), "sqlite": sqlite3.sqlite_version,
                            "base": base, "seeded_animals": 6, "viewport":[1390,865],
                            "profile_navigation_actions":2, "navigation_start":"unfiltered home; fresh visitor"}
                timings = {}
                for label, path in [("dog_search","/?species=Dog&status=available"),("maple_profile","/animals/1")]:
                    pg.goto(base+path)
                    samples = []
                    for _ in range(10):
                        response=pg.goto(base+path, wait_until="load")
                        assert response.status == 200
                        pg.wait_for_function("performance.getEntriesByType('navigation')[0].loadEventEnd > 0")
                        samples.append(pg.evaluate("performance.getEntriesByType('navigation')[0].loadEventEnd"))
                    timings[label]={"samples_ms":samples, "median_ms":statistics.median(samples),"max_ms":max(samples)}
                observed["timings"]=timings
                mobile=browser.new_context(viewport={"width":390,"height":844})
                small=mobile.new_page(); small.goto(base+"/animals/1")
                assert small.evaluate("document.documentElement.scrollWidth <= innerWidth")
                small.keyboard.press("Tab")
                assert small.locator(":focus").inner_text()=="Skip to content"
                observed["small_viewport"]="390x844, Maple profile: no horizontal overflow; first Tab reached skip link"
                mobile.close()
                pg.goto(base+"/register")
                pg.locator('[name=name]').fill("River Demo")
                pg.locator('[name=email]').fill("river@example.test")
                adopter_pw = secrets.token_urlsafe(16)
                pg.locator('[name=password]').fill(adopter_pw)
                pg.get_by_role("button", name="Create account").click()
                has("Your account is ready"); has("My applications")
                snap("N01-registration.png")
                pg.get_by_role("button", name="Sign out").click()
                login("river@example.test",adopter_pw);assert pg.url.endswith("/dashboard")
                pg.get_by_role("button", name="Sign out").click()
                login("staff@example.test",staff_pw);assert pg.url.endswith("/staff")
                snap("N02-staff-desk.png")
                pg.goto(base+"/staff/animals/new")
                for k,v in {"name":"Juniper","breed":"Domestic shorthair","age_months":"12","description":"Indoor companion who enjoys a quiet introduction."}.items():
                    pg.locator(f'[name={k}]').fill(v)
                pg.locator('[name=species]').select_option(label="Cat")
                pg.locator('[name=sex]').select_option(label="Female")
                pg.get_by_role("button",name="Save animal").click()
                has("Juniper"); has("Animal profile saved")
                record_url=pg.url
                pg.get_by_role("link",name="Edit profile").click()
                pg.locator('[name=age_months]').fill("13")
                pg.locator('[name=description]').fill("Quiet indoor companion. Updated care note: offer a covered resting spot.")
                snap("N03-edit-animal.png")
                pg.get_by_role("button",name="Save animal").click()
                assert pg.url==record_url
                pg.reload()
                has("13 months"); has("covered resting spot")
                snap("N04-saved-animal.png")
                observed["checks"]=["Two-click discovery","Filtered list and profile timings",
                    "Small viewport and initial keyboard focus","Adopter registration and sign-in",
                    "Staff sign-in","Animal creation, edit and persistence after reload"]
                (out/"browser-results.json").write_text(json.dumps(observed,indent=2))
                print("PASS: local browser checks completed; results and screenshots written.")
                browser.close()
        finally:
            server.shutdown()
            thread.join(5)

if __name__=="__main__":
    main()
