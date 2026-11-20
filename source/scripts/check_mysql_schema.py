"""Compile MySQL DDL without connecting. This is NOT a MySQL integration test."""

from pathlib import Path
import sys
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shelter.models import db

output = Path(__file__).resolve().parents[1] / "docs" / "mysql-schema.sql"
statements = [
    str(CreateTable(table).compile(dialect=mysql.dialect())) + ";"
    for table in db.metadata.sorted_tables
]
output.write_text(
    "-- SQLAlchemy generated MySQL DDL. Apply via init-db.\n"
    "-- Syntax compilation only; not executed against MySQL.\n\n" + "\n\n".join(statements),
    encoding="utf-8",
)
print(
    f"Compiled {len(statements)} tables for the MySQL dialect. No server connection was made."
)
