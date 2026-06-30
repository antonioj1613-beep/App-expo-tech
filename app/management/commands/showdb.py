import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Print all SQLite tables in a readable format (passwords hidden)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--export",
            type=str,
            default="",
            help="Also write output to this file path (e.g. database_snapshot.txt)",
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])
        lines = self._dump(db_path)
        output = "\n".join(lines)
        self.stdout.write(output)

        export_path = options.get("export")
        if export_path:
            path = Path(export_path)
            path.write_text(output + "\n", encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"\nExported to {path.resolve()}"))

    def _dump(self, db_path: Path):
        lines = [f"Database: {db_path.resolve()}", ""]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tables = [row[0] for row in cur.fetchall()]

        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM [{table}]")
            count = cur.fetchone()[0]
            lines.append(f"=== {table} ({count} rows) ===")

            if count:
                cur.execute(f"SELECT * FROM [{table}]")
                rows = cur.fetchall()
                cols = rows[0].keys()
                lines.append("  " + " | ".join(cols))
                lines.append("  " + "-" * 72)
                for row in rows:
                    values = []
                    for col in cols:
                        val = row[col]
                        if table == "users" and col == "password":
                            val = "[bcrypt hash — hidden]"
                        values.append(str(val))
                    lines.append("  " + " | ".join(values))
                if count > 50:
                    lines.append(f"  ... showing first {min(len(rows), 50)} of {count} rows")
            lines.append("")

        conn.close()
        return lines
