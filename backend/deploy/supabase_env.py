"""Write the hosted demo's database settings from the git-ignored .env.deploy (OWNER_PW, APP_PW, REF).

Finds which Supabase session pooler (IPv4, port 5432) answers for the project, then writes .env.supabase with
AAHAR_MIGRATION_DATABASE_URL, AAHAR_DATABASE_URL and AAHAR_APP_DB_PASSWORD. Prints the host only, never a password.
Usage (inside the backend container): python deploy/supabase_env.py /workspace/.env.deploy /workspace/.env.supabase
"""

import sys
from pathlib import Path
from urllib.parse import quote

import psycopg

REGIONS = ("ap-southeast-1",)
PREFIXES = ("aws-0", "aws-1")


def main() -> int:
    src, dst = sys.argv[1], sys.argv[2]
    env = dict(line.split("=", 1) for line in Path(src).read_text(encoding="utf-8").split() if "=" in line)
    ref, owner_pw, app_pw = env["REF"], env["OWNER_PW"], env["APP_PW"]
    for prefix in PREFIXES:
        for region in REGIONS:
            host = f"{prefix}-{region}.pooler.supabase.com"
            try:
                with psycopg.connect(
                    host=host,
                    port=5432,
                    dbname="postgres",
                    user=f"aahar_owner.{ref}",
                    password=owner_pw,
                    connect_timeout=10,
                ) as conn:
                    conn.execute("select 1")
            except psycopg.Error as exc:
                print(f"{host}: no ({type(exc).__name__})")
                continue
            base = f"{host}:5432/postgres"
            Path(dst).write_text(
                f"AAHAR_MIGRATION_DATABASE_URL=postgresql+psycopg://aahar_owner.{ref}:{quote(owner_pw)}@{base}\n"
                f"AAHAR_DATABASE_URL=postgresql+psycopg://aahar_app.{ref}:{quote(app_pw)}@{base}\n"
                f"AAHAR_APP_DB_PASSWORD={app_pw}\n",
                encoding="utf-8",
            )
            print(f"{host}: yes; wrote {dst}")
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
