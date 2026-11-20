"""Count physical and nonblank lines; neither is an effort or quality metric."""

from pathlib import Path
import json

root = Path(__file__).resolve().parents[1]
groups = {
    "Python application": list((root / "shelter").glob("*.py")),
    "HTML templates": list((root / "shelter/templates").glob("*.html")),
    "Custom CSS": list((root / "shelter/static").glob("*.css")),
    "SVG illustrations": list((root / "shelter/static").glob("*.svg")),
    "Automated tests": list((root.parent / "test").glob("*.py")),
    "Utility scripts": list((root / "scripts").glob("*.py")),
}
result = {}
for name, paths in groups.items():
    lines = [line for p in paths for line in p.read_text(encoding="utf-8").splitlines()]
    result[name] = {
        "files": len(paths),
        "physical_lines": len(lines),
        "nonblank_lines": sum(bool(line.strip()) for line in lines),
    }
result["method"] = (
    "Physical lines include comments and blank lines; nonblank excludes only blanks. "
    "Dependencies, documentation, generated SQL, local data and setup/config files are excluded. "
    "Formatting changes this count. It is not a completion, effort or authorship measure."
)
print(json.dumps(result, indent=2))
